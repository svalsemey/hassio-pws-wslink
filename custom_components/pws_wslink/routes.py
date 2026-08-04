"""HTTP views routing station payloads to the config entry they authenticate to."""

from collections.abc import Mapping
from http import HTTPStatus
from logging import getLogger
from typing import Any, Protocol

from aiohttp.web import Request, Response
from aiohttp.web_exceptions import HTTPUnauthorized

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import API_MODE_BY_URI, CREDENTIAL_FIELDS_BY_MODE, DOMAIN

_LOGGER = getLogger(__name__)


class StationHandler(Protocol):
    """Interface a coordinator exposes to the router."""

    @property
    def api_mode(self) -> str:
        """Return the protocol the station is configured to use."""

    def credentials_match(self, station_id: str, station_password: str) -> bool:
        """Return True when the payload credentials belong to this station."""

    async def async_handle_payload(self, data: Mapping[str, Any]) -> None:
        """Process one authenticated payload."""


class StationRouter:
    """Dispatch incoming payloads to the station they authenticate to.

    All stations share the same two endpoints, so a payload is routed by the
    credentials it carries rather than by the URL it was sent to.
    """

    def __init__(self) -> None:
        """Initialize a router without any station."""
        self._handlers: dict[str, StationHandler] = {}

    def async_register_views(self, hass: HomeAssistant) -> None:
        """Register one Home Assistant view per supported endpoint."""
        for url, api_mode in API_MODE_BY_URI.items():
            hass.http.register_view(WeatherStationView(self, url, api_mode))

    def register(self, entry_id: str, handler: StationHandler) -> None:
        """Add or replace the handler of one config entry."""
        self._handlers[entry_id] = handler

    def unregister(self, entry_id: str) -> None:
        """Drop the handler of one config entry."""
        self._handlers.pop(entry_id, None)

    async def async_dispatch(self, api_mode: str, request: Request) -> Response:
        """Authenticate a payload and hand it over to the matching station."""
        data = dict(request.query) | dict(await request.post())
        id_field, password_field = CREDENTIAL_FIELDS_BY_MODE[api_mode]
        station_id = data.get(id_field)
        station_password = data.get(password_field)

        matched: StationHandler | None = None
        if station_id is not None and station_password is not None:
            # Every candidate is evaluated so the response time does not reveal
            # which station matched, nor how many are configured.
            for handler in list(self._handlers.values()):
                if handler.api_mode == api_mode and handler.credentials_match(
                    station_id, station_password
                ):
                    matched = handler

        if matched is None:
            _LOGGER.error("Unauthorised %s request on %s", api_mode, request.path)
            raise HTTPUnauthorized

        await matched.async_handle_payload(data)
        return Response(body="OK", status=HTTPStatus.OK)


class WeatherStationView(HomeAssistantView):
    """Expose one station endpoint through the Home Assistant HTTP component.

    Authentication is disabled at HTTP level because weather stations only
    support their own station id/password scheme and cannot present a Home
    Assistant access token. Credentials carried by the payload are verified
    with a constant-time comparison before any data is processed, and rejected
    requests raise HTTPUnauthorized so the Home Assistant IP ban middleware can
    throttle brute-force attempts.
    """

    requires_auth = False
    cors_allowed = False

    def __init__(self, router: StationRouter, url: str, api_mode: str) -> None:
        """Initialize the view bound to a single endpoint."""
        self._router = router
        self._api_mode = api_mode
        self.url = url
        self.name = f"api:{DOMAIN}:{api_mode}"

    async def get(self, request: Request) -> Response:
        """Handle a payload pushed as query parameters."""
        return await self._router.async_dispatch(self._api_mode, request)

    async def post(self, request: Request) -> Response:
        """Handle a payload pushed as a form body."""
        return await self._router.async_dispatch(self._api_mode, request)
