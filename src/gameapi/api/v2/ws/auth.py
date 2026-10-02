from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from time import monotonic

from fastapi import WebSocket

from gameapi.core.config import settings
from gameapi.core.security import TokenDecodeError, decode_access_token

WS_CLOSE_AUTH_TIMEOUT = 4408
WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_RATE_LIMITED = 4429

_ws_attempts: dict[str, deque[float]] = defaultdict(deque)


def _parse_limit(limit: str) -> tuple[int, float]:
    count_str, period_str = limit.split("/", 1)
    count = int(count_str)
    period = {
        "second": 1.0,
        "minute": 60.0,
        "hour": 3600.0,
        "day": 86400.0,
    }[period_str]
    return count, period


def _check_ws_rate_limit(user_id: str) -> bool:
    limit_str = settings.rate_limit.ws_handshake
    count, period = _parse_limit(limit_str)
    now = monotonic()
    window_start = now - period

    attempts = _ws_attempts[user_id]
    while attempts and attempts[0] < window_start:
        attempts.popleft()

    if len(attempts) >= count:
        return False

    attempts.append(now)
    return True


async def authenticate_websocket(
    websocket: WebSocket,
    *,
    timeout_seconds: float = 10.0,
) -> str | None:
    """
    Read the first message from the WS, validate JWT.

    Returns the user_id (str) on success, None if auth failed (the connection
    has already been closed with the appropriate code).
    """
    await websocket.accept()

    try:
        first_message = await asyncio.wait_for(websocket.receive_json(), timeout=timeout_seconds)
    except TimeoutError:
        await websocket.close(code=WS_CLOSE_AUTH_TIMEOUT, reason="auth_timeout")
        return None
    except ValueError:
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED, reason="invalid_auth_message")
        return None

    if not isinstance(first_message, dict) or first_message.get("event") != "auth":
        await websocket.send_json(
            {
                "event": "auth_error",
                "payload": {"reason": "expected_auth_event"},
            }
        )
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED)
        return None

    payload = first_message.get("payload")
    token = payload.get("token") if isinstance(payload, dict) else None
    if not isinstance(token, str):
        await websocket.send_json(
            {
                "event": "auth_error",
                "payload": {"reason": "invalid_token"},
            }
        )
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED)
        return None

    try:
        claims = decode_access_token(token)
    except TokenDecodeError:
        await websocket.send_json(
            {
                "event": "auth_error",
                "payload": {"reason": "invalid_token"},
            }
        )
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED)
        return None

    if not _check_ws_rate_limit(claims.sub):
        await websocket.send_json(
            {
                "event": "auth_error",
                "payload": {"reason": "rate_limited"},
            }
        )
        await websocket.close(code=WS_CLOSE_RATE_LIMITED, reason="rate_limited")
        return None

    return str(claims.sub)
