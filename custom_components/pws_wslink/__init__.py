"""Weather Station integration."""

import logging

import aiohttp.web
from aiohttp.web_exceptions import HTTPUnauthorized

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import InvalidStateError, PlatformNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    API_ID,
    API_KEY,
    API_MODE,
    API_MODE_WSLINK,
    BATTERY_LIST,
    BATTERY_NON_BINARY,
    DEV_DBG,
    DOMAIN,
    SENSORS_TO_LOAD,
    T6_BATTERY_KEYS,
    T6_WATER_LEAK_KEYS,
    T234_BATTERY_KEYS,
    T234_HUMIDITY_KEYS,
    T234_TEMP_KEYS,
    URI_API_PWS,
    URI_API_WSLINK,
    WATER_LEAK_LIST,
)
from .device_map import module_for_key
from .helpers import (
    anonymize,
    check_disabled,
    loaded_sensors,
    remap_items_pws,
    remap_items_wslink,
    translated_notification,
    translations,
    update_options,
)
from .routes import Routes, unregistered

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


class IncorrectDataError(InvalidStateError):
    """Invalid exception."""


def _parse_connected(value) -> bool | None:
    """Parse WSLink connection flag (1/0)."""
    if value in (None, ""):
        return None
    try:
        return int(float(value)) == 1
    except TypeError, ValueError:
        return None


def _wslink_inactive_channel_modules(raw_data: dict) -> set[str]:
    """Return inactive WSLink channel modules (Type234 / Type6).

    Inactive means: cn missing, empty, or not equal to 1.
    """
    inactive: set[str] = set()

    for idx in range(7):
        ch = idx + 1

        if _parse_connected(raw_data.get(f"t234c{ch}cn")) is not True:
            inactive.add(f"t234c{ch}")

        if _parse_connected(raw_data.get(f"t6c{ch}cn")) is not True:
            inactive.add(f"t6c{ch}")

    return inactive


def _sensor_keys_for_channel_module(module: str) -> set[str]:
    """Return all sensor keys belonging to one channel module."""
    if module.startswith("t234c"):
        ch_txt = module[5:]
        if ch_txt.isdigit():
            idx = int(ch_txt) - 1
            if 0 <= idx < 7:
                return {
                    T234_TEMP_KEYS[idx],
                    T234_HUMIDITY_KEYS[idx],
                    T234_BATTERY_KEYS[idx],
                }
        return set()

    if module.startswith("t6c"):
        ch_txt = module[3:]
        if ch_txt.isdigit():
            idx = int(ch_txt) - 1
            if 0 <= idx < 7:
                return {
                    T6_WATER_LEAK_KEYS[idx],
                    T6_BATTERY_KEYS[idx],
                }
        return set()

    return set()


def _sensor_keys_for_channel_modules(modules: set[str]) -> set[str]:
    """Return flattened sensor keys for multiple channel modules."""
    keys: set[str] = set()
    for module in modules:
        keys.update(_sensor_keys_for_channel_module(module))
    return keys


def _channel_modules_from_keys(keys: set[str]) -> set[str]:
    """Extract channel module ids from sensor keys."""
    modules: set[str] = set()
    for key in keys:
        module = module_for_key(key)
        if module.startswith("t234c") or module.startswith("t6c"):
            modules.add(module)
    return modules


async def _async_remove_stale_channel_entities_and_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    inactive_modules: set[str],
) -> None:
    """Remove stale entities/devices for inactive WSLink channel modules."""
    if not inactive_modules:
        return

    ent_reg = er.async_get(hass)

    sensor_keys = _sensor_keys_for_channel_modules(inactive_modules)
    target_unique_ids = set(sensor_keys)
    target_unique_ids.update(f"{key}_binary" for key in sensor_keys)
    target_unique_ids.update(f"{module}_channel_number" for module in inactive_modules)

    for entity_id, reg_entry in list(ent_reg.entities.items()):
        if reg_entry.config_entry_id != entry.entry_id:
            continue
        if reg_entry.unique_id in target_unique_ids:
            ent_reg.async_remove(entity_id)

    dev_reg = dr.async_get(hass)
    for module in inactive_modules:
        identifier = (DOMAIN, f"{entry.entry_id}_{module}")
        device = dev_reg.async_get_device(identifiers={identifier})
        if device is None:
            continue

        linked_entities = er.async_entries_for_device(
            ent_reg, device_id=device.id, include_disabled_entities=True
        )
        if linked_entities:
            continue

        dev_reg.async_remove_device(device.id)


