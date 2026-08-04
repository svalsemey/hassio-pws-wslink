# Weather Station for Home Assistant

Custom integration for local weather stations.

This integration supports stations that can send data to a custom server using:

- Personal Weather Station / WeatherUnderground API (PWS/WU)
- WS-Link API

It is designed for stations such as **Sencor**, **Bresser**, **Garni**, and compatible models using similar payload formats.

---

## Features

- Native UI configuration flow (no YAML required)
- Multiple stations supported: add the integration once per station
- Local push architecture (`iot_class: local_push`)
- Credential validation (station ID / password), compared in constant time
- Supports both **PWS/WU** and **WSLink** receive modes
- HTTPS awareness in config flow:
  - If Home Assistant is detected as non-HTTPS, a confirmation warning is shown before continuing
- Automatic entity discovery:
  - Sensors are created as soon as the station sends the matching data
  - New entities appear immediately, without reloading the integration
  - Newly detected modules trigger a translated persistent notification
- Device topology:
  - The base station is exposed as a hub device
  - Each detected module gets its own device, linked to the hub
  - Any module device can be removed manually from its device page
- Rich weather and environmental sensor coverage:
  - Indoor/outdoor temperature & humidity
  - Pressure, wind speed/direction/gust, rain metrics
  - UV, solar radiation, dew point, feels like, heat index, wind chill
  - Lightning sensors (time, distance, strike counters)
  - Optional air-quality sensors (PM, HCHO, VOC, CO₂, CO) when reported
- Lightning handling:
  - The last strike time is derived from the elapsed minutes reported by the station
  - Strikes are detected from the counters as well, so a burst is never missed
  - Implausible payloads, such as a rebooted station, are ignored
- WSLink battery handling:
  - Percentage battery sensors for modules reporting a level
  - Dedicated battery binary sensors (low/normal semantics)
  - All battery entities are exposed in the diagnostic category

---

## Requirements

- Home Assistant **2026.7** or newer
- The `http` integration enabled (default)
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

1. Copy `custom_components/pws_wslink` into your Home Assistant config:
   - `config/custom_components/pws_wslink`
2. Restart Home Assistant
3. Add integration from **Settings → Devices & Services**

---

## Configuration (UI)

When adding the integration:

- `Station ID`: the station ID configured on the station
- `Station password`: the password configured on the station
- `API mode`:
  - `pws` = PWS/WU endpoint mode
  - `wslink` = WSLink endpoint mode
- `Developer log` (optional): verbose diagnostics in logs

No YAML is needed.

---

## Options (UI)

In integration options, you can change:

- `Station ID` and `Station password`
- `API mode`
- `Developer log`

Credentials and the developer log are applied immediately. Changing the API mode
reloads the integration, since it selects the sensor set.

---

## Multiple Stations

Several weather stations can be configured side by side. Add the integration
once per station, each with its own station ID and password.

All stations share the same two endpoints. Incoming payloads are routed to the
right station by the credentials they carry, so both stations can use the same
API mode, or a different one each.

Each station gets its own hub device, with its own modules attached. The station
ID is shown as the serial number of the hub. Two stations cannot share the same
station ID; the configuration flow rejects a duplicate.

---

## Devices and Modules

The base station is exposed as a hub device. Every module reported by the
station becomes its own device attached to that hub: outdoor sensor, extra
channels, lightning sensor, water leak sensors, air-quality sensors, and so on.
Channel-based modules also expose a diagnostic sensor holding their channel
number.

### Removing a module

Open the device page of the module and use **⋮ → Delete**. The device and all its
entities are removed right away, without reloading the integration.

Removal is not permanent by design: the module is simply forgotten. If the
station keeps reporting it, the device and its entities are recreated on the next
payload, along with a detection notification. To make the removal stick, stop the
module from reporting, or unpair it from the station.

This is the intended way to get rid of a module you no longer own. The
integration never deletes devices on its own.

---

## ⚠️ Important — HTTPS and weather station uploads

Many recent weather stations send data over HTTPS only.

If Home Assistant is not reachable over HTTPS on your local network, uploads may fail depending on station behavior.

For this reason, the integration shows a **confirmation warning** during configuration whenever Home Assistant is detected as non-HTTPS.

If your station requires HTTPS, you must either:

1. Put Home Assistant behind your own HTTPS reverse proxy, **or**
2. Install the **WSLink proxy add-on**:
   - https://github.com/schizza/wslink-addon

The WSLink proxy add-on terminates TLS (HTTPS) from the station and forwards requests to Home Assistant over local HTTP.

### Quick rule

- **Station sends HTTPS** → HTTPS endpoint is required (native HTTPS HA or reverse proxy/add-on)
- **Station sends plain HTTP** → proxy is usually not required

---

## Station Setup

Configure your station custom upload target to your Home Assistant host.

- **PWS/WU mode**: use endpoint
  `/weatherstation/updateweatherstation.php`
- **WSLink mode**: use endpoint
  `/data/upload.php`

Both endpoints accept `GET` and `POST`.

Use the same station ID and password on both the station and the integration.

---

## Entity Availability Behavior

