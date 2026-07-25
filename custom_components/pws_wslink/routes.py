"""Store and dispatch route info."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from logging import getLogger

from aiohttp.web import AbstractRoute, Request, Response, StreamResponse

_LOGGER = getLogger(__name__)

HandlerT = Callable[[Request], Awaitable[StreamResponse]]


@dataclass(slots=True)
class Route:
    """Store route metadata and active handler."""

    method: str
    url_path: str
    route: AbstractRoute
    handler: HandlerT
    enabled: bool = False

    def __str__(self) -> str:
        """Return string representation."""
        status = "enabled" if self.enabled else "disabled"
        return f"{self.method} {self.url_path} ({status}) -> {self.handler}"


class Routes:
    """Store routes info and provide safe handler dispatching."""

    def __init__(self) -> None:
        """Initialize routes."""
        self.routes: dict[str, Route] = {}

    @staticmethod
    def _key(method: str, url_path: str) -> str:
        """Build internal route key."""
        return f"{method.upper()}:{url_path}"

    def make_dispatcher(self, method: str, url_path: str) -> HandlerT:
        """Create a stable aiohttp handler that dispatches to current Route.handler."""

        key = self._key(method, url_path)

        async def _dispatcher(request: Request) -> StreamResponse:
            route = self.routes.get(key)
            if route is None:
                _LOGGER.error("Dispatcher called for unknown route: %s", key)
                return Response(text="Unregistered webhook.", status=404)

            return await route.handler(request)

        return _dispatcher

    def switch_route(self, coordinator: HandlerT, url_path: str) -> None:
        """Enable handlers for one URL path and disable others."""
        for route in self.routes.values():
            if route.url_path == url_path:
                _LOGGER.info(
                    "New coordinator to route: %s %s", route.method, route.url_path
                )
                route.enabled = True
                route.handler = coordinator
            else:
                route.enabled = False
                route.handler = unregistered

    def add_route(
        self,
        url_path: str,
        route: AbstractRoute,
        handler: HandlerT,
        enabled: bool = False,
    ) -> None:
        """Add route metadata."""
        key = self._key(route.method, url_path)
        self.routes[key] = Route(
            method=route.method,
            url_path=url_path,
            route=route,
            handler=handler,
            enabled=enabled,
        )

    def get_route(self, url_path: str) -> Route | None:
        """Get first route matching url_path."""
        for route in self.routes.values():
            if route.url_path == url_path:
                return route
        return None

    def get_enabled(self) -> str:
        """Get enabled routes."""
        enabled_routes = {
            route.url_path for route in self.routes.values() if route.enabled
        }
        return ", ".join(sorted(enabled_routes)) if enabled_routes else "None"

    def __str__(self) -> str:
        """Return string representation."""
        return "\n".join(str(route) for route in self.routes.values())


async def unregistered(_request: Request) -> Response:
    """Handle incoming data for disabled/unregistered webhook."""
    _LOGGER.error("Received data to unregistered webhook. Check your settings")
    return Response(text="Unregistered webhook.", status=404)