def _notification_translation_candidates(sensor_key: str) -> list[str]:
    """Return ordered translation candidates for 'new sensors' notifications.

    Order:
    1) Specific key (backward-compatible): sensor.<sensor_key>
    2) Generic key fallback based on sensor family
    """
    candidates = [f"sensor.{sensor_key}"]

    if sensor_key in BATTERY_LIST or sensor_key in BATTERY_NON_BINARY:
        # Prefer binary sensor generic wording for batteries; fallback to sensor generic.
        candidates.extend(["binary_sensor.battery", "sensor.battery"])
    elif sensor_key in WATER_LEAK_LIST:
        candidates.append("binary_sensor.water_leak")
    elif sensor_key.endswith("_temp"):
        candidates.append("sensor.temperature")
    elif sensor_key.endswith("_humidity"):
        candidates.append("sensor.humidity")

    return candidates


class WeatherDataUpdateCoordinator(DataUpdateCoordinator):
    """Manage fetched data."""

    def __init__(self, hass: HomeAssistant, config: ConfigEntry) -> None:
        """Init global updater."""
        self.hass = hass
        self.config = config
        self.config_entry = config
        super().__init__(hass, _LOGGER, name=DOMAIN)

    async def received_data(self, webdata: aiohttp.web.Request):
        """Handle incoming data query."""
        is_wslink = self.config_entry.options.get(API_MODE) == API_MODE_WSLINK
        get_data = webdata.query
        post_data = await webdata.post()

        data = dict(get_data) | dict(post_data)

        if not is_wslink and ("ID" not in data or "PASSWORD" not in data):
            _LOGGER.error("Invalid request. No security data provided!")
            raise HTTPUnauthorized

        if is_wslink and ("wsid" not in data or "wspw" not in data):
            _LOGGER.error("Invalid request. No security data provided!")
            raise HTTPUnauthorized

        if is_wslink:
            id_data = data["wsid"]
            key_data = data["wspw"]
        else:
            id_data = data["ID"]
            key_data = data["PASSWORD"]

        _id = self.config_entry.options.get(API_ID)
        _key = self.config_entry.options.get(API_KEY)

        if id_data != _id or key_data != _key:
            _LOGGER.error("Unauthorised access!")
            raise HTTPUnauthorized

        remaped_items = remap_items_wslink(data) if is_wslink else remap_items_pws(data)

        loaded = loaded_sensors(self.config_entry) or []
        discovered = check_disabled(self.hass, remaped_items, self.config) or []

        if discovered:
            translated_names: list[str] = []
            for t_key in discovered:
                resolved_name = ""
                for tr_key in _notification_translation_candidates(t_key):
                    resolved_name = await translations(
                        self.hass,
                        DOMAIN,
                        tr_key,
                        key="name",
                        category="entity",
                    )
                    if resolved_name:
                        break
                translated_names.append(resolved_name or t_key)

            human_readable = "\n".join(translated_names)
            await translated_notification(
                self.hass,
                DOMAIN,
                "new_sensors",
                {"added_sensors": f"{human_readable}\n"},
            )

        merged = list(dict.fromkeys([*loaded, *discovered]))

        if is_wslink:
            inactive_modules = _wslink_inactive_channel_modules(data)
            inactive_keys = _sensor_keys_for_channel_modules(inactive_modules)

            if inactive_keys:
                merged = [key for key in merged if key not in inactive_keys]

            if merged != loaded:
                await update_options(
                    self.hass, self.config_entry, SENSORS_TO_LOAD, merged
                )

            if inactive_modules:
                await _async_remove_stale_channel_entities_and_devices(
                    self.hass, self.config_entry, inactive_modules
                )
        elif merged != loaded:
            await update_options(self.hass, self.config_entry, SENSORS_TO_LOAD, merged)

        self.async_set_updated_data(remaped_items)

        if self.config_entry.options.get(DEV_DBG):
            _LOGGER.info("Dev log: %s", anonymize(data))

        return aiohttp.web.Response(body="OK", status=200)


