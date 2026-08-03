"""Weather Station integration."""

from datetime import datetime, timedelta
from hmac import compare_digest
import logging
from typing import Any

import aiohttp.web
from aiohttp.web_exceptions import HTTPUnauthorized

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    API_ID,
    API_KEY,
    API_MODE,
    API_MODE_WSLINK,
    CLEANUP_INACTIVE_MIN_AGE_MIN,
    CLEANUP_INACTIVE_STREAK,
    CREDENTIAL_FIELDS_PWS,
    CREDENTIAL_FIELDS_WSLINK,
    DEFAULT_CLEANUP_INACTIVE_MIN_AGE_MIN,
    DEFAULT_CLEANUP_INACTIVE_STREAK,
    DEV_DBG,
    DOMAIN,
    RELOAD_OPTIONS,
    ROUTES_KEY,
    SENSORS_TO_LOAD,
    URI_API_PWS,
    URI_API_WSLINK,
    WSLINK_CONNECTION_KEY_BY_MODULE,
    WSLINK_PURGE_MODULES,
    WSLINK_PURGED_MODULES,
    WSLINK_SENSOR_KEYS_BY_MODULE,
)
from .device_map import channel_of_module, module_for_key, module_metadata
from .helpers import (
    anonymize,
    check_disabled,
    loaded_sensors,
    remap_items_pws,
    remap_items_wslink,
    signal_new_keys,
    translated_notification,
    translations,
)
from .routes import Routes

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


def _parse_connected(value) -> bool | None:
    """Parse WSLink connection flag (1/0)."""
    if value in (None, ""):
        return None
    try:
        return int(float(value)) == 1
    except TypeError, ValueError:
        return None


def _sensor_keys_for_modules(modules: set[str]) -> set[str]:
    """Return flattened sensor keys for multiple WSLink modules."""
    keys: set[str] = set()
    for module in modules:
        keys.update(set(WSLINK_SENSOR_KEYS_BY_MODULE.get(module, ())))
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

    # Channel diagnostic entities only exist for channel modules.
    target_unique_ids.update(
        f"{module}_channel_number"
        for module in inactive_modules
        if channel_of_module(module) is not None
    )

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


class WeatherDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manage fetched data."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Init global updater."""
        super().__init__(hass, _LOGGER, config_entry=config_entry, name=DOMAIN)

        # Safe cleanup state for WSLink modules
        self._inactive_streak: dict[str, int] = {}
        self._inactive_since: dict[str, datetime] = {}
        self._purged_modules: set[str] = {
            module
            for module in config_entry.options.get(WSLINK_PURGED_MODULES, [])
            if module in WSLINK_PURGE_MODULES
        }
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

        Only modules listed in `WSLINK_PURGE_MODULES` are evaluated.
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

        loaded = loaded_sensors(self.config_entry) or []
        discovered = check_disabled(remaped_items, self.config_entry) or []
        merged = list(dict.fromkeys([*loaded, *discovered]))

        if is_wslink:
            purged_before = set(self._purged_modules)
            inactive_modules = self._newly_confirmed_inactive_modules(data)

            still_inactive_purged = {
                module
                for module in self._purged_modules
                if self._module_connected_from_raw(data, module) is not True
            }

            effective_inactive_modules = inactive_modules | still_inactive_purged
            inactive_keys = _sensor_keys_for_modules(effective_inactive_modules)

            if inactive_keys:
                discovered = [key for key in discovered if key not in inactive_keys]
                merged = [key for key in merged if key not in inactive_keys]

            options_changed = False
            new_options = dict(self.config_entry.options)

            if merged != loaded:
                new_options[SENSORS_TO_LOAD] = merged
                options_changed = True

            if self._purged_modules != purged_before:
                new_options[WSLINK_PURGED_MODULES] = sorted(self._purged_modules)
                options_changed = True

            if options_changed:
                self.hass.config_entries.async_update_entry(
                    self.config_entry, options=new_options
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
            new_options = dict(self.config_entry.options)
            new_options[SENSORS_TO_LOAD] = merged
            self.hass.config_entries.async_update_entry(
                self.config_entry, options=new_options
            )

        self.async_set_updated_data(remaped_items)

        if new_keys := set(merged) - set(loaded):
            # Publish discoveries once the data is available, so entities created
            # by the platforms expose their value right away.
            async_dispatcher_send(self.hass, signal_new_keys(self.config_entry))
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


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    hass.data[DOMAIN].pop(entry.entry_id, None)
    if (routes := hass.data[DOMAIN].get(ROUTES_KEY)) is not None:
        routes.release()

    return True
