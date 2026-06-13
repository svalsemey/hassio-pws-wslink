# Weather Station for Home Assistant

Custom integration to for local weather stations.

This integration supports stations that can send data to a custom server using:

- Personal Weather Station / WeatherUnderground API (PWS/WU)
- WS-Link API

It is designed for stations such as **Sencor**, **Bresser**, **Garni**, and compatible models using similar payload formats.

---

## Features

- Native UI configuration flow (no YAML required)
- Local push architecture (`iot_class: local_push`)
- Credential validation (`API_ID` / `API_KEY`)
- Supports both **PWS/WU** and **WSLink** receive modes
- Automatic entity discovery:
  - Sensors are created when first data is received
  - New sensor detection triggers a translated persistent notification
- Rich weather and environmental sensor coverage:
  - Indoor/outdoor temperature & humidity
  - Pressure, wind speed/direction/gust, rain metrics
  - UV, solar radiation, dew point, feels like, heat index, wind chill
  - Lightning sensors (time, distance, strike counters)
  - Optional air-quality sensors (HCHO, VOC, CO2) when reported
- WSLink battery handling:
  - Sensor battery values
  - Dedicated battery binary sensors (low/normal semantics)

---

## Requirements

- Home Assistant with `http` integration enabled (default)
- A weather station capable of sending data to a custom server
- Network connectivity from station to Home Assistant

---

## Installation

### HACS (Custom Repository)

1. Go to **HACS → Integrations → ⋮ → Custom repositories**
2. Add your repository URL (the one hosting this integration)
3. Category: **Integration**
4. Install **Weather Station**
5. Restart Home Assistant

### Manual Installation

1. Copy `custom_components/weather_station` into your Home Assistant config:
   - `config/custom_components/weather_station`
2. Restart Home Assistant
3. Add integration from **Settings → Devices & Services**

---

## Configuration (UI)

When adding the integration:

- `API_ID`: station ID/identifier configured on the station
- `API_KEY`: password/key configured on the station
- `WSLink API`:
  - **Disabled** = PWS/WU endpoint mode
  - **Enabled** = WSLink endpoint mode
- `Developer log` (optional): verbose diagnostics in logs

No YAML is needed.

---

## Station Setup

Configure your station custom upload target to your Home Assistant host.

- **PWS/WU mode**: use endpoint  
  `/weatherstation/updateweatherstation.php`
- **WSLink mode**: use endpoint  
  `/data/upload.php`

Use the same `API_ID` / `API_KEY` on both station and integration config.

---

## Entity Availability Behavior

- Before first payload after startup/reload, entities remain available (bootstrap-safe behavior).
- After payloads are received, if a sensor is missing in incoming data, it becomes `unavailable`.
- Entities are **not auto-disabled** in registry and are kept manageable by the user.

---

## Supported Entity Types

- **Sensor**
- **Binary Sensor** (battery binary sensors for WSLink battery fields)

---

## Troubleshooting

- No data arriving:
  - Verify station target URL, host/IP, and port
  - Confirm protocol mode (PWS/WU vs WSLink) matches integration option
  - Check credentials (`API_ID` / `API_KEY`)
- Unauthorized errors:
  - Credentials in payload do not match integration options
- Missing sensors:
  - Sensors appear only after station sends corresponding keys at least once

Enable debug logs:

```yaml
logger:
  default: info
  logs:
    custom_components.weather_station: debug
```

---

## Privacy & Security

- Data flow is local (station → Home Assistant)
- No cloud account required by this integration
- Keep Home Assistant and station endpoints protected within your LAN

---

## Acknowledgments

Special thanks to **Lukas Svoboda** ([@schizza](https://github.com/schizza)) for his major work on the original Sencor SWS integration:

- https://github.com/schizza/SWS-12500-custom-component

This `weather_station` integration has been **very largely based** on those works.

---

## License

MIT.
