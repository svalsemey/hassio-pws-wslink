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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import WeatherDataUpdateCoordinator
from .const import BATTERY_LIST, DOMAIN, SENSORS_TO_LOAD, WSLINK


@dataclass(frozen=True, kw_only=True)
class BatteryBinarySensorEntityDescription(BinarySensorEntityDescription):
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
        parsed = int(value)
    except TypeError, ValueError:
        return None

    if parsed == 0:
        return True
    if parsed == 1:
        return False
    return None


BATTERY_BINARY_SENSORS: tuple[BatteryBinarySensorEntityDescription, ...] = tuple(
    BatteryBinarySensorEntityDescription(
        key=battery_key,
        translation_key=battery_key,
        device_class=BinarySensorDeviceClass.BATTERY,
        value_fn=_battery_is_low,
    )
    for battery_key in BATTERY_LIST
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Weather Station battery binary sensors."""
    coordinator: WeatherDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Binary battery fields are WSLink-specific in this integration.
    if not config_entry.options.get(WSLINK, False):
        return

    sensors_to_load = config_entry.options.get(SENSORS_TO_LOAD, [])
    if not isinstance(sensors_to_load, list):
        sensors_to_load = []

    entities = [
        WeatherBatteryBinarySensor(coordinator, description)
        for description in BATTERY_BINARY_SENSORS
        if description.key in sensors_to_load
    ]

    if entities:
        async_add_entities(entities)


class WeatherBatteryBinarySensor(
    CoordinatorEntity[WeatherDataUpdateCoordinator], BinarySensorEntity
):
    """Representation of Weather Station battery binary sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: WeatherDataUpdateCoordinator,
        description: BatteryBinarySensorEntityDescription,
    ) -> None:
        """Initialize binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{description.key}_binary"

        # Bootstrap guard:
        # Keep entities available until at least one payload has been received
        # after integration startup/reload.
        self._has_seen_payload = False

    async def async_added_to_hass(self) -> None:
        """Handle entity added to hass."""
        await super().async_added_to_hass()
        self.coordinator.async_add_listener(self._handle_coordinator_update)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        data = (
            self.coordinator.data if isinstance(self.coordinator.data, dict) else None
        )

        # Mark bootstrap as completed once we receive first payload
        if data is not None:
            self._has_seen_payload = True

        super()._handle_coordinator_update()
        self.async_write_ha_state()

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
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            connections=set(),
            name="Weather Station",
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN,)},
            manufacturer="PWS/WU / WS-Link",
            model="Weather Station",
        )

    def _source_present_in_payload(self) -> bool:
        """Return True if payload has source value for this battery key."""
        if not isinstance(self.coordinator.data, dict):
            return False
        return self.coordinator.data.get(self.entity_description.key) not in (None, "")
