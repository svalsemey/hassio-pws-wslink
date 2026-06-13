"""Sensors definition for Weather Station."""

from datetime import datetime
import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo, generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import WeatherDataUpdateCoordinator
from .const import (
    BATTERY_LIST,
    CHILL_INDEX,
    DOMAIN,
    HEAT_INDEX,
    LIGHTNING_DISTANCE,
    LIGHTNING_STRIKE_COUNT_LAST_HOUR,
    LIGHTNING_STRIKE_TIME,
    OUTSIDE_HUMIDITY,
    OUTSIDE_TEMP,
    SENSORS_TO_LOAD,
    WIND_AZIMUTH,
    WIND_DIR,
    WIND_SPEED,
    WSLINK,
    UnitOfBat,
)
from .sensors_common import WeatherSensorEntityDescription
from .sensors_weather import SENSOR_TYPES_WEATHER_API
from .sensors_wslink import SENSOR_TYPES_WSLINK
from .utils import (
    battery_level_to_icon,
    battery_level_to_text,
    chill_index,
    heat_index,
    minutes_since_to_timestamp,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Weather Station sensors."""

    coordinator: WeatherDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    sensors_to_load: list = []
    sensors: list = []
    _wslink = config_entry.options.get(WSLINK)

    sensor_types = SENSOR_TYPES_WSLINK if _wslink else SENSOR_TYPES_WEATHER_API

    # Check if we have some sensors to load.
    if sensors_to_load := config_entry.options.get(SENSORS_TO_LOAD, []):
        if WIND_DIR in sensors_to_load:
            sensors_to_load.append(WIND_AZIMUTH)
        if (OUTSIDE_HUMIDITY in sensors_to_load) and (OUTSIDE_TEMP in sensors_to_load):
            sensors_to_load.append(HEAT_INDEX)

        if (WIND_SPEED in sensors_to_load) and (OUTSIDE_TEMP in sensors_to_load):
            sensors_to_load.append(CHILL_INDEX)
        sensors = [
            WeatherSensor(hass, description, coordinator)
            for description in sensor_types
            if description.key in sensors_to_load
            and not (_wslink and description.key in BATTERY_LIST)
        ]
        async_add_entities(sensors)


class WeatherSensor(  # pyright: ignore[reportIncompatibleVariableOverride]
    RestoreEntity, CoordinatorEntity[WeatherDataUpdateCoordinator], SensorEntity
):  # pyright: ignore[reportIncompatibleVariableOverride]
    """Implementation of Weather Sensor entity."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        description: WeatherSensorEntityDescription,
        coordinator: WeatherDataUpdateCoordinator,
    ) -> None:
        """Initialize sensor."""
        super().__init__(coordinator)
        self.hass = hass
        self.coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = description.key
        self._data = None

        # Bootstrap guard:
        # Keep entities available until at least one payload has been received
        # after integration startup/reload.
        self._has_seen_payload = False

        # Lightning timestamp stabilization state (persisted/restored)
        self._last_lightning_ts: datetime | None = None
        self._last_lightning_minutes: int | None = None
        self._last_lightning_count_last_hour: int | None = None
        self._last_lightning_distance: int | None = None

    async def async_added_to_hass(self) -> None:
        """Handle listeners and restore state."""
        await super().async_added_to_hass()

        # Restore persisted lightning state after HA restart
        if self.entity_description.key in (LIGHTNING_STRIKE_TIME, LIGHTNING_DISTANCE):
            last_state = await self.async_get_last_state()
            if last_state:
                if self.entity_description.key == LIGHTNING_STRIKE_TIME:
                    restored_ts = dt_util.parse_datetime(last_state.state)
                    if restored_ts is not None:
                        self._last_lightning_ts = dt_util.as_utc(restored_ts)

                if self.entity_description.key == LIGHTNING_DISTANCE:
                    self._last_lightning_distance = self._to_int(last_state.state)

                self._last_lightning_minutes = self._to_int(
                    last_state.attributes.get("last_minutes_since_strike")
                )
                self._last_lightning_count_last_hour = self._to_int(
                    last_state.attributes.get("last_count_last_hour")
                )

        self.coordinator.async_add_listener(self._handle_coordinator_update)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        data = (
            self.coordinator.data if isinstance(self.coordinator.data, dict) else None
        )
        self._data = data.get(self.entity_description.key) if data is not None else None

        # Mark bootstrap as completed once we receive first payload
        if data is not None:
            self._has_seen_payload = True

        super()._handle_coordinator_update()
        self.async_write_ha_state()

    @staticmethod
    def _to_int(value) -> int | None:
        """Convert value to int safely."""
        if value in (None, ""):
            return None
        try:
            return int(float(value))
        except TypeError, ValueError:
            return None

    @staticmethod
    def _has_value(value) -> bool:
        """Return True if payload value is usable."""
        return value not in (None, "")

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
        data = self.coordinator.data
        if not isinstance(data, dict):
            return False

        _wslink = self.coordinator.config.options.get(WSLINK)
        key = self.entity_description.key

        if key == WIND_AZIMUTH:
            return data.get(WIND_DIR) not in (None, "")

        if key == HEAT_INDEX and not _wslink:
            return data.get(OUTSIDE_TEMP) not in (None, "") and data.get(
                OUTSIDE_HUMIDITY
            ) not in (None, "")

        if key == CHILL_INDEX and not _wslink:
            return data.get(OUTSIDE_TEMP) not in (None, "") and data.get(
                WIND_SPEED
            ) not in (None, "")

        return data.get(key) not in (None, "")

    def _stable_lightning_last_strike(self) -> datetime | None:
        """Return stable lightning last-strike timestamp.

        Strict rule:
        - Update timestamp ONLY when:
        1) minutes-since-strike drops (counter reset/new strike)
        2) and strike count over last hour increases at the same time.
        - Otherwise keep previously coherent timestamp.
        """
        if not self.coordinator.data:
            return self._last_lightning_ts

        raw_minutes = self.coordinator.data.get(LIGHTNING_STRIKE_TIME)
        raw_count = self.coordinator.data.get(LIGHTNING_STRIKE_COUNT_LAST_HOUR)

        minutes_now = self._to_int(raw_minutes)
        count_now = self._to_int(raw_count)

        # No usable current value -> keep last coherent one
        if minutes_now is None:
            return self._last_lightning_ts

        candidate_ts = minutes_since_to_timestamp(minutes_now)
        if candidate_ts is None:
            return self._last_lightning_ts

        # First coherent sample (cold start without restore)
        if self._last_lightning_ts is None:
            self._last_lightning_ts = candidate_ts
            self._last_lightning_minutes = minutes_now
            self._last_lightning_count_last_hour = count_now
            return self._last_lightning_ts

        minutes_dropped = (
            self._last_lightning_minutes is not None
            and minutes_now < self._last_lightning_minutes
        )
        count_increased = (
            count_now is not None
            and self._last_lightning_count_last_hour is not None
            and count_now > self._last_lightning_count_last_hour
        )

        # Accept as real new strike ONLY if both conditions are true
        if minutes_dropped and count_increased:
            self._last_lightning_ts = candidate_ts

        # Always refresh comparators for next cycle
        self._last_lightning_minutes = minutes_now
        self._last_lightning_count_last_hour = count_now

        return self._last_lightning_ts

    def _stable_lightning_distance(self) -> int | None:
        """Return stable lightning distance in km (integer).

        Strict rule (same as lightning_last_strike_time):
        - Update distance ONLY when:
        1) minutes-since-strike drops
        2) and strike count over last hour increases.
        - Otherwise keep previously coherent distance.
        """
        if not self.coordinator.data:
            return self._last_lightning_distance

        raw_distance = self.coordinator.data.get(LIGHTNING_DISTANCE)
        raw_minutes = self.coordinator.data.get(LIGHTNING_STRIKE_TIME)
        raw_count = self.coordinator.data.get(LIGHTNING_STRIKE_COUNT_LAST_HOUR)

        distance_now = self._to_int(raw_distance)
        minutes_now = self._to_int(raw_minutes)
        count_now = self._to_int(raw_count)

        if distance_now is None:
            return self._last_lightning_distance

        # First coherent sample
        if self._last_lightning_distance is None:
            self._last_lightning_distance = distance_now
            self._last_lightning_minutes = minutes_now
            self._last_lightning_count_last_hour = count_now
            return self._last_lightning_distance

        minutes_dropped = (
            self._last_lightning_minutes is not None
            and minutes_now is not None
            and minutes_now < self._last_lightning_minutes
        )
        count_increased = (
            count_now is not None
            and self._last_lightning_count_last_hour is not None
            and count_now > self._last_lightning_count_last_hour
        )

        # Accept as real new strike ONLY if both conditions are true
        if minutes_dropped and count_increased:
            self._last_lightning_distance = distance_now

        # Always refresh comparators for next cycle
        self._last_lightning_minutes = minutes_now
        self._last_lightning_count_last_hour = count_now

        return self._last_lightning_distance

    @property
    def native_value(self):  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return value of entity."""
        if not self.available:
            return None

        _wslink = self.coordinator.config.options.get(WSLINK)
        data = self.coordinator.data if isinstance(self.coordinator.data, dict) else {}

        if self.entity_description.key == LIGHTNING_STRIKE_TIME:
            return self._stable_lightning_last_strike()

        if self.entity_description.key == LIGHTNING_DISTANCE:
            return self._stable_lightning_distance()

        if self.entity_description.key == WIND_AZIMUTH:
            return self.entity_description.value_fn(data.get(WIND_DIR))  # pyright: ignore[ reportAttributeAccessIssue]

        if self.entity_description.key == HEAT_INDEX and not _wslink:
            return self.entity_description.value_fn(heat_index(data))  # pyright: ignore[ reportAttributeAccessIssue]

        if self.entity_description.key == CHILL_INDEX and not _wslink:
            return self.entity_description.value_fn(chill_index(data))  # pyright: ignore[ reportAttributeAccessIssue]

        return (
            None if self._data == "" else self.entity_description.value_fn(self._data)
        )  # pyright: ignore[ reportAttributeAccessIssue]

    @property
    def extra_state_attributes(self) -> dict[str, int | str] | None:
        """Persist helper attributes for lightning restoration."""
        if self.entity_description.key not in (
            LIGHTNING_STRIKE_TIME,
            LIGHTNING_DISTANCE,
        ):
            return None

        attrs: dict[str, int | float | str] = {}

        if self._last_lightning_minutes is not None:
            attrs["last_minutes_since_strike"] = self._last_lightning_minutes
        if self._last_lightning_count_last_hour is not None:
            attrs["last_count_last_hour"] = self._last_lightning_count_last_hour

        return attrs or None

    @property
    def suggested_entity_id(self) -> str:
        """Return name."""
        return generate_entity_id("sensor.{}", self.entity_description.key)

    @property
    def icon(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Return the dynamic icon for battery representation."""

        if self.entity_description.key in BATTERY_LIST:
            if self.native_value:
                battery_level = battery_level_to_text(self.native_value)
                return battery_level_to_icon(battery_level)

            return battery_level_to_icon(UnitOfBat.UNKNOWN)

        return self.entity_description.icon

    @property
    def device_info(self) -> DeviceInfo:  # pyright: ignore[reportIncompatibleVariableOverride]
        """Device info."""
        return DeviceInfo(
            connections=set(),
            name="Weather Station",
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN,)},  # type: ignore[arg-type]
            manufacturer="PWS/WU / WS-Link",
            model="Weather Station",
        )
