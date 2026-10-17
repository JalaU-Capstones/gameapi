"""Transport for the global in-memory chat; the state lives in chat_service."""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from fastapi import APIRouter, WebSocket
from fastapi.websockets import WebSocketDisconnect
from pydantic import ValidationError

from gameapi.api.v2.ws.auth import authenticate_websocket
from gameapi.api.v2.ws.manager import chat_manager
from gameapi.db.session import PostgresDatabase
from gameapi.schemas.ws_events import ChatSendPayload
from gameapi.services.chat_service import ChatMessage, chat_service
from gameapi.services.exceptions import (
    ChatEmptyMessageError,
    ChatMessageTooLongError,
    ChatRateLimitedError,
)
from gameapi.services.user_service import UserService

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_RAW_CONTENT_LENGTH = 2000


def _message_to_payload(message: ChatMessage) -> dict[str, Any]:
    """Serialize a ChatMessage for JSON transport."""
    return {
        "id": message.id,
        "user_id": message.user_id,
        "user_name": message.user_name,
        "content": message.content,
        "timestamp": message.timestamp.isoformat(),
    }


async def _send_chat_error(
    websocket: WebSocket,
    code: str,
    message: str,
    *,
    retry_after_seconds: int | None = None,
) -> None:
    """Send a chat_error frame. Swallows disconnect errors."""
    payload: dict[str, Any] = {"code": code, "message": message}
    if retry_after_seconds is not None:
        payload["retry_after_seconds"] = retry_after_seconds

    with contextlib.suppress(WebSocketDisconnect, RuntimeError):
        await websocket.send_json({"event": "chat_error", "payload": payload})


async def _handle_message(
    user_id: str,
    user_name: str,
    message: dict[str, Any],
    websocket: WebSocket,
) -> None:
    event = message.get("event") if isinstance(message, dict) else None
    if event is None:
        await _send_chat_error(websocket, "INVALID_EVENT", "Missing 'event' field")
        return

    if event == "ping":
        await websocket.send_json({"event": "pong", "payload": {}})
        return

    if event == "chat_send":
        payload_raw = message.get("payload")
        if not isinstance(payload_raw, dict):
            await _send_chat_error(websocket, "INVALID_PAYLOAD", "Missing 'payload'")
            return

        try:
            payload = ChatSendPayload(**payload_raw)
        except ValidationError:
            await _send_chat_error(websocket, "INVALID_PAYLOAD", "Invalid payload")
            return

        if len(payload.content) > MAX_RAW_CONTENT_LENGTH:
            await _send_chat_error(
                websocket,
                "CHAT_MESSAGE_TOO_LONG",
                "Content exceeds the maximum allowed length",
            )
            return

        try:
            stored = await chat_service.publish(user_id, user_name, payload.content)
        except ChatEmptyMessageError:
            await _send_chat_error(
                websocket,
                "CHAT_MESSAGE_EMPTY",
                "Chat message is empty after sanitization",
            )
            return
        except ChatMessageTooLongError:
            await _send_chat_error(
                websocket,
                "CHAT_MESSAGE_TOO_LONG",
                "Chat message exceeds the maximum allowed length",
            )
            return
        except ChatRateLimitedError as exc:
            await _send_chat_error(
                websocket,
                "CHAT_RATE_LIMITED",
                "Chat rate limit exceeded; retry after some time",
                retry_after_seconds=exc.retry_after_seconds,
            )
            return

        await chat_manager.broadcast(
            {"event": "chat_message", "payload": _message_to_payload(stored)}
        )
        return

    await _send_chat_error(
        websocket,
        "NOT_IMPLEMENTED",
        f"Event not implemented yet: {event}",
    )


@router.websocket("/chat")
async def chat_websocket(websocket: WebSocket) -> None:
    auth = await authenticate_websocket(websocket)
    if auth is None:
        return
    user_id, sid = auth

    if chat_manager.get_user_socket(user_id) is not None:
        await websocket.close(code=4409, reason="session_already_active")
        return

    async with PostgresDatabase.session_factory()() as session:
        user = await UserService(session).get_by_id(user_id)
    user_name = user.name if user is not None else "Unknown"

    await chat_manager.connect(user_id, websocket, sid)
    logger.info(
        "Chat websocket connected",
        extra={"event_type": "chat_connected", "player_id": user_id},
    )

    await websocket.send_json({"event": "auth_ok", "payload": {"user_id": user_id}})
    count = len(chat_manager.online_user_ids())
    await websocket.send_json(
        {
            "event": "chat_history",
            "payload": {
                "messages": [_message_to_payload(message) for message in chat_service.history()],
                "users_count": count,
            },
        }
    )
    await chat_manager.broadcast(
        {"event": "chat_users_count", "payload": {"count": count}},
        exclude={user_id},
    )

    try:
        while True:
            message = await websocket.receive_json()
            if not isinstance(message, dict):
                await _send_chat_error(
                    websocket,
                    "INVALID_PAYLOAD",
                    "Message must be a JSON object",
                )
                continue
            await _handle_message(user_id, user_name, message, websocket)
    except WebSocketDisconnect:
        pass
    finally:
        chat_manager.disconnect(user_id, websocket)
        logger.info(
            "Chat websocket disconnected",
            extra={"event_type": "chat_disconnected", "player_id": user_id},
        )
        remaining = len(chat_manager.online_user_ids())
        await chat_manager.broadcast({"event": "chat_users_count", "payload": {"count": remaining}})
