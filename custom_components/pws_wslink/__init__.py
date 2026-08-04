"""Weather Station integration."""

from collections.abc import Mapping
from hmac import compare_digest
import logging
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    API_MODE,
    API_MODE_PWS,
    API_MODE_WSLINK,
    DEV_DBG,
    DOMAIN,
    RELOAD_OPTIONS,
    ROUTER_KEY,
    SENSORS_TO_LOAD,
    STATION_ID,
    STATION_PASSWORD,
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
from .lightning import LightningTracker
from .routes import StationRouter

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]
# Credential option keys used before they were renamed after the station wording.
_RENAMED_OPTIONS: Final[dict[str, str]] = {
    "API_ID": STATION_ID,
    "API_KEY": STATION_PASSWORD,
}


class WeatherDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manage fetched data."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Init global updater."""
        super().__init__(hass, _LOGGER, config_entry=config_entry, name=DOMAIN)

        # Snapshot of the options read while setting up, used to decide reloads.
        self._setup_options = {
            key: config_entry.options.get(key) for key in RELOAD_OPTIONS
        }
        # Shared by the strike time and distance entities of this station.
        self.lightning = LightningTracker()

    def reload_required(self) -> bool:
        """Return True when an option only read at setup time has changed."""
        return any(
            value != self.config_entry.options.get(key)
            for key, value in self._setup_options.items()
        )

    @property
    def api_mode(self) -> str:
        """Return the protocol this station is configured to use."""
        return self.config_entry.options.get(API_MODE, API_MODE_PWS)

    def credentials_match(self, station_id: str, station_password: str) -> bool:
        """Compare station credentials using constant-time comparison.

        Both comparisons are always evaluated (bitwise `&` instead of `and`)
        so that no timing information about the station id leaks.
        """
        options = self.config_entry.options
        return bool(
            compare_digest(
                str(station_id).encode(), str(options.get(STATION_ID) or "").encode()
            )
            & compare_digest(
                str(station_password).encode(),
                str(options.get(STATION_PASSWORD) or "").encode(),
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

    async def async_handle_payload(self, data: Mapping[str, Any]) -> None:
        """Process one authenticated payload coming from this station."""
        remaped_items = (
            remap_items_wslink(data)
            if self.api_mode == API_MODE_WSLINK
            else remap_items_pws(data)
        )
        self.lightning.apply(remaped_items)

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
            _LOGGER.info("Dev log for %s: %s", self.config_entry.title, anonymize(data))


def _async_router(hass: HomeAssistant) -> StationRouter:
    """Return the shared router, registering the HTTP views once."""
    hass_data = hass.data.setdefault(DOMAIN, {})

    if (router := hass_data.get(ROUTER_KEY)) is None:
        router = StationRouter()
        try:
            router.async_register_views(hass)
        except RuntimeError as err:
            raise PlatformNotReady(
                f"Unable to register the Weather Station HTTP views: {err}"
            ) from err
        hass_data[ROUTER_KEY] = router

    return router


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry only when an option read at setup time has changed.

    Sensor discovery rewrites the options from inside the HTTP handler, so
    reloading unconditionally would tear down the coordinator while it is still
    serving the request.
    """
    coordinator: WeatherDataUpdateCoordinator | None = hass.data[DOMAIN].get(
        entry.entry_id
    )
    if coordinator is None or coordinator.reload_required():
        await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate an entry created before multi-station support.

    Entity unique ids used to be bare sensor keys, which would collide as soon
    as a second station is configured, the entry unique id was the domain itself
    instead of the station id, and credentials were stored under API oriented
    keys.
    """
    if entry.version > 2:
        return False

    ent_reg = er.async_get(hass)
    prefix = f"{entry.entry_id}_"
    for reg_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if not reg_entry.unique_id.startswith(prefix):
            ent_reg.async_update_entity(
                reg_entry.entity_id, new_unique_id=f"{prefix}{reg_entry.unique_id}"
            )

    data = {_RENAMED_OPTIONS.get(key, key): value for key, value in entry.data.items()}
    options = {
        _RENAMED_OPTIONS.get(key, key): value for key, value in entry.options.items()
    }

    hass.config_entries.async_update_entry(
        entry,
        version=2,
        unique_id=options.get(STATION_ID) or data.get(STATION_ID),
        data=data,
        options=options,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the config entry of one weather station."""
    coordinator = WeatherDataUpdateCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    _async_router(hass).register(entry.entry_id, coordinator)

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
    """Unload a config entry, leaving the other stations untouched."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    hass.data[DOMAIN].pop(entry.entry_id, None)
    if (router := hass.data[DOMAIN].get(ROUTER_KEY)) is not None:
        router.unregister(entry.entry_id)

    return True
