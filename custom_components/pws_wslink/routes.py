"""HTTP views and request dispatching for the Weather Station endpoints."""

from collections.abc import Awaitable, Callable
from http import HTTPStatus
from logging import getLogger

from aiohttp.web import Request, Response, StreamResponse

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN, URI_API_PWS, URI_API_WSLINK

_LOGGER = getLogger(__name__)

HandlerT = Callable[[Request], Awaitable[StreamResponse]]

ENDPOINTS: tuple[tuple[str, str], ...] = (
    (URI_API_PWS, "pws"),
    (URI_API_WSLINK, "wslink"),
)


async def unregistered(_request: Request) -> Response:
    """Reject data sent to an endpoint that is not bound to a coordinator."""
    _LOGGER.error("Received data on an inactive endpoint. Check your settings")
    return Response(text="Unregistered endpoint.", status=HTTPStatus.NOT_FOUND)


class Routes:
    """Track the handler currently bound to each endpoint."""

    def __init__(self) -> None:
        """Initialize every endpoint as inactive."""
        self.handlers: dict[str, HandlerT] = dict.fromkeys(
            (url for url, _ in ENDPOINTS), unregistered
        )

    def async_register_views(self, hass: HomeAssistant) -> None:
        """Register one Home Assistant view per supported endpoint."""
        for url, slug in ENDPOINTS:
            hass.http.register_view(WeatherStationView(self, url, slug))

    async def async_dispatch(self, url_path: str, request: Request) -> StreamResponse:
        """Forward a request to the handler currently bound to the endpoint."""
        return await self.handlers.get(url_path, unregistered)(request)

    def switch_route(self, handler: HandlerT, url_path: str) -> None:
        """Bind the handler to one endpoint and release the others."""
        self.handlers = {
            url: handler if url == url_path else unregistered for url in self.handlers
        }
        _LOGGER.info("Active endpoint: %s", self.get_enabled())

    def release(self) -> None:
        """Release every endpoint, e.g. when the config entry is unloaded."""
        self.handlers = dict.fromkeys(self.handlers, unregistered)

    def get_enabled(self) -> str:
        """Return the comma-separated list of active endpoints."""
        return (
            ", ".join(
                sorted(
                    url
                    for url, handler in self.handlers.items()
                    if handler is not unregistered
                )
            )
            or "None"
        )

    def __str__(self) -> str:
        """Return string representation."""
        return "\n".join(
            f"{url} -> {handler}" for url, handler in self.handlers.items()
        )


class WeatherStationView(HomeAssistantView):
    """Expose one station endpoint through the Home Assistant HTTP component.

    Authentication is disabled at HTTP level because weather stations only
    support their own station id/password scheme and cannot present a Home
    Assistant access token. Credentials carried by the payload are verified
    with a constant-time comparison by the coordinator before any data is
    processed, and rejected requests raise HTTPUnauthorized so the Home
    Assistant IP ban middleware can throttle brute-force attempts.
    """

    requires_auth = False
    cors_allowed = False

    def __init__(self, routes: Routes, url: str, slug: str) -> None:
        """Initialize the view bound to a single endpoint."""
        self._routes = routes
        self.url = url
        self.name = f"api:{DOMAIN}:{slug}"

    async def get(self, request: Request) -> StreamResponse:
        """Handle a payload pushed as query parameters."""
        return await self._routes.async_dispatch(self.url, request)

    async def post(self, request: Request) -> StreamResponse:
        """Handle a payload pushed as a form body."""
        return await self._routes.async_dispatch(self.url, request)
