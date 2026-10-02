"""Centralized rate limiter configuration.

Uses slowapi with a hierarchical key function: authenticated users are
limited by their user_id; anonymous clients by their remote IP.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from gameapi.core.config import settings
from gameapi.core.security import TokenDecodeError, decode_access_token

F = TypeVar("F", bound=Callable[..., Any])


def rate_limit(limit_value: str) -> Callable[[F], F]:
    """
    Typed wrapper around slowapi's `limiter.limit`.

    slowapi ships no type stubs, so `limiter.limit(...)` returns
    `Callable[..., Any]` and mypy strict mode reports `[misc]` on the
    decorated function. This wrapper preserves the input callable's type.
    """
    return cast(Callable[[F], F], limiter.limit(limit_value))


def _try_decode(token: str) -> str | None:
    try:
        claims = decode_access_token(token)
    except TokenDecodeError:
        return None
    return claims.sub


def _is_anonymous_rate_limit_route(request: Request) -> bool:
    """Routes that should be counted by client IP, even if a stale auth token is present."""
    method = request.method.upper()
    path = request.url.path.rstrip("/")
    anonymous_paths = {
        "/api/v2/auth/login",
        "/api/v2/auth/register",
        "/api/v2/auth/refresh",
        "/api/v1/users/login",
    }
    if path in anonymous_paths:
        return True
    return method == "POST" and path == "/api/v1/users"


def hierarchical_key(request: Request) -> str:
    """
    Extract the rate limit key from the request.

    Priority:
    1. `user_id` from a valid JWT in the Authorization header (Bearer) for authenticated routes.
    2. `user_id` from the `gameapi_at` cookie (browser clients) for authenticated routes.
    3. Remote IP address (anonymous and login/register/refresh flows).
    """
    if _is_anonymous_rate_limit_route(request):
        remote_addr = get_remote_address(request) or "unknown"
        return f"ip:{remote_addr}"

    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        user_id = _try_decode(token)
        if user_id:
            return f"user:{user_id}"

    cookie_token = request.cookies.get("gameapi_at")
    if cookie_token:
        user_id = _try_decode(cookie_token)
        if user_id:
            return f"user:{user_id}"

    remote_addr = get_remote_address(request) or "unknown"
    return f"ip:{remote_addr}"


limiter = Limiter(
    key_func=hierarchical_key,
    default_limits=[],
    storage_uri=settings.rate_limit.storage_uri,
    strategy="fixed-window",
    headers_enabled=True,
    enabled=settings.rate_limit.enabled,
)
