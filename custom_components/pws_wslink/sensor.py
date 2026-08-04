"""Sensors definition for Weather Station."""

from datetime import datetime

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import WeatherDataUpdateCoordinator
from .const import (
    API_MODE,
    API_MODE_WSLINK,
    BATTERY_LIST,
    CHILL_INDEX,
    DOMAIN,
    HEAT_INDEX,
    LIGHTNING_DISTANCE,
    LIGHTNING_STABILIZED_KEYS,
    OUTSIDE_HUMIDITY,
    OUTSIDE_TEMP,
    WIND_AZIMUTH,
    WIND_DIR,
    WIND_SPEED,
)
from .device_map import (
    channel_of_module,
    device_info_for_key,
    device_info_for_module,
    module_for_key,
)
from .helpers import (
    chill_index,
    heat_index,
    loaded_sensors,
    signal_keys_changed,
    to_int,
)
from .sensors_common import WeatherSensorEntityDescription
from .sensors_pws import SENSOR_TYPES_PWS
from .sensors_wslink import SENSOR_TYPES_WSLINK


class ChannelDiagnosticSensor(SensorEntity):
    """Static diagnostic sensor exposing the channel number of a channel module."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "channel_number"
    _attr_icon = "mdi:numeric"

    def __init__(
        self,
        config_entry: ConfigEntry,
        module: str,
        channel: int,
    ) -> None:
        """Initialize the channel number sensor of one module."""
        self._config_entry = config_entry
        self._module = module
        self._attr_unique_id = f"{config_entry.entry_id}_{module}_channel_number"
        self._attr_native_value = channel

    @property
    def device_info(self):
        """Attach the sensor to the device of its module."""
        return device_info_for_module(self._config_entry, self._module)


def _channel_diagnostic_entities(
    config_entry: ConfigEntry,
    loaded_keys: list[str],
) -> list[ChannelDiagnosticSensor]:
    """Build one diagnostic 'channel number' sensor per channel module."""
    channels: dict[str, int] = {}
    for key in loaded_keys:
        module = module_for_key(key)
        if (channel := channel_of_module(module)) is not None:
            channels[module] = channel

    return [
        ChannelDiagnosticSensor(config_entry, module, channel)
        for module, channel in sorted(channels.items(), key=lambda item: item[1])
    ]


def _sensor_entities(
    config_entry: ConfigEntry,
    coordinator: WeatherDataUpdateCoordinator,
) -> list[SensorEntity]:
    """Build every sensor entity matching the currently active keys."""
    is_wslink = config_entry.options.get(API_MODE) == API_MODE_WSLINK
    loaded_keys = loaded_sensors(config_entry)

    # Derived sensors are computed locally and never pushed by the station.
    requested = set(loaded_keys)
    if WIND_DIR in requested:
        requested.add(WIND_AZIMUTH)
    if not is_wslink:
        if {OUTSIDE_TEMP, OUTSIDE_HUMIDITY} <= requested:
            requested.add(HEAT_INDEX)
        if {OUTSIDE_TEMP, WIND_SPEED} <= requested:
            requested.add(CHILL_INDEX)

    return [
        *(
            WeatherSensor(description, coordinator)
            for description in (SENSOR_TYPES_WSLINK if is_wslink else SENSOR_TYPES_PWS)
            if description.key in requested
            and not (is_wslink and description.key in BATTERY_LIST)
        ),
        *_channel_diagnostic_entities(config_entry, loaded_keys),
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Weather Station sensors and follow later key changes."""
    coordinator: WeatherDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    tracked_unique_ids: set[str | None] = set()

    @callback
    def _async_sync_entities() -> None:
        """Add the entities of newly active keys and forget the removed ones."""
        entities = _sensor_entities(config_entry, coordinator)
        current_ids = {entity.unique_id for entity in entities}
        tracked_unique_ids.intersection_update(current_ids)

        new_entities = [
            entity for entity in entities if entity.unique_id not in tracked_unique_ids
        ]
        tracked_unique_ids.update(current_ids)
        async_add_entities(new_entities)

    config_entry.async_on_unload(
        async_dispatcher_connect(
            hass, signal_keys_changed(config_entry), _async_sync_entities
        )
    )
    _async_sync_entities()


class WeatherSensor(
    CoordinatorEntity[WeatherDataUpdateCoordinator], RestoreEntity, SensorEntity
):
    """Implementation of Weather Sensor entity."""

    _attr_has_entity_name = True

    entity_description: WeatherSensorEntityDescription

    def __init__(
        self,
        description: WeatherSensorEntityDescription,
        coordinator: WeatherDataUpdateCoordinator,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

        # Seed from the current payload so entities created after a discovery
        # expose their value without waiting for the next one.
        self._data = (coordinator.data or {}).get(description.key)

        # Bootstrap guard:
        # Keep entities available until at least one payload has been received
        # after integration startup/reload.
        self._has_seen_payload = coordinator.data is not None

    async def async_added_to_hass(self) -> None:
        """Seed the shared lightning tracker with the restored value."""
        await super().async_added_to_hass()

        key = self.entity_description.key
        if key not in LIGHTNING_STABILIZED_KEYS:
            return

        if (last_state := await self.async_get_last_state()) is None:
            return

        if key == LIGHTNING_DISTANCE:
            self.coordinator.lightning.distance = to_int(last_state.state)
        elif (restored := dt_util.parse_datetime(last_state.state)) is not None:
            self.coordinator.lightning.last_strike = dt_util.as_utc(restored)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if (data := self.coordinator.data) is not None:
            self._data = data.get(self.entity_description.key)
            self._has_seen_payload = True
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        """Bootstrap-safe availability.

        Before first payload after startup/reload, keep entity available.
        After first payload, availability follows per-entity source presence.
        """
        if not self._has_seen_payload:
            return True
        return self._source_present_in_payload()

    def _source_present_in_payload(self) -> bool:
        """Return True if current payload provides data needed by this entity."""
        if (data := self.coordinator.data) is None:
            return False

        is_wslink = (
            self.coordinator.config_entry.options.get(API_MODE) == API_MODE_WSLINK
        )
        key = self.entity_description.key

        if key in LIGHTNING_STABILIZED_KEYS:
            # The coordinator publishes these keys even before a coherent strike
            # is known, so presence of the key is what availability follows.
            return key in data

        if key == WIND_AZIMUTH:
            return data.get(WIND_DIR) not in (None, "")

        if key == HEAT_INDEX and not is_wslink:
            return data.get(OUTSIDE_TEMP) not in (None, "") and data.get(
                OUTSIDE_HUMIDITY
            ) not in (None, "")

        if key == CHILL_INDEX and not is_wslink:
            return data.get(OUTSIDE_TEMP) not in (None, "") and data.get(
                WIND_SPEED
            ) not in (None, "")

        return data.get(key) not in (None, "")

    @property
    def native_value(self) -> StateType | datetime:
        """Return the current value of the entity."""
        if not self.available:
            return None

        key = self.entity_description.key
        data = self.coordinator.data or {}
        if key == WIND_AZIMUTH:
            return self.entity_description.value_fn(data.get(WIND_DIR))

        if self.coordinator.config_entry.options.get(API_MODE) != API_MODE_WSLINK:
            if key == HEAT_INDEX:
                return self.entity_description.value_fn(heat_index(data))
            if key == CHILL_INDEX:
                return self.entity_description.value_fn(chill_index(data))

        return (
            None if self._data == "" else self.entity_description.value_fn(self._data)
        )

    @property
    def device_info(self):
        """Attach the entity to the device of its module."""
        return device_info_for_key(
            self.coordinator.config_entry, self.entity_description.key
        )
