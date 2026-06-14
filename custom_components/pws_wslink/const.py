"""Constants."""

from enum import StrEnum
from typing import Final

DOMAIN = "pws_wslink"
DEFAULT_URL = "/weatherstation/updateweatherstation.php"
WSLINK_URL = "/data/upload.php"
WSLINK_ADDON_URL: Final = "https://github.com/schizza/wslink-addon"
DATABASE_PATH = "/config/home-assistant_v2.db"

ICON = "mdi:weather"

API_KEY = "API_KEY"
API_ID = "API_ID"

SENSORS_TO_LOAD: Final = "sensors_to_load"
SENSOR_TO_MIGRATE: Final = "sensor_to_migrate"

DEV_DBG: Final = "dev_debug_checkbox"
WSLINK: Final = "wslink"

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
OUTSIDE_TEMP: Final = "outside_temp"
DEW_POINT: Final = "dew_point"
OUTSIDE_HUMIDITY: Final = "outside_humidity"
OUTSIDE_CONNECTION: Final = "outside_connection"
OUTSIDE_BATTERY: Final = "outside_battery"
WIND_SPEED: Final = "wind_speed"
WIND_GUST: Final = "wind_gust"
WIND_DIR: Final = "wind_dir"
WIND_AZIMUTH: Final = "wind_azimuth"
RAIN: Final = "rain"
HOURLY_RAIN: Final = "hourly_rain"
WEEKLY_RAIN: Final = "weekly_rain"
MONTHLY_RAIN: Final = "monthly_rain"
YEARLY_RAIN: Final = "yearly_rain"
DAILY_RAIN: Final = "daily_rain"
SOLAR_RADIATION: Final = "solar_radiation"
INDOOR_TEMP: Final = "indoor_temp"
INDOOR_HUMIDITY: Final = "indoor_humidity"
INDOOR_BATTERY: Final = "indoor_battery"
UV: Final = "uv"
CH1_TEMP: Final = "ch1_temp"
CH1_HUMIDITY: Final = "ch1_humidity"
CH1_CONNECTION: Final = "ch1_connection"
CH1_BATTERY: Final = "ch1_battery"
CH2_TEMP: Final = "ch2_temp"
CH2_HUMIDITY: Final = "ch2_humidity"
CH2_CONNECTION: Final = "ch2_connection"
CH2_BATTERY: Final = "ch2_battery"
CH3_TEMP: Final = "ch3_temp"
CH3_HUMIDITY: Final = "ch3_humidity"
CH3_CONNECTION: Final = "ch3_connection"
CH3_BATTERY: Final = "ch3_battery"
CH4_TEMP: Final = "ch4_temp"
CH4_HUMIDITY: Final = "ch4_humidity"
CH4_CONNECTION: Final = "ch4_connection"
CH4_BATTERY: Final = "ch4_battery"
CH5_TEMP: Final = "ch5_temp"
CH5_HUMIDITY: Final = "ch5_humidity"
CH5_CONNECTION: Final = "ch5_connection"
CH5_BATTERY: Final = "ch5_battery"
CH6_TEMP: Final = "ch6_temp"
CH6_HUMIDITY: Final = "ch6_humidity"
CH6_CONNECTION: Final = "ch6_connection"
CH6_BATTERY: Final = "ch6_battery"
CH7_TEMP: Final = "ch7_temp"
CH7_HUMIDITY: Final = "ch7_humidity"
CH7_CONNECTION: Final = "ch7_connection"
CH7_BATTERY: Final = "ch7_battery"
HEAT_INDEX: Final = "heat_index"
FEELS_LIKE: Final = "feels_like"
CHILL_INDEX: Final = "chill_index"
WBGT_TEMP: Final = "wbgt_temp"
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
T5_BATTERY: Final = "t5_battery"
T5_CONN: Final = "t5_conn"
HCHO: Final = "hcho"
VOC: Final = "voc"
T9_BATTERY: Final = "t9_battery"  # T9 sensors are HCHO and VOC
T9_CONN: Final = "t9_conn"
CO2: Final = "co2"
T10_BATTERY: Final = "t10_battery"  # T10 sensors is CO²
T10_CONN: Final = "t10_conn"


REMAP_ITEMS: dict[str, str] = {
    "baromin": BARO_PRESSURE,
    "tempf": OUTSIDE_TEMP,
    "dewptf": DEW_POINT,
    "humidity": OUTSIDE_HUMIDITY,
    "windspeedmph": WIND_SPEED,
    "windgustmph": WIND_GUST,
    "winddir": WIND_DIR,
    "rainin": RAIN,
    "dailyrainin": DAILY_RAIN,
    "solarradiation": SOLAR_RADIATION,
    "indoortempf": INDOOR_TEMP,
    "indoorhumidity": INDOOR_HUMIDITY,
    "UV": UV,
    "soiltempf": CH1_TEMP,
    "soilmoisture": CH1_HUMIDITY,
    "soiltemp2f": CH2_TEMP,
    "soilmoisture2": CH2_HUMIDITY,
    "soiltemp3f": CH3_TEMP,
    "soilmoisture3": CH3_HUMIDITY,
    "soiltemp4f": CH4_TEMP,
    "soilmoisture4": CH4_HUMIDITY,
    "soiltemp5f": CH5_TEMP,
    "soilmoisture5": CH5_HUMIDITY,
    "soiltemp6f": CH6_TEMP,
    "soilmoisture6": CH6_HUMIDITY,
    "soiltemp7f": CH7_TEMP,
    "soilmoisture7": CH7_HUMIDITY,
}

