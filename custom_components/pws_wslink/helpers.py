"""Utils for Weather Station."""

from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
import logging
import math
import re
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util

from .const import (
    AZIMUTH,
    CONNECTION_GATED_SENSORS,
    CONNECTION_KEYS,
    CREDENTIAL_FIELDS,
    DEV_DBG,
    DOMAIN,
    INVALID_CREDENTIALS,
    OUTSIDE_HUMIDITY,
    OUTSIDE_TEMP,
    REMAP_ITEMS_PWS,
    REMAP_ITEMS_WSLINK,
    SENSORS_TO_LOAD,
    VOC_LEVEL_MAP,
    WIND_SPEED,
    UnitOfDir,
    VOCLevel,
)

_LOGGER = logging.getLogger(__name__)
_CREDENTIAL_SEPARATORS = re.compile(r"[\s_-]+")


async def translations(
    hass: HomeAssistant,
    translation_domain: str,
    translation_key: str,
    category: str,
    *,
    key: str = "message",
) -> str:
    """Return one translated string, or an empty string when it is missing.

    `category` is the top-level section of strings.json holding the key, for
    instance "entity" or "exceptions".
    """
    return (
        await async_get_translations(
            hass, hass.config.language, category, [translation_domain]
        )
    ).get(f"component.{translation_domain}.{category}.{translation_key}.{key}", "")


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


def anonymize(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return the received payload without the station credentials."""
    return {key: value for key, value in data.items() if key not in CREDENTIAL_FIELDS}


def is_placeholder_credential(value: str) -> bool:
    """Return True when a credential is blank or a well-known placeholder label.

    Matching ignores case, surrounding blanks and the separator used between
    words, so "Station ID", "station-id" and " _STATION_ID_ " are all rejected.
    """
    normalized = _CREDENTIAL_SEPARATORS.sub("_", value.strip().upper()).strip("_")
    return not normalized or normalized in INVALID_CREDENTIALS


def signal_keys_changed(config_entry: ConfigEntry) -> str:
    """Return the dispatcher signal announcing a change in the active sensor keys."""
    return f"{DOMAIN}_keys_changed_{config_entry.entry_id}"


def ha_https_enabled(hass: HomeAssistant) -> bool:
    """Best-effort detection of HTTPS availability for HA."""
    internal = (hass.config.internal_url or "").lower()
    external = (hass.config.external_url or "").lower()

    if internal.startswith("https://") or external.startswith("https://"):
        return True

    return bool(getattr(hass.http, "ssl_certificate", None))


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


def remap_items_pws(entities: Mapping[str, Any]) -> dict[str, Any]:
    """Remap items in query."""
    items = {}
    for item in entities:
        if item in REMAP_ITEMS_PWS:
            items[REMAP_ITEMS_PWS[item]] = entities[item]

    return items


def _is_connected_flag(value: Any) -> bool | None:
    """Return True/False when parsable, None when unknown."""
    if value in (None, ""):
        return None
    try:
        return int(float(value)) == 1
    except TypeError, ValueError:
        return None


def remap_items_wslink(entities: Mapping[str, Any]) -> dict[str, Any]:
    """Remap items in query for WSLink API."""
    items = {}
    for item in entities:
        if item in REMAP_ITEMS_WSLINK:
            items[REMAP_ITEMS_WSLINK[item]] = entities[item]

    for conn_key, gated in CONNECTION_GATED_SENSORS.items():
        # connection keys are remapped in `items`
        connected = _is_connected_flag(items.get(conn_key))

        # Uniform behavior for all WSLink modules:
        # if cn is missing / empty / 0 -> remove all gated sensors
        if connected is True:
            continue

        for sensor_key in gated:
            items.pop(sensor_key, None)

    # Connection markers are internal-only: never expose them as discoverable sensors.
    for conn_key in CONNECTION_KEYS:
        items.pop(conn_key, None)

    return items


def loaded_sensors(config_entry: ConfigEntry) -> list[str]:
    """Return the sensor keys already loaded for this config entry."""
    return config_entry.options.get(SENSORS_TO_LOAD) or []


def check_disabled(items: Iterable[str], config_entry: ConfigEntry) -> list[str] | None:
    """Check if we have data for unloaded sensors.

    If so, then add sensor to load queue.

    Returns list of found sensors or None
    """

    log: bool = config_entry.options.get(DEV_DBG, False)
    entity_found: bool = False
    _loaded_sensors = loaded_sensors(config_entry)
    missing_sensors: list = []

    for item in items:
        # Never discover connection markers as entities.
        if item in CONNECTION_KEYS:
            continue

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

    if deg in (None, ""):
        return None
    return AZIMUTH[int(abs((float(deg) - 11.25) % 360) / 22.5)]


def heat_index(data: Mapping[str, Any]) -> float | None:
    """Return the NWS heat index computed from the outdoor temperature.

    Values are expected in Fahrenheit, as sent by PWS stations.
    """

    temp = data.get(OUTSIDE_TEMP, None)
    rh = data.get(OUTSIDE_HUMIDITY, None)

    if temp in (None, "") or rh in (None, ""):
        return None

    temp = float(temp)
    rh = float(rh)

    adjustment = None

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
        if rh < 13 and 80 <= temp <= 112:
            adjustment = ((13 - rh) / 4) * math.sqrt((17 - abs(temp - 95)) / 17)
        elif rh > 85 and 80 <= temp <= 87:
            adjustment = ((rh - 85) / 10) * ((87 - temp) / 5)

        return round(full_index + (adjustment or 0.0), 2)

    return round(simple, 2)


def chill_index(data: Mapping[str, Any]) -> float | None:
    """Return the NWS wind chill computed from temperature and wind speed.

    Values are expected in Fahrenheit and miles per hour, as sent by PWS stations.
    """

    temp = data.get(OUTSIDE_TEMP, None)
    wind = data.get(WIND_SPEED, None)

    if temp in (None, "") or wind in (None, ""):
        return None

    temp = float(temp)
    wind = float(wind)

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
    return VOC_LEVEL_MAP.get(int(float(value)))


def battery_5step_to_pct(value: str) -> int | None:
    """Convert 0-5 battery steps to percentage."""

    if value in (None, ""):
        return None

    return round(int(float(value)) / 5 * 100)
