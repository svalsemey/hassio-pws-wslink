"""Shared building blocks for Weather Station sensor descriptions."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature

from .const import HUMIDITY, T234_HUMIDITY_KEYS, T234_TEMP_KEYS, TEMPERATURE


@dataclass(frozen=True, kw_only=True)
class WeatherSensorEntityDescription(SensorEntityDescription):
    """Describe Weather Sensor entities."""

    value_fn: Callable[[Any], int | float | str | datetime | None]


def temperature_description(
    key: str,
    unit: UnitOfTemperature,
    *,
    icon: str = "mdi:thermometer",
) -> WeatherSensorEntityDescription:
    """Build a temperature description for a value sent in the station unit."""
    return WeatherSensorEntityDescription(
        key=key,
        native_unit_of_measurement=unit,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        icon=icon,
        translation_key=TEMPERATURE,
        value_fn=lambda data: cast("float", data),
    )


def humidity_description(
    key: str,
    *,
    icon: str = "mdi:water-percent",
) -> WeatherSensorEntityDescription:
    """Build a relative humidity description."""
    return WeatherSensorEntityDescription(
        key=key,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.HUMIDITY,
        icon=icon,
        translation_key=HUMIDITY,
        value_fn=lambda data: cast("int", data),
    )


def channel_descriptions(
    unit: UnitOfTemperature,
) -> tuple[WeatherSensorEntityDescription, ...]:
    """Build the temperature and humidity descriptions of Type2/3/4 channels."""
    return tuple(
        description
        for temp_key, humidity_key in zip(
            T234_TEMP_KEYS, T234_HUMIDITY_KEYS, strict=True
        )
        for description in (
            temperature_description(temp_key, unit),
            humidity_description(humidity_key),
        )
    )
