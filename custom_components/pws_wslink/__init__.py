"""Weather Station integration."""

import logging

import aiohttp.web
from aiohttp.web_exceptions import HTTPUnauthorized

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import InvalidStateError, PlatformNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    API_ID,
    API_KEY,
    API_MODE,
    API_MODE_WSLINK,
    DEV_DBG,
    DOMAIN,
    SENSORS_TO_LOAD,
    URI_API_PWS,
    URI_API_WSLINK,
)
from .helpers import (
    anonymize,
    check_disabled,
    loaded_sensors,
    remap_items,
    remap_wslink_items,
    translated_notification,
    translations,
    update_options,
)
from .routes import Routes, unregistered

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


class IncorrectDataError(InvalidStateError):
    """Invalid exception."""


class WeatherDataUpdateCoordinator(DataUpdateCoordinator):
    """Manage fetched data."""

    def __init__(self, hass: HomeAssistant, config: ConfigEntry) -> None:
        """Init global updater."""
        self.hass = hass
        self.config = config
        self.config_entry = config
        super().__init__(hass, _LOGGER, name=DOMAIN)

    async def received_data(self, webdata: aiohttp.web.Request):
        """Handle incoming data query."""
        is_wslink = self.config_entry.options.get(API_MODE) == API_MODE_WSLINK
        get_data = webdata.query
        post_data = await webdata.post()

        data = dict(get_data) | dict(post_data)

        if not is_wslink and ("ID" not in data or "PASSWORD" not in data):
            _LOGGER.error("Invalid request. No security data provided!")
            raise HTTPUnauthorized

        if is_wslink and ("wsid" not in data or "wspw" not in data):
            _LOGGER.error("Invalid request. No security data provided!")
            raise HTTPUnauthorized

        if is_wslink:
            id_data = data["wsid"]
            key_data = data["wspw"]
        else:
            id_data = data["ID"]
            key_data = data["PASSWORD"]

        _id = self.config_entry.options.get(API_ID)
        _key = self.config_entry.options.get(API_KEY)

        if id_data != _id or key_data != _key:
            _LOGGER.error("Unauthorised access!")
            raise HTTPUnauthorized

        remaped_items = remap_wslink_items(data) if is_wslink else remap_items(data)

        if sensors := check_disabled(self.hass, remaped_items, self.config):
            # Translate sensor labels only once per key.
            translated_names: list[str] = []
            for t_key in sensors:
                name = await translations(
                    self.hass, DOMAIN, f"sensor.{t_key}", key="name", category="entity"
                )
                if name:
                    translated_names.append(name)

            human_readable = "\n".join(translated_names)

            await translated_notification(
                self.hass,
                DOMAIN,
                "new_sensors",
                {"added_sensors": f"{human_readable}\n"},
            )

            loaded = loaded_sensors(self.config_entry) or []
            # Merge without duplicates, keep insertion order.
            merged = list(dict.fromkeys([*loaded, *sensors]))
            await update_options(self.hass, self.config_entry, SENSORS_TO_LOAD, merged)

        self.async_set_updated_data(remaped_items)

        if self.config_entry.options.get(DEV_DBG):
            _LOGGER.info("Dev log: %s", anonymize(data))

        return aiohttp.web.Response(body="OK", status=200)


def register_path(
    hass: HomeAssistant,
    url_path: str,
    coordinator: WeatherDataUpdateCoordinator,
    config: ConfigEntry,
):
    """Register path to handle incoming data."""

    hass_data = hass.data.setdefault(DOMAIN, {})
    debug = config.options.get(DEV_DBG)
    is_wslink = config.options.get(API_MODE) == API_MODE_WSLINK

    routes: Routes = hass_data.get("routes", Routes())

    if not routes.routes:
        routes = Routes()
        _LOGGER.info("Routes not found, creating new routes")

        if debug:
            _LOGGER.debug("Enabled route is: %s, WSLink is %s", url_path, is_wslink)

        try:
            default_route = hass.http.app.router.add_get(
                URI_API_PWS,
                coordinator.received_data if not is_wslink else unregistered,
                name="weather_default_url",
            )
            if debug:
                _LOGGER.debug("Default route: %s", default_route)

            wslink_route = hass.http.app.router.add_get(
                URI_API_WSLINK,
                coordinator.received_data if is_wslink else unregistered,
                name="weather_wslink_url",
            )
            if debug:
                _LOGGER.debug("WSLink route: %s", wslink_route)

            wslink_post_route = hass.http.app.router.add_post(
                URI_API_WSLINK,
                coordinator.received_data if is_wslink else unregistered,
                name="weather_wslink_post_route_url",
            )
            if debug:
                _LOGGER.debug("WSLink route: %s", wslink_post_route)

            routes.add_route(
                URI_API_PWS,
                default_route,
                coordinator.received_data if not is_wslink else unregistered,
                not is_wslink,
            )
            routes.add_route(
                URI_API_WSLINK, wslink_route, coordinator.received_data, is_wslink
            )

            routes.add_route(
                URI_API_WSLINK, wslink_post_route, coordinator.received_data, is_wslink
            )

            hass_data["routes"] = routes

        except RuntimeError as Ex:
            if (
                "Added route will never be executed, method GET is already registered"
                in Ex.args
            ):
                _LOGGER.info("Handler to URL (%s) already registred", url_path)
                return False

            _LOGGER.error("Unable to register URL handler! (%s)", Ex.args)
            return False

        _LOGGER.info(
            "Registered path to handle weather data: %s",
            routes.get_enabled(),  # pylint: disable=used-before-assignment
        )

    if is_wslink:
        routes.switch_route(coordinator.received_data, URI_API_WSLINK)
    else:
        routes.switch_route(coordinator.received_data, URI_API_PWS)

    return routes


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the config entry for my device."""

    coordinator = WeatherDataUpdateCoordinator(hass, entry)

    hass_data = hass.data.setdefault(DOMAIN, {})
    hass_data[entry.entry_id] = coordinator

    is_wslink = entry.options.get(API_MODE) == API_MODE_WSLINK
    debug = entry.options.get(DEV_DBG)

    if debug:
        _LOGGER.debug("WS Link is %s", "enabled" if is_wslink else "disabled")

    route = register_path(
        hass, URI_API_PWS if not is_wslink else URI_API_WSLINK, coordinator, entry
    )

    if not route:
        _LOGGER.error("Fatal: path not registered!")
        raise PlatformNotReady

    hass_data["route"] = route

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Update setup listener."""

    await hass.config_entries.async_reload(entry.entry_id)

    _LOGGER.info("Settings updated")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    _ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if _ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return _ok
