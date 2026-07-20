from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import get_settings
from app.core.errors import error_response

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class OriginCheckMiddleware(BaseHTTPMiddleware):
    """Reject mutating cross-origin requests (CSRF defence alongside SameSite=Lax)."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        origin = request.headers.get("origin")
        if origin is not None and request.method in MUTATING_METHODS:
            allowed = str(get_settings().public_origin).rstrip("/")
            if origin.rstrip("/") != allowed:
                return error_response(403, "FORBIDDEN_ORIGIN", "Origin tidak diizinkan.")
        return await call_next(request)
