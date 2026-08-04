"""Map weather station modules to Home Assistant devices."""

import re
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import (
    BARO_PRESSURE,
    CO,
    CO2,
    DOMAIN,
    HCHO,
    INDOOR_BATTERY,
    INDOOR_HUMIDITY,
    INDOOR_TEMP,
    LIGHTNING_DISTANCE,
    LIGHTNING_STRIKE_COUNT_DURING_1_DAY,
    LIGHTNING_STRIKE_COUNT_DURING_1_HOUR,
    LIGHTNING_STRIKE_COUNT_DURING_5_MINUTES,
    LIGHTNING_STRIKE_COUNT_DURING_30_MINUTES,
    LIGHTNING_STRIKE_COUNT_LAST_HOUR,
    LIGHTNING_STRIKE_TIME,
    MANUFACTURER,
    PM10,
    PM10_AQI,
    PM25,
    PM25_AQI,
    T5_BATTERY,
    T8_BATTERY,
    T9_BATTERY,
    T10_BATTERY,
    T11_BATTERY,
    VOC,
)

_TYPE234_CHANNEL_RE = re.compile(r"^ch([1-7])_")
_TYPE5_KEYS = {
    LIGHTNING_STRIKE_TIME,
    LIGHTNING_DISTANCE,
    LIGHTNING_STRIKE_COUNT_LAST_HOUR,
    LIGHTNING_STRIKE_COUNT_DURING_5_MINUTES,
    LIGHTNING_STRIKE_COUNT_DURING_30_MINUTES,
    LIGHTNING_STRIKE_COUNT_DURING_1_HOUR,
    LIGHTNING_STRIKE_COUNT_DURING_1_DAY,
    T5_BATTERY,
}
_TYPE6_CHANNEL_RE = re.compile(r"^t6_c([1-7])_")
_TYPE8_KEYS = {PM25, PM10, PM25_AQI, PM10_AQI, T8_BATTERY}
_TYPE9_KEYS = {HCHO, VOC, T9_BATTERY}
_TYPE10_KEYS = {CO2, T10_BATTERY}
_TYPE11_KEYS = {CO, T11_BATTERY}
_HUB_KEYS = {INDOOR_TEMP, INDOOR_HUMIDITY, INDOOR_BATTERY, BARO_PRESSURE}


def module_for_key(key: str) -> str:
    """Return logical module id for a sensor/binary_sensor key."""
    if key in _HUB_KEYS:
        return "hub"
    t234_match = _TYPE234_CHANNEL_RE.match(key)
    if t234_match:
        return f"t234c{t234_match.group(1)}"
    if key in _TYPE5_KEYS:
        return "type5"
    t6_match = _TYPE6_CHANNEL_RE.match(key)
    if t6_match:
        return f"t6c{t6_match.group(1)}"
    if key in _TYPE8_KEYS:
        return "type8"
    if key in _TYPE9_KEYS:
        return "type9"
    if key in _TYPE10_KEYS:
        return "type10"
    if key in _TYPE11_KEYS:
        return "type11"
    return "type1"


# Fixed modules: module id -> (device model, strings.json translation key).
_MODULE_METADATA: Final[dict[str, tuple[str, str]]] = {
    "hub": ("Base station", "hub"),
    "type1": ("Type 1", "type1"),
    "type5": ("Type 5", "type5"),
    "type8": ("Type 8", "type8"),
    "type9": ("Type 9", "type9"),
    "type10": ("Type 10", "type10"),
    "type11": ("Type 11", "type11"),
}

# Channel modules: id prefix -> (device model, strings.json translation key).
_CHANNEL_METADATA: Final[tuple[tuple[str, str, str], ...]] = (
    ("t234c", "Type 2/3/4", "type234"),
    ("t6c", "Type 6", "type6"),
)


def module_metadata(module: str) -> tuple[str, str, dict[str, str] | None]:
    """Return the device model, translation key and placeholders of one module."""
    for prefix, model, translation_key in _CHANNEL_METADATA:
        if module.startswith(prefix):
            return model, translation_key, {"channel": module.removeprefix(prefix)}

    return (*_MODULE_METADATA.get(module, _MODULE_METADATA["type1"]), None)


def channel_of_module(module: str) -> int | None:
    """Return the channel number of a channel module, None for single modules."""
    for prefix, _model, _translation_key in _CHANNEL_METADATA:
        if module.startswith(prefix):
            return int(module.removeprefix(prefix))
    return None


def device_info_for_module(config_entry: ConfigEntry, module: str) -> DeviceInfo:
    """Build the DeviceInfo representing one station module."""
    model, translation_key, placeholders = module_metadata(module)
    hub_identifier = (DOMAIN, f"{config_entry.entry_id}_hub")

    if module == "hub":
        return DeviceInfo(
            identifiers={hub_identifier},
            manufacturer=MANUFACTURER,
            model=model,
            serial_number=config_entry.unique_id,
            entry_type=DeviceEntryType.SERVICE,
            translation_key=translation_key,
            translation_placeholders=placeholders,
        )

    return DeviceInfo(
        identifiers={(DOMAIN, f"{config_entry.entry_id}_{module}")},
        via_device=hub_identifier,
        manufacturer=MANUFACTURER,
        model=model,
        translation_key=translation_key,
        translation_placeholders=placeholders,
    )


def device_info_for_key(config_entry: ConfigEntry, key: str) -> DeviceInfo:
    """Build the DeviceInfo of the module owning one sensor key."""
    return device_info_for_module(config_entry, module_for_key(key))