def register_path(
    hass: HomeAssistant,
    url_path: str,
    coordinator: WeatherDataUpdateCoordinator,
    config: ConfigEntry,
):
    """Register path to handle incoming data."""

    hass_data = hass.data.setdefault(DOMAIN, {})
    debug = config.options.get(DEV_DBG)
    is_wslink = config.options.get(API_MODE) == API_MODE_WSLINK

    routes: Routes = hass_data.get("routes", Routes())

    if not routes.routes:
        routes = Routes()
        _LOGGER.info("Routes not found, creating new routes")

        if debug:
            _LOGGER.debug("Enabled route is: %s, WSLink is %s", url_path, is_wslink)

        try:
            default_route = hass.http.app.router.add_get(
                URI_API_PWS,
                coordinator.received_data if not is_wslink else unregistered,
                name="weather_default_url",
            )
            if debug:
                _LOGGER.debug("Default route: %s", default_route)

            wslink_route = hass.http.app.router.add_get(
                URI_API_WSLINK,
                coordinator.received_data if is_wslink else unregistered,
                name="weather_wslink_url",
            )
            if debug:
                _LOGGER.debug("WSLink route: %s", wslink_route)

            wslink_post_route = hass.http.app.router.add_post(
                URI_API_WSLINK,
                coordinator.received_data if is_wslink else unregistered,
                name="weather_wslink_post_route_url",
            )
            if debug:
                _LOGGER.debug("WSLink route: %s", wslink_post_route)

            routes.add_route(
                URI_API_PWS,
                default_route,
                coordinator.received_data if not is_wslink else unregistered,
                not is_wslink,
            )
            routes.add_route(
                URI_API_WSLINK, wslink_route, coordinator.received_data, is_wslink
            )

            routes.add_route(
                URI_API_WSLINK, wslink_post_route, coordinator.received_data, is_wslink
            )

            hass_data["routes"] = routes

        except RuntimeError as Ex:
            if (
                "Added route will never be executed, method GET is already registered"
                in Ex.args
            ):
                _LOGGER.info("Handler to URL (%s) already registred", url_path)
                return False

            _LOGGER.error("Unable to register URL handler! (%s)", Ex.args)
            return False

        _LOGGER.info(
            "Registered path to handle weather data: %s",
            routes.get_enabled(),  # pylint: disable=used-before-assignment
        )

    if is_wslink:
        routes.switch_route(coordinator.received_data, URI_API_WSLINK)
    else:
        routes.switch_route(coordinator.received_data, URI_API_PWS)

    return routes


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the config entry for my device."""

    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    hass_data = hass.data.setdefault(DOMAIN, {})
    hass_data[entry.entry_id] = coordinator

    is_wslink = entry.options.get(API_MODE) == API_MODE_WSLINK
    debug = entry.options.get(DEV_DBG)

    if debug:
        _LOGGER.debug("WS Link is %s", "enabled" if is_wslink else "disabled")

    route = register_path(
        hass, URI_API_PWS if not is_wslink else URI_API_WSLINK, coordinator, entry
    )

    if not route:
        _LOGGER.error("Fatal: path not registered!")
        raise PlatformNotReady

    hass_data["route"] = route

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Update setup listener."""

    await hass.config_entries.async_reload(entry.entry_id)

    _LOGGER.info("Settings updated")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    _ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if _ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return _ok
