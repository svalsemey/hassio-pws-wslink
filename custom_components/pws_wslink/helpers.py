"""Utils for Weather Station."""

from datetime import datetime, timedelta
import logging
import math
from pathlib import Path
import sqlite3
from typing import Any

import numpy as np

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util

from .const import (
    AZIMUTH,
    CONNECTION_GATED_SENSORS,
    DATABASE_PATH,
    DEV_DBG,
    OUTSIDE_HUMIDITY,
    OUTSIDE_TEMP,
    REMAP_ITEMS,
    REMAP_WSLINK_ITEMS,
    SENSORS_TO_LOAD,
    VOC_LEVEL_MAP,
    WIND_SPEED,
    UnitOfBat,
    UnitOfDir,
    VOCLevel,
)

_LOGGER = logging.getLogger(__name__)


async def translations(
    hass: HomeAssistant,
    translation_domain: str,
    translation_key: str,
    *,
    key: str = "message",
    category: str = "notify",
) -> str:
    """Get translated keys for domain."""

    localize_key = f"component.{translation_domain}.{category}.{translation_key}.{key}"

    language = hass.config.language

    _translations = await async_get_translations(
        hass, language, category, [translation_domain]
    )
    if localize_key in _translations:
        return _translations[localize_key]
    return ""


async def translated_notification(
    hass: HomeAssistant,
    translation_domain: str,
    translation_key: str,
    translation_placeholders: dict[str, str] | None = None,
    notification_id: str | None = None,
    *,
    key: str = "message",
    category: str = "exceptions",
):
    """Create a translated persistent notification (Hassfest-safe).

    This helper does not use the non-supported "notify" section in strings.json.
    It expects translation keys in:
      component.<domain>.<category>.<translation_key>.message
      component.<domain>.<category>.<translation_key>_title.message
    """

    language = hass.config.language
    _translations = await async_get_translations(
        hass, language, category, [translation_domain]
    )

    # Message key (required)
    message_key = f"component.{translation_domain}.{category}.{translation_key}.{key}"

    # Title key (optional convention: <translation_key>_title.message)
    title_key = (
        f"component.{translation_domain}.{category}.{translation_key}_title.message"
    )

    message_template = _translations.get(message_key)
    if not message_template:
        return

    title = _translations.get(title_key, translation_domain)

    if translation_placeholders:
        try:
            message = message_template.format(**translation_placeholders)
        except KeyError:
            # Fallback if placeholders are incomplete
            message = message_template
    else:
        message = message_template

    persistent_notification.async_create(
        hass,
        message,
        title,
        notification_id,
    )


async def update_options(
    hass: HomeAssistant, entry: ConfigEntry, update_key, update_value
) -> bool:
    """Update config.options entry."""
    conf = {**entry.options}
    conf[update_key] = update_value

    return hass.config_entries.async_update_entry(entry, options=conf)


def anonymize(data):
    """Anoynimize received data."""

    anonym = {}
    for k in data:
        if k not in {"ID", "PASSWORD", "wsid", "wspw"}:
            anonym[k] = data[k]

    return anonym


def ha_https_enabled(self) -> bool:
    """Best-effort detection of HTTPS availability for HA."""
    internal = (self.hass.config.internal_url or "").lower()
    external = (self.hass.config.external_url or "").lower()

    if internal.startswith("https://") or external.startswith("https://"):
        return True

    return bool(getattr(self.hass.http, "ssl_certificate", None))


def minutes_since_to_timestamp(value: str | float | None) -> datetime | None:
    """Convert minutes since last event to UTC timestamp rounded to minute.

    Input is expected to be the number of minutes since the last lightning strike.
    Returns timezone-aware UTC datetime with seconds and microseconds set to zero.
    """

    if value in (None, ""):
        return None

    try:
        minutes = int(float(value))
    except TypeError, ValueError:
        return None

    if minutes < 0:
        return None

    timestamp = dt_util.utcnow() - timedelta(minutes=minutes)
    return timestamp.replace(second=0, microsecond=0)


def remap_items(entities):
    """Remap items in query."""
    items = {}
    for item in entities:
        if item in REMAP_ITEMS:
            items[REMAP_ITEMS[item]] = entities[item]

    return items


