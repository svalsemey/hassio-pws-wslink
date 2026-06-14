"""Constants."""

from enum import StrEnum
from typing import Final

DOMAIN = "pws_wslink"
MANUFACTURER = "PWS / WSLink"
URI_API_PWS = "/weatherstation/updateweatherstation.php"
URI_API_WSLINK = "/data/upload.php"
URL_WSLINK_ADDON: Final = "https://github.com/schizza/wslink-addon"
DATABASE_PATH = "/config/home-assistant_v2.db"

ICON = "mdi:weather"

API_ID = "API_ID"
API_KEY = "API_KEY"

SENSORS_TO_LOAD: Final = "sensors_to_load"
SENSOR_TO_MIGRATE: Final = "sensor_to_migrate"

API_MODE: Final = "api_mode"
API_MODE_PWS: Final = "pws"
API_MODE_WSLINK: Final = "wslink"

DEV_DBG: Final = "dev_debug_checkbox"

INVALID_CREDENTIALS: Final = [
    "API",
    "API_ID",
    "API ID",
    "_ID",
    "ID",
    "API KEY",
    "API_KEY",
    "KEY",
    "_KEY",
]


BARO_PRESSURE: Final = "baro_pressure"
BATTERY: Final = "battery"
DEW_POINT: Final = "dew_point"
HUMIDITY: Final = "humidity"
INDOOR_TEMP: Final = "indoor_temp"
INDOOR_HUMIDITY: Final = "indoor_humidity"
INDOOR_BATTERY: Final = "indoor_battery"
OUTSIDE_TEMP: Final = "outside_temp"
OUTSIDE_HUMIDITY: Final = "outside_humidity"
OUTSIDE_CONNECTION: Final = "outsideconnection"
OUTSIDE_BATTERY: Final = "outside_battery"
TEMPERATURE: Final = "temperature"
WIND_SPEED: Final = "wind_speed"
WIND_GUST: Final = "wind_gust"
WIND_DIR: Final = "wind_dir"
WIND_AZIMUTH: Final = "wind_azimuth"
RAIN_RATE: Final = "rain_rate"
RAINFALL_HOURLY: Final = "rainfall_hourly"
RAINFALL_WEEKLY: Final = "rainfall_weekly"
RAINFALL_MONTHLY: Final = "rainfall_monthly"
RAINFALL_YEARLY: Final = "rainfall_yearly"
RAINFALL_DAILY: Final = "rainfall_daily"
SOLAR_RADIATION: Final = "solar_radiation"
UV: Final = "uv"
HEAT_INDEX: Final = "heat_index"
FEELS_LIKE: Final = "feels_like"
CHILL_INDEX: Final = "chill_index"
WBGT_TEMP: Final = "wbgt_temp"

# Type2/3/4 channels
T234_TEMP_KEYS: list[str] = [f"ch{i}_temp" for i in range(1, 8)]
T234_HUMIDITY_KEYS: list[str] = [f"ch{i}_humidity" for i in range(1, 8)]
T234_BATTERY_KEYS: list[str] = [f"ch{i}_battery" for i in range(1, 8)]
T234_CONNECTION_KEYS: list[str] = [f"ch{i}connection" for i in range(1, 8)]


# T5 sensors are lightning related
T5_BATTERY: Final = "t5_battery"
T5_CONNECTION: Final = "t5connection"
LIGHTNING_STRIKE_TIME: Final = "lightning_last_strike_time"
LIGHTNING_DISTANCE: Final = "lightning_distance"
LIGHTNING_STRIKE_COUNT_LAST_HOUR: Final = "lightning_strike_count_last_hour"
LIGHTNING_STRIKE_COUNT_DURING_5_MINUTES: Final = (
    "lightning_strike_count_during_5_minutes"
)
LIGHTNING_STRIKE_COUNT_DURING_30_MINUTES: Final = (
    "lightning_strike_count_during_30_minutes"
)
LIGHTNING_STRIKE_COUNT_DURING_1_HOUR: Final = "lightning_strike_count_during_1_hour"
LIGHTNING_STRIKE_COUNT_DURING_1_DAY: Final = "lightning_strike_count_during_1_day"