- Before first payload after startup/reload, entities remain available (bootstrap-safe behavior).
- After payloads are received, if a sensor is missing in incoming data, it becomes `unavailable`.
- In WSLink mode, a module reported as disconnected stops publishing values, so its entities become `unavailable` until it comes back.
- Entities are **not auto-disabled** in registry and are kept manageable by the user.
- The lightning strike time and distance keep their last coherent value between
  strikes, instead of following the raw payload.

---

## Supported Entity Types

Two platforms are used: **sensor** and **binary sensor**. Nothing is created up
front: an entity appears the first time the station reports the matching field,
so your own list depends on the modules you actually own.

### Base station (hub)

| Entity | Type | PWS/WU | WSLink |
| --- | --- | :---: | :---: |
| Temperature | sensor | ✅ | ✅ |
| Humidity | sensor | ✅ | ✅ |
| Barometric pressure | sensor | ✅ | ✅ |
| Battery | binary sensor | — | ✅ |

### Outdoor sensor (Type 1)

| Entity | Type | PWS/WU | WSLink |
| --- | --- | :---: | :---: |
| Temperature | sensor | ✅ | ✅ |
| Humidity | sensor | ✅ | ✅ |
| Dew point | sensor | ✅ | ✅ |
| Apparent temperature | sensor | computed | ✅ |
| Wind chill temperature | sensor | computed | ✅ |
| Feels like temperature | sensor | — | ✅ |
| Wet-bulb globe temperature | sensor | — | ✅ |
| Wind speed | sensor | ✅ | ✅ |
| Wind gust | sensor | ✅ | ✅ |
| Wind direction | sensor | ✅ | ✅ |
| Bearing | sensor | derived | derived |
| Rain rate | sensor | ✅ | ✅ |
| Rainfall (daily total) | sensor | ✅ | ✅ |
| Rainfall (hourly, weekly, monthly, yearly) | sensor | — | ✅ |
| Solar irradiance | sensor | ✅ | ✅ |
| UV index | sensor | ✅ | ✅ |
| Battery | binary sensor | — | ✅ |

### Channels 1 to 7 (Type 2/3/4)

Thermo-hygrometer, pool and soil sensors. In PWS/WU mode these come from the
`soiltemp` and `soilmoisture` fields.

| Entity | Type | PWS/WU | WSLink |
| --- | --- | :---: | :---: |
| Temperature | sensor | ✅ | ✅ |
| Humidity | sensor | ✅ | ✅ |
| Channel number | sensor (diagnostic) | ✅ | ✅ |
| Battery | binary sensor | — | ✅ |

### WSLink-only modules

| Module | Entities |
| --- | --- |
| Lightning sensor (Type 5) | Last strike time, distance, strike counts over the last hour, 5 minutes, 30 minutes, 1 hour and 1 day, battery (binary) |
| Water leak sensor 1 to 7 (Type 6) | Water leak (binary), channel number (diagnostic), battery (binary) |
| PM sensor (Type 8) | PM2.5, PM10, PM2.5 AQI, PM10 AQI, battery (%) |
| HCHO/VOC sensor (Type 9) | Formaldehyde, VOC level, battery (%) |
| CO₂ sensor (Type 10) | Carbon dioxide, battery (%) |
| CO sensor (Type 11) | Carbon monoxide, battery (%) |

**computed** — the station does not report the value in this mode, so the
integration derives it from the outdoor temperature, humidity and wind speed.

**derived** — the bearing is the cardinal direction matching the reported wind
direction, exposed as a separate entity.

Battery levels are reported either as a low/normal flag, exposed as a binary
sensor, or as a 0 to 5 level, exposed as a percentage sensor. Both are placed in
the diagnostic section of the device page.

---

## Troubleshooting

- No data arriving:
  - Verify station target URL, host/IP, and port
  - Confirm protocol mode (PWS/WU vs WSLink) matches integration option
  - Check credentials (station ID / password)
  - If your station sends HTTPS, verify your HTTPS endpoint/proxy setup
- The wrong station received the data:
  - Both stations use the same credentials; give each one its own station ID
- Unauthorized errors:
  - No configured station matches the credentials sent in the payload
  - Check that the API mode of the target station matches the endpoint used
  - Repeated failures may get the station IP banned by Home Assistant; check `ip_bans.yaml`
- Missing sensors:
  - Sensors appear only after station sends corresponding keys at least once
- A deleted module came back:
  - The station is still reporting it; stop or unpair the module at the station
- Entities stay `unavailable`:
  - The module is reported as disconnected, or the station stopped sending that data
- Lightning strike time looks stuck:
  - It only moves when a new strike is detected; check the strike counters
  - Two strikes within the same minute share one timestamp, but both are counted

Enable debug logs:

```yaml
logger:
  default: info
  logs:
    custom_components.pws_wslink: debug
```

---

## Privacy & Security

- Data flow is local (station → Home Assistant)
- No cloud account required by this integration
- Station endpoints are served through Home Assistant's HTTP component, so failed
  authentication attempts feed the built-in IP ban protection
- Station credentials are compared in constant time and are never written to logs
- Keep Home Assistant and station endpoints protected within your LAN

---

## Acknowledgments

Special thanks to **Lukas Svoboda** ([@schizza](https://github.com/schizza)) for his major work on the original Sencor SWS integration:

- https://github.com/schizza/SWS-12500-custom-component

This integration has been **very largely based** on those works.

---

## License

MIT.
