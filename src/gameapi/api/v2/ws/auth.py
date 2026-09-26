from __future__ import annotations

import asyncio

from fastapi import WebSocket

from gameapi.core.security import TokenDecodeError, decode_access_token

WS_CLOSE_AUTH_TIMEOUT = 4408
WS_CLOSE_UNAUTHORIZED = 4401


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

    return str(claims.sub)