# Type6 (water leak channels 1..7)
T6_WATER_LEAK_KEYS: list[str] = [f"t6_c{i}_water_leak" for i in range(1, 8)]
T6_BATTERY_KEYS: list[str] = [f"t6_c{i}_battery" for i in range(1, 8)]
T6_CONNECTION_KEYS: list[str] = [f"t6c{i}connection" for i in range(1, 8)]

# Type 8 (PM2.5/PM10)
T8_BATTERY: Final = "t8_battery"
T8_CONNECTION: Final = "t8connection"
PM25: Final = "pm25"
PM10: Final = "pm10"
PM25_AQI: Final = "pm25_aqi"
PM10_AQI: Final = "pm10_aqi"

# Type 9 (HCHO/VOC)
T9_BATTERY: Final = "t9_battery"
T9_CONNECTION: Final = "t9connection"
HCHO: Final = "hcho"
VOC: Final = "voc"

# Type 10 (CO₂)
T10_BATTERY: Final = "t10_battery"
T10_CONNECTION: Final = "t10connection"
CO2: Final = "co2"

WATER_LEAK: Final = "water_leak"

# Type11 (CO)
T11_BATTERY: Final = "t11_battery"
T11_CONNECTION: Final = "t11connection"
CO: Final = "co"

CONNECTION_KEYS: Final[list[str]] = [
    OUTSIDE_CONNECTION,
    *T234_CONNECTION_KEYS,
    T5_CONNECTION,
    *T6_CONNECTION_KEYS,
    T8_CONNECTION,
    T9_CONNECTION,
    T10_CONNECTION,
    T11_CONNECTION,
]

WATER_LEAK_LIST: list[str] = T6_WATER_LEAK_KEYS

REMAP_ITEMS_PWS: dict[str, str] = {
    "baromin": BARO_PRESSURE,
    "tempf": OUTSIDE_TEMP,
    "dewptf": DEW_POINT,
    "humidity": OUTSIDE_HUMIDITY,
    "windspeedmph": WIND_SPEED,
    "windgustmph": WIND_GUST,
    "winddir": WIND_DIR,
    "rainin": RAIN_RATE,
    "dailyrainin": RAINFALL_DAILY,
    "solarradiation": SOLAR_RADIATION,
    "indoortempf": INDOOR_TEMP,
    "indoorhumidity": INDOOR_HUMIDITY,
    "UV": UV,
    **{
        key: T234_TEMP_KEYS[i]
        for i, key in enumerate(["soiltempf", *[f"soiltemp{n}f" for n in range(2, 8)]])
    },
    **{
        key: T234_HUMIDITY_KEYS[i]
        for i, key in enumerate(
            ["soilmoisture", *[f"soilmoisture{n}" for n in range(2, 8)]]
        )
    },
}

