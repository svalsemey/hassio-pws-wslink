"""Sensors definition for Weather Station."""

from datetime import datetime

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
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
    LIGHTNING_STRIKE_COUNT_DURING_1_DAY,
    LIGHTNING_STRIKE_COUNT_DURING_1_HOUR,
    LIGHTNING_STRIKE_COUNT_DURING_5_MINUTES,
    LIGHTNING_STRIKE_COUNT_DURING_30_MINUTES,
    LIGHTNING_STRIKE_COUNT_LAST_HOUR,
    LIGHTNING_STRIKE_TIME,
    OUTSIDE_HUMIDITY,
    OUTSIDE_TEMP,
    T6_WATER_LEAK_KEYS,
    T234_TEMP_KEYS,
    WIND_AZIMUTH,
    WIND_DIR,
    WIND_SPEED,
)
from .device_map import active_sensor_keys, device_info_for_key, module_for_key
from .helpers import chill_index, heat_index, minutes_since_to_timestamp
from .sensors_common import WeatherSensorEntityDescription
from .sensors_pws import SENSOR_TYPES_PWS
from .sensors_wslink import SENSOR_TYPES_WSLINK


class ChannelDiagnosticSensor(SensorEntity):
    """Static diagnostic sensor exposing channel number for channel-based modules."""

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
        device_key: str,
    ) -> None:
        """Initialize diagnostic channel sensor."""
        self._config_entry = config_entry
        self._module = module
        self._device_key = device_key
        self._attr_unique_id = f"{module}_channel_number"
        self._attr_native_value = channel

    @property
    def device_info(self):
        """Attach diagnostic sensor to the corresponding module device."""
        return device_info_for_key(self._config_entry, self._device_key)


def _channel_diagnostic_entities(
    config_entry: ConfigEntry,
    loaded_keys: list[str],
) -> list[ChannelDiagnosticSensor]:
    """Build one diagnostic 'channel number' sensor per channel-based device."""
    modules: dict[str, tuple[int, str]] = {}

    for key in loaded_keys:
        module = module_for_key(key)

        if module.startswith("t234c"):
            ch_txt = module[5:]
            if ch_txt.isdigit():
                ch = int(ch_txt)
                if 1 <= ch <= 7:
                    modules.setdefault(module, (ch, T234_TEMP_KEYS[ch - 1]))
            continue

        if module.startswith("t6c"):
            ch_txt = module[3:]
            if ch_txt.isdigit():
                ch = int(ch_txt)
                if 1 <= ch <= 7:
                    modules.setdefault(module, (ch, T6_WATER_LEAK_KEYS[ch - 1]))

    return [
        ChannelDiagnosticSensor(config_entry, module, channel, device_key)
        for module, (channel, device_key) in sorted(
            modules.items(), key=lambda item: item[1][0]
        )
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Weather Station sensors."""
    coordinator: WeatherDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    is_wslink = config_entry.options.get(API_MODE) == API_MODE_WSLINK
    loaded_keys = active_sensor_keys(config_entry)

    # Derived sensors are computed locally and never pushed by the station.
    requested = set(loaded_keys)
    if WIND_DIR in requested:
        requested.add(WIND_AZIMUTH)
    if not is_wslink:
        if {OUTSIDE_TEMP, OUTSIDE_HUMIDITY} <= requested:
            requested.add(HEAT_INDEX)
        if {OUTSIDE_TEMP, WIND_SPEED} <= requested:
            requested.add(CHILL_INDEX)

    async_add_entities(
        [
            *(
                WeatherSensor(description, coordinator)
                for description in (
                    SENSOR_TYPES_WSLINK if is_wslink else SENSOR_TYPES_PWS
                )
                if description.key in requested
                and not (is_wslink and description.key in BATTERY_LIST)
            ),
            *_channel_diagnostic_entities(config_entry, loaded_keys),
        ]
    )


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

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if (data := self.coordinator.data) is not None:
            self._data = data.get(self.entity_description.key)
            self._has_seen_payload = True
        super()._handle_coordinator_update()

    @staticmethod
    def _to_int(value) -> int | None:
        """Convert value to int safely."""
        if value in (None, ""):
            return None
        try:
            return int(float(value))
        except TypeError, ValueError:
            return None

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

    def _stable_lightning_last_strike(self) -> datetime | None:
        """Return stable lightning last-strike timestamp.

        Strict rule:
        - On fresh install (no stored timestamp), keep unknown while all strike counters are 0.
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

        # Fresh install behavior:
        # no known last strike yet + no strike counters > 0 => unknown
        if self._last_lightning_ts is None and not self._has_any_lightning_strike():
            self._last_lightning_minutes = minutes_now
            self._last_lightning_count_last_hour = count_now
            return None

        # No usable current value -> keep last coherent one
        if minutes_now is None:
            return self._last_lightning_ts

        candidate_ts = minutes_since_to_timestamp(minutes_now)
        if candidate_ts is None:
            return self._last_lightning_ts

        # First coherent sample (after first detected strike or restored state)
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

    def _has_any_lightning_strike(self) -> bool:
        """Return True if at least one lightning counter is > 0."""
        data = self.coordinator.data or {}
        return any(
            (value := self._to_int(data.get(key))) is not None and value > 0
            for key in (
                LIGHTNING_STRIKE_COUNT_LAST_HOUR,
                LIGHTNING_STRIKE_COUNT_DURING_5_MINUTES,
                LIGHTNING_STRIKE_COUNT_DURING_30_MINUTES,
                LIGHTNING_STRIKE_COUNT_DURING_1_HOUR,
                LIGHTNING_STRIKE_COUNT_DURING_1_DAY,
            )
        )

    @property
    def native_value(self) -> StateType | datetime:
        """Return the current value of the entity."""
        if not self.available:
            return None

        key = self.entity_description.key
        if key == LIGHTNING_STRIKE_TIME:
            return self._stable_lightning_last_strike()
        if key == LIGHTNING_DISTANCE:
            return self._stable_lightning_distance()

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
    def extra_state_attributes(self) -> dict[str, int] | None:
        """Expose the comparators used to restore the lightning state."""
        if self.entity_description.key not in (
            LIGHTNING_STRIKE_TIME,
            LIGHTNING_DISTANCE,
        ):
            return None

        attrs: dict[str, int] = {}
        if self._last_lightning_minutes is not None:
            attrs["last_minutes_since_strike"] = self._last_lightning_minutes
        if self._last_lightning_count_last_hour is not None:
            attrs["last_count_last_hour"] = self._last_lightning_count_last_hour
        return attrs or None

    @property
    def device_info(self):
        """Attach entity to hub or corresponding module device."""
        return device_info_for_key(
            self.coordinator.config_entry, self.entity_description.key
        )
