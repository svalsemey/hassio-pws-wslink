"""Weather Station integration."""

from datetime import datetime, timedelta
import logging

import aiohttp.web
from aiohttp.web_exceptions import HTTPUnauthorized

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import InvalidStateError, PlatformNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    API_ID,
    API_KEY,
    API_MODE,
    API_MODE_WSLINK,
    BATTERY_LIST,
    BATTERY_NON_BINARY,
    CLEANUP_INACTIVE_MIN_AGE_MIN,
    CLEANUP_INACTIVE_STREAK,
    DEFAULT_CLEANUP_INACTIVE_MIN_AGE_MIN,
    DEFAULT_CLEANUP_INACTIVE_STREAK,
    DEV_DBG,
    DOMAIN,
    SENSORS_TO_LOAD,
    URI_API_PWS,
    URI_API_WSLINK,
    WATER_LEAK_LIST,
    WSLINK_CONNECTION_KEY_BY_MODULE,
    WSLINK_PURGE_MODULES,
    WSLINK_SENSOR_KEYS_BY_MODULE,
)
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


def _sensor_keys_for_module(module: str) -> set[str]:
    """Return all sensor keys belonging to one WSLink module."""
    return set(WSLINK_SENSOR_KEYS_BY_MODULE.get(module, ()))


def _sensor_keys_for_modules(modules: set[str]) -> set[str]:
    """Return flattened sensor keys for multiple WSLink modules."""
    keys: set[str] = set()
    for module in modules:
        keys.update(_sensor_keys_for_module(module))
    return keys


async def _async_remove_stale_wslink_entities_and_devices(
    hass: HomeAssistant,
    entry: ConfigEntry,
    inactive_modules: set[str],
) -> None:
    """Remove stale entities/devices for inactive WSLink modules."""
    if not inactive_modules:
        return

    ent_reg = er.async_get(hass)

    sensor_keys = _sensor_keys_for_modules(inactive_modules)
    target_unique_ids = set(sensor_keys)
    target_unique_ids.update(f"{key}_binary" for key in sensor_keys)

    # Channel diagnostic entities only exist for Type234 / Type6 modules.
    channel_modules = {
        module for module in inactive_modules if module.startswith(("t234c", "t6c"))
    }
    target_unique_ids.update(f"{module}_channel_number" for module in channel_modules)

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

        # Safe cleanup state for channel modules
        self._inactive_streak: dict[str, int] = {}
        self._inactive_since: dict[str, datetime] = {}
        self._purged_modules: set[str] = set()

        super().__init__(hass, _LOGGER, name=DOMAIN)

    def _module_connected_from_raw(self, raw_data: dict, module: str) -> bool | None:
        """Return connection status for one WSLink module from raw payload."""
        conn_key = WSLINK_CONNECTION_KEY_BY_MODULE.get(module)
        if conn_key is None:
            return None
        return _parse_connected(raw_data.get(conn_key))

    def _newly_confirmed_inactive_modules(self, raw_data: dict) -> set[str]:
        """Return WSLink modules newly confirmed as inactive (safe cleanup).

        A module is confirmed inactive only when both conditions are met:
        1) It is disconnected or missing for at least N consecutive payloads
        (`cleanup_inactive_streak`).
        2) It remains inactive for at least the configured minimum duration
        (`cleanup_inactive_min_age_min`).

        Only modules listed in `WSLINK_PURGE_MODULES` are evaluated (Type1 is excluded).
        Once a module is confirmed inactive, it is emitted only once until it reconnects.
        When a module reconnects (`cn == 1`), its inactivity tracking state is reset.
        """

        now = dt_util.utcnow()
        streak_threshold = self._cleanup_streak_threshold()
        min_age = self._cleanup_min_age()
        newly_confirmed: set[str] = set()

        for module in WSLINK_PURGE_MODULES:
            connected = self._module_connected_from_raw(raw_data, module)

            if connected is True:
                # Recovery/reset if module comes back online
                self._inactive_streak.pop(module, None)
                self._inactive_since.pop(module, None)
                self._purged_modules.discard(module)
                continue

            # connected is False or None -> count as inactive sample
            self._inactive_streak[module] = self._inactive_streak.get(module, 0) + 1
            self._inactive_since.setdefault(module, now)

            streak_ok = self._inactive_streak[module] >= streak_threshold
            age_ok = (now - self._inactive_since[module]) >= min_age

            if streak_ok and age_ok and module not in self._purged_modules:
                newly_confirmed.add(module)
                self._purged_modules.add(module)

        return newly_confirmed

    def _cleanup_streak_threshold(self) -> int:
        """Return cleanup streak threshold from options with safe fallback."""
        raw_value = self.config_entry.options.get(
            CLEANUP_INACTIVE_STREAK, DEFAULT_CLEANUP_INACTIVE_STREAK
        )
        try:
            return max(1, int(raw_value))
        except TypeError, ValueError:
            return DEFAULT_CLEANUP_INACTIVE_STREAK

    def _cleanup_min_age(self) -> timedelta:
        """Return cleanup minimum inactivity age from options with safe fallback."""
        raw_value = self.config_entry.options.get(
            CLEANUP_INACTIVE_MIN_AGE_MIN, DEFAULT_CLEANUP_INACTIVE_MIN_AGE_MIN
        )
        try:
            minutes = max(1, int(raw_value))
        except TypeError, ValueError:
            minutes = DEFAULT_CLEANUP_INACTIVE_MIN_AGE_MIN
        return timedelta(minutes=minutes)

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
            inactive_modules = self._newly_confirmed_inactive_modules(data)
            inactive_keys = _sensor_keys_for_modules(inactive_modules)

            if inactive_keys:
                merged = [key for key in merged if key not in inactive_keys]

            if merged != loaded:
                await update_options(
                    self.hass, self.config_entry, SENSORS_TO_LOAD, merged
                )

            if inactive_modules:
                _LOGGER.info(
                    "Safe cleanup: confirmed inactive modules=%s",
                    ", ".join(sorted(inactive_modules)),
                )
                await _async_remove_stale_wslink_entities_and_devices(
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