REMAP_ITEMS_WSLINK: dict[str, str] = {
    "intem": INDOOR_TEMP,
    "inhum": INDOOR_HUMIDITY,
    "inbat": INDOOR_BATTERY,
    "rbar": BARO_PRESSURE,
    "t1tem": OUTSIDE_TEMP,
    "t1hum": OUTSIDE_HUMIDITY,
    "t1wbgt": WBGT_TEMP,
    "t1dew": DEW_POINT,
    "t1wdir": WIND_DIR,
    "t1ws": WIND_SPEED,
    "t1wgust": WIND_GUST,
    "t1rainra": RAIN_RATE,
    "t1raindy": RAINFALL_DAILY,
    "t1solrad": SOLAR_RADIATION,
    "t1feels": FEELS_LIKE,
    "t1chill": CHILL_INDEX,
    "t1uvi": UV,
    "t1heat": HEAT_INDEX,
    "t1rainhr": RAINFALL_HOURLY,
    "t1rainwy": RAINFALL_WEEKLY,
    "t1rainmth": RAINFALL_MONTHLY,
    "t1rainyr": RAINFALL_YEARLY,
    "t1bat": OUTSIDE_BATTERY,
    "t1cn": OUTSIDE_CONNECTION,
    **{f"t234c{i + 1}tem": T234_TEMP_KEYS[i] for i in range(7)},
    **{f"t234c{i + 1}hum": T234_HUMIDITY_KEYS[i] for i in range(7)},
    **{f"t234c{i + 1}bat": T234_BATTERY_KEYS[i] for i in range(7)},
    **{f"t234c{i + 1}cn": T234_CONNECTION_KEYS[i] for i in range(7)},
    "t5lst": LIGHTNING_STRIKE_TIME,
    "t5lskm": LIGHTNING_DISTANCE,
    "t5lsf": LIGHTNING_STRIKE_COUNT_LAST_HOUR,
    "t5ls5mtc": LIGHTNING_STRIKE_COUNT_DURING_5_MINUTES,
    "t5ls30mtc": LIGHTNING_STRIKE_COUNT_DURING_30_MINUTES,
    "t5ls1htc": LIGHTNING_STRIKE_COUNT_DURING_1_HOUR,
    "t5ls1dtc": LIGHTNING_STRIKE_COUNT_DURING_1_DAY,
    "t5lsbat": T5_BATTERY,
    "t5lscn": T5_CONNECTION,
    **{f"t6c{i + 1}wls": T6_WATER_LEAK_KEYS[i] for i in range(7)},
    **{f"t6c{i + 1}bat": T6_BATTERY_KEYS[i] for i in range(7)},
    **{f"t6c{i + 1}cn": T6_CONNECTION_KEYS[i] for i in range(7)},
    "t8pm25": PM25,
    "t8pm10": PM10,
    "t8pm25ai": PM25_AQI,
    "t8pm10ai": PM10_AQI,
    "t8bat": T8_BATTERY,
    "t8cn": T8_CONNECTION,
    "t9hcho": HCHO,
    "t9voclv": VOC,
    "t9bat": T9_BATTERY,  # T9 battery is 0-5, where 5 is full
    "t9cn": T9_CONNECTION,
    "t10co2": CO2,
    "t10bat": T10_BATTERY,  # T10 battery is 0-5, where 5 is full
    "t10cn": T10_CONNECTION,
    "t11co": CO,
    "t11bat": T11_BATTERY,
    "t11cn": T11_CONNECTION,
}

DISABLED_BY_DEFAULT: Final = [
    OUTSIDE_BATTERY,
    WBGT_TEMP,
    *T234_TEMP_KEYS,
    *T234_HUMIDITY_KEYS,
    *T234_BATTERY_KEYS,
    LIGHTNING_STRIKE_TIME,
    LIGHTNING_DISTANCE,
    LIGHTNING_STRIKE_COUNT_LAST_HOUR,
    LIGHTNING_STRIKE_COUNT_DURING_5_MINUTES,
    LIGHTNING_STRIKE_COUNT_DURING_30_MINUTES,
    LIGHTNING_STRIKE_COUNT_DURING_1_HOUR,
    LIGHTNING_STRIKE_COUNT_DURING_1_DAY,
    T5_BATTERY,
    *T6_WATER_LEAK_KEYS,
    *T6_BATTERY_KEYS,
    PM25,
    PM10,
    PM25_AQI,
    PM10_AQI,
    T8_BATTERY,
    HCHO,
    VOC,
    T9_BATTERY,
    CO2,
    T10_BATTERY,
    CO,
    T11_BATTERY,
]

BATTERY_LIST = [
    OUTSIDE_BATTERY,
    INDOOR_BATTERY,
    *T234_BATTERY_KEYS,
    T5_BATTERY,
    *T6_BATTERY_KEYS,
]

BATTERY_NON_BINARY: list[str] = [T8_BATTERY, T9_BATTERY, T10_BATTERY, T11_BATTERY]