def remap_wslink_items(entities):
    """Remap items in query for WSLink API."""
    items = {}
    for item in entities:
        if item in REMAP_WSLINK_ITEMS:
            items[REMAP_WSLINK_ITEMS[item]] = entities[item]

    for conn_key, gated in CONNECTION_GATED_SENSORS.items():
        if str(entities.get(conn_key, "0")) != "1":
            for key in gated:
                items.pop(key, None)

    return items


def loaded_sensors(config_entry: ConfigEntry) -> list | None:
    """Get loaded sensors."""

    return config_entry.options.get(SENSORS_TO_LOAD) or []


def check_disabled(
    hass: HomeAssistant, items, config_entry: ConfigEntry
) -> list | None:
    """Check if we have data for unloaded sensors.

    If so, then add sensor to load queue.

    Returns list of found sensors or None
    """

    log: bool = config_entry.options.get(DEV_DBG, False)
    entity_found: bool = False
    _loaded_sensors = loaded_sensors(config_entry)
    missing_sensors: list = []

    for item in items:
        if log:
            _LOGGER.info("Checking %s", item)

        if item not in _loaded_sensors:
            missing_sensors.append(item)
            entity_found = True
            if log:
                _LOGGER.info("Add sensor (%s) to loading queue", item)

    return missing_sensors if entity_found else None


def wind_dir_to_text(deg: float) -> UnitOfDir | None:
    """Return wind direction in text representation.

    Returns UnitOfDir or None
    """

    if deg:
        return AZIMUTH[int(abs((float(deg) - 11.25) % 360) / 22.5)]

    return None


def battery_level_to_text(battery: int) -> UnitOfBat:
    """Return battery level in text representation.

    Returns UnitOfBat
    """

    level_map: dict[int, UnitOfBat] = {
        0: UnitOfBat.LOW,
        1: UnitOfBat.NORMAL,
    }

    if battery is None:
        return UnitOfBat.UNKNOWN

    return level_map.get(int(battery), UnitOfBat.UNKNOWN)


def battery_level_to_icon(battery: UnitOfBat) -> str:
    """Return battery level in icon representation.

    Returns str
    """

    icons = {
        UnitOfBat.LOW: "mdi:battery-low",
        UnitOfBat.NORMAL: "mdi:battery",
    }

    return icons.get(battery, "mdi:battery-unknown")


def fahrenheit_to_celsius(fahrenheit: float) -> float:
    """Convert Fahrenheit to Celsius."""
    return (fahrenheit - 32) * 5.0 / 9.0