REMAP_WSLINK_ITEMS: dict[str, str] = {
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
    "t1rainra": RAIN,
    "t1raindy": DAILY_RAIN,
    "t1solrad": SOLAR_RADIATION,
    "t1feels": FEELS_LIKE,
    "t1chill": CHILL_INDEX,
    "t1uvi": UV,
    "t1heat": HEAT_INDEX,
    "t1rainhr": HOURLY_RAIN,
    "t1rainwy": WEEKLY_RAIN,
    "t1rainmth": MONTHLY_RAIN,
    "t1rainyr": YEARLY_RAIN,
    "t1bat": OUTSIDE_BATTERY,
    "t1cn": OUTSIDE_CONNECTION,
    "t234c1tem": CH1_TEMP,
    "t234c1hum": CH1_HUMIDITY,
    "t234c1bat": CH1_BATTERY,
    "t234c1cn": CH1_CONNECTION,
    "t234c2tem": CH2_TEMP,
    "t234c2hum": CH2_HUMIDITY,
    "t234c2bat": CH2_BATTERY,
    "t234c2cn": CH2_CONNECTION,
    "t234c3tem": CH3_TEMP,
    "t234c3hum": CH3_HUMIDITY,
    "t234c3bat": CH3_BATTERY,
    "t234c3cn": CH3_CONNECTION,
    "t234c4tem": CH4_TEMP,
    "t234c4hum": CH4_HUMIDITY,
    "t234c4bat": CH4_BATTERY,
    "t234c4cn": CH4_CONNECTION,
    "t234c5tem": CH5_TEMP,
    "t234c5hum": CH5_HUMIDITY,
    "t234c5bat": CH5_BATTERY,
    "t234c5cn": CH5_CONNECTION,
    "t234c6tem": CH6_TEMP,
    "t234c6hum": CH6_HUMIDITY,
    "t234c6bat": CH6_BATTERY,
    "t234c6cn": CH6_CONNECTION,
    "t234c7tem": CH7_TEMP,
    "t234c7hum": CH7_HUMIDITY,
    "t234c7bat": CH7_BATTERY,
    "t234c7cn": CH7_CONNECTION,
    "t5lst": LIGHTNING_STRIKE_TIME,
    "t5lskm": LIGHTNING_DISTANCE,
    "t5lsf": LIGHTNING_STRIKE_COUNT_LAST_HOUR,
    "t5ls5mtc": LIGHTNING_STRIKE_COUNT_DURING_5_MINUTES,
    "t5ls30mtc": LIGHTNING_STRIKE_COUNT_DURING_30_MINUTES,
    "t5ls1htc": LIGHTNING_STRIKE_COUNT_DURING_1_HOUR,
    "t5ls1dtc": LIGHTNING_STRIKE_COUNT_DURING_1_DAY,
    "t5lsbat": T5_BATTERY,
    "t5lscn": T5_CONN,
    "t9hcho": HCHO,
    "t9voclv": VOC,
    "t9bat": T9_BATTERY,  # T9 battery is 0-5, where 5 is full
    "t10co2": CO2,
    "t10bat": T10_BATTERY,  # T10 battery is 0-5, where 5 is full
}


DISABLED_BY_DEFAULT: Final = [
    CH1_TEMP,
    CH1_HUMIDITY,
    CH1_BATTERY,
    CH2_TEMP,
    CH2_HUMIDITY,
    CH2_BATTERY,
    CH3_TEMP,
    CH3_HUMIDITY,
    CH3_BATTERY,
    CH4_TEMP,
    CH4_HUMIDITY,
    CH4_BATTERY,
    CH5_TEMP,
    CH5_HUMIDITY,
    CH5_BATTERY,
    CH6_TEMP,
    CH6_HUMIDITY,
    CH6_BATTERY,
    CH7_TEMP,
    CH7_HUMIDITY,
    CH7_BATTERY,
    OUTSIDE_BATTERY,
    WBGT_TEMP,
    LIGHTNING_STRIKE_TIME,
    LIGHTNING_DISTANCE,
    LIGHTNING_STRIKE_COUNT_LAST_HOUR,
    LIGHTNING_STRIKE_COUNT_DURING_5_MINUTES,
    LIGHTNING_STRIKE_COUNT_DURING_30_MINUTES,
    LIGHTNING_STRIKE_COUNT_DURING_1_HOUR,
    LIGHTNING_STRIKE_COUNT_DURING_1_DAY,
    T5_BATTERY,
    HCHO,
    VOC,
    T9_BATTERY,
    CO2,
    T10_BATTERY,
]

BATTERY_LIST = [
    OUTSIDE_BATTERY,
    INDOOR_BATTERY,
    CH1_BATTERY,
    CH2_BATTERY,
    CH3_BATTERY,
    CH4_BATTERY,
    CH5_BATTERY,
    CH6_BATTERY,
    CH7_BATTERY,
    T5_BATTERY,
]

BATTERY_NON_BINARY: list[str] = [T9_BATTERY, T10_BATTERY]

CONNECTION_GATED_SENSORS: Final[dict[str, list[str]]] = {
    "t9cn": [HCHO, VOC, T9_BATTERY],
    "t10cn": [CO2, T10_BATTERY],
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
