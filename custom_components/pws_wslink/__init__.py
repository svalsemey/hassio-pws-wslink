"""Weather Station integration."""

from hmac import compare_digest
import logging
from typing import Any

import aiohttp.web
from aiohttp.web_exceptions import HTTPUnauthorized

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    API_ID,
    API_KEY,
    API_MODE,
    API_MODE_WSLINK,
    CREDENTIAL_FIELDS_PWS,
    CREDENTIAL_FIELDS_WSLINK,
    DEV_DBG,
    DOMAIN,
    RELOAD_OPTIONS,
    ROUTES_KEY,
    SENSORS_TO_LOAD,
    URI_API_PWS,
    URI_API_WSLINK,
)
from .device_map import module_for_key, module_metadata
from .helpers import (
    anonymize,
    check_disabled,
    loaded_sensors,
    remap_items_pws,
    remap_items_wslink,
    signal_keys_changed,
    translated_notification,
    translations,
)
from .routes import Routes

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


class WeatherDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manage fetched data."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Init global updater."""
        super().__init__(hass, _LOGGER, config_entry=config_entry, name=DOMAIN)

        # Snapshot of the options read while setting up, used to decide reloads.
        self._setup_options = {
            key: config_entry.options.get(key) for key in RELOAD_OPTIONS
        }

    def reload_required(self) -> bool:
        """Return True when an option only read at setup time has changed."""
        return any(
            value != self.config_entry.options.get(key)
            for key, value in self._setup_options.items()
        )

    def _credentials_match(self, station_id: str, station_key: str) -> bool:
        """Compare station credentials using constant-time comparison.

        Both comparisons are always evaluated (bitwise `&` instead of `and`)
        so that no timing information about the station id leaks.
        """
        options = self.config_entry.options
        return bool(
            compare_digest(
                str(station_id).encode(), str(options.get(API_ID) or "").encode()
            )
            & compare_digest(
                str(station_key).encode(), str(options.get(API_KEY) or "").encode()
            )
        )

    async def _async_notify_new_modules(
        self, new_keys: set[str], known_keys: list[str]
    ) -> None:
        """Notify the user about the station modules revealed by new sensor keys.

        Modules are named with the device labels of strings.json, so the
        notification matches what the device page shows.
        """
        new_modules = {module_for_key(key) for key in new_keys} - {
            module_for_key(key) for key in known_keys
        }
        if not new_modules:
            return

        labels: list[str] = []
        for module in new_modules:
            _, translation_key, placeholders = module_metadata(module)
            label = await translations(
                self.hass, DOMAIN, translation_key, "device", key="name"
            )
            if label and placeholders:
                label = label.format(**placeholders)
            labels.append(label or module)

        await translated_notification(
            self.hass,
            DOMAIN,
            "new_modules",
            {"modules": "\n".join(sorted(labels))},
            f"{DOMAIN}_new_modules_{self.config_entry.entry_id}",
        )

    async def received_data(self, webdata: aiohttp.web.Request) -> aiohttp.web.Response:
        """Handle incoming data query."""
        is_wslink = self.config_entry.options.get(API_MODE) == API_MODE_WSLINK
        data = dict(webdata.query) | dict(await webdata.post())
        id_field, key_field = (
            CREDENTIAL_FIELDS_WSLINK if is_wslink else CREDENTIAL_FIELDS_PWS
        )

        if id_field not in data or key_field not in data:
            _LOGGER.error("Invalid request. No security data provided!")
            raise HTTPUnauthorized

        if not self._credentials_match(data[id_field], data[key_field]):
            _LOGGER.error("Unauthorised access on %s", webdata.path)
            raise HTTPUnauthorized

        remaped_items = remap_items_wslink(data) if is_wslink else remap_items_pws(data)

        loaded = loaded_sensors(self.config_entry)
        merged = list(
            dict.fromkeys(
                [*loaded, *(check_disabled(remaped_items, self.config_entry) or [])]
            )
        )

        if merged != loaded:
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                options={**self.config_entry.options, SENSORS_TO_LOAD: merged},
            )

        self.async_set_updated_data(remaped_items)

        if new_keys := set(merged) - set(loaded):
            # Publish discoveries once the data is available, so entities created
            # by the platforms expose their value right away.
            async_dispatcher_send(self.hass, signal_keys_changed(self.config_entry))
            await self._async_notify_new_modules(new_keys, loaded)

        if self.config_entry.options.get(DEV_DBG):
            _LOGGER.info("Dev log: %s", anonymize(data))

        return aiohttp.web.Response(body="OK", status=200)


def _async_routes(hass: HomeAssistant) -> Routes:
    """Return the shared route registry, registering the HTTP views once."""
    hass_data = hass.data.setdefault(DOMAIN, {})

    if (routes := hass_data.get(ROUTES_KEY)) is None:
        routes = Routes()
        try:
            routes.async_register_views(hass)
        except RuntimeError as err:
            raise PlatformNotReady(
                f"Unable to register the Weather Station HTTP views: {err}"
            ) from err
        hass_data[ROUTES_KEY] = routes

    return routes


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry only when an option read at setup time has changed.

    Sensor discovery rewrites the options from inside the HTTP handler, so
    reloading unconditionally would tear down the coordinator while it is still
    serving the request and reset the module inactivity counters.
    """
    coordinator: WeatherDataUpdateCoordinator | None = hass.data[DOMAIN].get(
        entry.entry_id
    )
    if coordinator is None or coordinator.reload_required():
        await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the config entry for the weather station."""
    coordinator = WeatherDataUpdateCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    _async_routes(hass).switch_route(
        coordinator.received_data,
        URI_API_WSLINK
        if entry.options.get(API_MODE) == API_MODE_WSLINK
        else URI_API_PWS,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """Let the user delete a module from its Home Assistant device page.

    The sensor keys of the module are dropped from the entry, so the device and
    its entities are only recreated once the station sends that module again.
    """
    prefix = f"{config_entry.entry_id}_"
    modules = {
        identifier.removeprefix(prefix)
        for domain, identifier in device_entry.identifiers
        if domain == DOMAIN and identifier.startswith(prefix)
    }

    loaded = loaded_sensors(config_entry)
    remaining = [key for key in loaded if module_for_key(key) not in modules]
    if remaining != loaded:
        hass.config_entries.async_update_entry(
            config_entry,
            options={**config_entry.options, SENSORS_TO_LOAD: remaining},
        )
        async_dispatcher_send(hass, signal_keys_changed(config_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    hass.data[DOMAIN].pop(entry.entry_id, None)
    if (routes := hass.data[DOMAIN].get(ROUTES_KEY)) is not None:
        routes.release()

    return True