def celsius_to_fahrenheit(celsius: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return celsius * 9.0 / 5.0 + 32


def heat_index(data: Any, convert: bool = False) -> float | None:
    """Calculate heat index from temperature.

    data: dict with temperature and humidity
    convert: bool, convert received data from Celsius to Fahrenheit
    """

    temp = data.get(OUTSIDE_TEMP, None)
    rh = data.get(OUTSIDE_HUMIDITY, None)

    if not temp or not rh:
        return None

    temp = float(temp)
    rh = float(rh)

    adjustment = None

    if convert:
        temp = celsius_to_fahrenheit(temp)

    simple = 0.5 * (temp + 61.0 + ((temp - 68.0) * 1.2) + (rh * 0.094))
    if ((simple + temp) / 2) > 80:
        full_index = (
            -42.379
            + 2.04901523 * temp
            + 10.14333127 * rh
            - 0.22475541 * temp * rh
            - 0.00683783 * temp * temp
            - 0.05481717 * rh * rh
            + 0.00122874 * temp * temp * rh
            + 0.00085282 * temp * rh * rh
            - 0.00000199 * temp * temp * rh * rh
        )
        if rh < 13 and (temp in np.arange(80, 112, 0.1)):
            adjustment = ((13 - rh) / 4) * math.sqrt((17 - abs(temp - 95)) / 17)

        if rh > 80 and (temp in np.arange(80, 87, 0.1)):
            adjustment = ((rh - 85) / 10) * ((87 - temp) / 5)

        return round((full_index + adjustment if adjustment else full_index), 2)

    return simple


def chill_index(data: Any, convert: bool = False) -> float | None:
    """Calculate wind chill index from temperature and wind speed.

    data: dict with temperature and wind speed
    convert: bool, convert received data from Celsius to Fahrenheit
    """

    temp = data.get(OUTSIDE_TEMP, None)
    wind = data.get(WIND_SPEED, None)

    if not temp or not wind:
        return None

    temp = float(temp)
    wind = float(wind)

    if convert:
        temp = celsius_to_fahrenheit(temp)

    return (
        round(
            (
                (35.7 + (0.6215 * temp))
                - (35.75 * (wind**0.16))
                + (0.4275 * (temp * (wind**0.16)))
            ),
            2,
        )
        if temp < 50 and wind > 3
        else temp
    )


def voc_level_to_text(value: str) -> VOCLevel | None:
    """Map 1-5 VOC level to text state."""
    if value in (None, ""):
        return None
    return VOC_LEVEL_MAP.get(int(value))


def battery_5step_to_pct(value: str) -> int | None:
    """Convert 0-5 battery steps to percentage."""

    if value in (None, ""):
        return None

    return round(int(value) / 5 * 100)


def long_term_units_in_statistics_meta():
    """Get units in long term statitstics."""
    sensor_units = []
    if not Path(DATABASE_PATH).exists():
        _LOGGER.error("Database file not found: %s", DATABASE_PATH)
        return False

    conn = sqlite3.connect(DATABASE_PATH)
    db = conn.cursor()

    try:
        db.execute(
            """
            SELECT statistic_id, unit_of_measurement from statistics_meta
            WHERE statistic_id LIKE 'sensor.weather_station_%'
            """
        )
        rows = db.fetchall()
        sensor_units = {
            statistic_id: f"{statistic_id} ({unit})" for statistic_id, unit in rows
        }

    except sqlite3.Error as e:
        _LOGGER.error("Error during data migration: %s", e)
    finally:
        conn.close()

    return sensor_units


async def migrate_data(hass: HomeAssistant, sensor_id: str | None = None) -> int | bool:
    """Migrate data from mm/d to mm."""

    _LOGGER.debug("Sensor %s is required for data migration", sensor_id)
    updated_rows = 0

    if not Path(DATABASE_PATH).exists():
        _LOGGER.error("Database file not found: %s", DATABASE_PATH)
        return False

    conn = sqlite3.connect(DATABASE_PATH)
    db = conn.cursor()

    try:
        _LOGGER.info(sensor_id)
        db.execute(
            """
            UPDATE statistics_meta
            SET unit_of_measurement = 'mm'
            WHERE statistic_id = ?
            AND unit_of_measurement = 'mm/d';
            """,
            (sensor_id,),
        )
        updated_rows = db.rowcount
        conn.commit()
        _LOGGER.info(
            "Data migration completed successfully. Updated rows: %s for %s",
            updated_rows,
            sensor_id,
        )

    except sqlite3.Error as e:
        _LOGGER.error("Error during data migration: %s", e)
    finally:
        conn.close()
    return updated_rows


def migrate_data_old(sensor_id: str | None = None):
    """Migrate data from mm/d to mm."""
    updated_rows = 0

    if not Path(DATABASE_PATH).exists():
        _LOGGER.error("Database file not found: %s", DATABASE_PATH)
        return False

    conn = sqlite3.connect(DATABASE_PATH)
    db = conn.cursor()

    try:
        _LOGGER.info(sensor_id)
        db.execute(
            """
            UPDATE statistics_meta
            SET unit_of_measurement = 'mm'
            WHERE statistic_id = ?
            AND unit_of_measurement = 'mm/d';
            """,
            (sensor_id,),
        )
        updated_rows = db.rowcount
        conn.commit()
        _LOGGER.info(
            "Data migration completed successfully. Updated rows: %s for %s",
            updated_rows,
            sensor_id,
        )

    except sqlite3.Error as e:
        _LOGGER.error("Error during data migration: %s", e)
    finally:
        conn.close()
    return updated_rows