CONNECTION_GATED_SENSORS: Final[dict[str, list[str]]] = {
    # Type1 (outdoor module)
    OUTSIDE_CONNECTION: [
        OUTSIDE_TEMP,
        OUTSIDE_HUMIDITY,
        FEELS_LIKE,
        CHILL_INDEX,
        HEAT_INDEX,
        DEW_POINT,
        WIND_DIR,
        WIND_SPEED,
        WIND_GUST,
        RAIN_RATE,
        RAINFALL_HOURLY,
        RAINFALL_DAILY,
        RAINFALL_WEEKLY,
        RAINFALL_MONTHLY,
        RAINFALL_YEARLY,
        UV,
        SOLAR_RADIATION,
        WBGT_TEMP,
        OUTSIDE_BATTERY,
    ],
    # Type2/3/4 channels
    **{
        T234_CONNECTION_KEYS[i]: [
            T234_TEMP_KEYS[i],
            T234_HUMIDITY_KEYS[i],
            T234_BATTERY_KEYS[i],
        ]
        for i in range(7)
    },
    # Type5 lightning
    T5_CONNECTION: [
        LIGHTNING_STRIKE_TIME,
        LIGHTNING_DISTANCE,
        LIGHTNING_STRIKE_COUNT_LAST_HOUR,
        LIGHTNING_STRIKE_COUNT_DURING_5_MINUTES,
        LIGHTNING_STRIKE_COUNT_DURING_30_MINUTES,
        LIGHTNING_STRIKE_COUNT_DURING_1_HOUR,
        LIGHTNING_STRIKE_COUNT_DURING_1_DAY,
        T5_BATTERY,
    ],
    # Type6 channels
    **{
        T6_CONNECTION_KEYS[i]: [T6_WATER_LEAK_KEYS[i], T6_BATTERY_KEYS[i]]
        for i in range(7)
    },
    # Type8 / Type9 / Type10 / Type11
    T8_CONNECTION: [PM25, PM10, PM25_AQI, PM10_AQI, T8_BATTERY],
    T9_CONNECTION: [HCHO, VOC, T9_BATTERY],
    T10_CONNECTION: [CO2, T10_BATTERY],
    T11_CONNECTION: [CO, T11_BATTERY],
}


class VOCLevel(StrEnum):
    """WSLink VOC Level 1-5 (1-worst)."""

    UNHEALTHY = "unhealthy"
    POOR = "poor"
    MODERATE = "moderate"
    GOOD = "good"
    EXCELLENT = "excellent"


VOC_LEVEL_MAP: dict[int, VOCLevel] = {
    1: VOCLevel.UNHEALTHY,
    2: VOCLevel.POOR,
    3: VOCLevel.MODERATE,
    4: VOCLevel.GOOD,
    5: VOCLevel.EXCELLENT,
}


class UnitOfDir(StrEnum):
    """Wind direction azimuth."""

    NNE = "nne"
    NE = "ne"
    ENE = "ene"
    E = "e"
    ESE = "ese"
    SE = "se"
    SSE = "sse"
    S = "s"
    SSW = "ssw"
    SW = "sw"
    WSW = "wsw"
    W = "w"
    WNW = "wnw"
    NW = "nw"
    NNW = "nnw"
    N = "n"


AZIMUTH: list[UnitOfDir] = [
    UnitOfDir.NNE,
    UnitOfDir.NE,
    UnitOfDir.ENE,
    UnitOfDir.E,
    UnitOfDir.ESE,
    UnitOfDir.SE,
    UnitOfDir.SSE,
    UnitOfDir.S,
    UnitOfDir.SSW,
    UnitOfDir.SW,
    UnitOfDir.WSW,
    UnitOfDir.W,
    UnitOfDir.WNW,
    UnitOfDir.NW,
    UnitOfDir.NNW,
    UnitOfDir.N,
]


class UnitOfBat(StrEnum):
    """Battery level unit of measure."""

    LOW = "low"
    NORMAL = "normal"
    UNKNOWN = "unknown"


BATTERY_LEVEL: list[UnitOfBat] = [
    UnitOfBat.LOW,
    UnitOfBat.NORMAL,
    UnitOfBat.UNKNOWN,
]
