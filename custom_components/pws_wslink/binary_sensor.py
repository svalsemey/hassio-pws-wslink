"""Binary sensors for Weather Station."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import WeatherDataUpdateCoordinator
from .const import (
    API_MODE,
    API_MODE_WSLINK,
    BATTERY,
    BATTERY_LIST,
    DOMAIN,
    WATER_LEAK,
    WATER_LEAK_LIST,
)
from .device_map import device_info_for_key
from .helpers import loaded_sensors, signal_keys_changed


@dataclass(frozen=True, kw_only=True)
class WeatherBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describe battery binary sensor entities."""

    value_fn: Callable[[Any], bool | None]


def _battery_is_low(value: Any) -> bool | None:
    """Map station battery state to HA binary battery semantics.

    Station values:
    - 1 = battery normal
    - 0 = battery low / drained

    HA binary_sensor battery semantics:
    - is_on = battery low
    - is_off = battery normal
    """

    if value in (None, ""):
        return None

    try:
        parsed = int(float(value))
    except TypeError, ValueError:
        return None

    if parsed == 0:
        return True
    if parsed == 1:
        return False
    return None


def _water_leak_detected(value: Any) -> bool | None:
    """Map station leak state to HA moisture binary sensor semantics.

    Station:
    - 1 = leak
    - 0 = no leak

    HA moisture binary_sensor:
    - is_on = moisture/leak detected
    """
    if value in (None, ""):
        return None

    try:
        parsed = int(float(value))
    except TypeError, ValueError:
        return None

    if parsed == 1:
        return True
    if parsed == 0:
        return False
    return None


BATTERY_BINARY_SENSORS: tuple[WeatherBinarySensorEntityDescription, ...] = tuple(
    WeatherBinarySensorEntityDescription(
        key=battery_key,
        translation_key=BATTERY,
        device_class=BinarySensorDeviceClass.BATTERY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_battery_is_low,
    )
    for battery_key in BATTERY_LIST
)

WATER_LEAK_BINARY_SENSORS: tuple[WeatherBinarySensorEntityDescription, ...] = tuple(
    WeatherBinarySensorEntityDescription(
        key=leak_key,
        translation_key=WATER_LEAK,
        device_class=BinarySensorDeviceClass.MOISTURE,
        value_fn=_water_leak_detected,
    )
    for leak_key in WATER_LEAK_LIST
)


class WeatherBinarySensor(
    CoordinatorEntity[WeatherDataUpdateCoordinator], BinarySensorEntity
):
    """Representation of Weather Station battery binary sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: WeatherDataUpdateCoordinator,
        description: WeatherBinarySensorEntityDescription,
    ) -> None:
        """Initialize binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{description.key}_binary"
        )

        # Bootstrap guard:
        # Keep entities available until at least one payload has been received
        # after integration startup/reload.
        self._has_seen_payload = coordinator.data is not None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data is not None:
            self._has_seen_payload = True
        super()._handle_coordinator_update()

    @property
    def is_on(self) -> bool | None:
        """Return true when battery is low."""
        if not self.coordinator.data:
            return None
        raw_value = self.coordinator.data.get(self.entity_description.key)
        return self.entity_description.value_fn(raw_value)

    @property
    def available(self) -> bool:
        """Bootstrap-safe availability.

        Before first payload after startup/reload, keep entity available.
        After first payload, availability follows source presence.
        """
        if not self._has_seen_payload:
            return True
        return self._source_present_in_payload()

    @property
    def device_info(self):
        """Attach the entity to the device of its module."""
        return device_info_for_key(
            self.coordinator.config_entry, self.entity_description.key
        )

    def _source_present_in_payload(self) -> bool:
        """Return True if payload has a source value for this key."""
        data = self.coordinator.data
        return data is not None and data.get(self.entity_description.key) not in (
            None,
            "",
        )


def _binary_sensor_entities(
    config_entry: ConfigEntry,
    coordinator: WeatherDataUpdateCoordinator,
) -> list[WeatherBinarySensor]:
    """Build every binary sensor matching the currently active keys."""
    sensors_to_load = set(loaded_sensors(config_entry))
    return [
        WeatherBinarySensor(coordinator, description)
        for description in (*BATTERY_BINARY_SENSORS, *WATER_LEAK_BINARY_SENSORS)
        if description.key in sensors_to_load
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Weather Station battery and water leak binary sensors."""
    # Binary battery and leak fields are WSLink-specific in this integration.
    if config_entry.options.get(API_MODE) != API_MODE_WSLINK:
        return

    coordinator: WeatherDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    tracked_unique_ids: set[str | None] = set()

    @callback
    def _async_sync_entities() -> None:
        """Add the entities of newly active keys and forget the removed ones."""
        entities = _binary_sensor_entities(config_entry, coordinator)
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
