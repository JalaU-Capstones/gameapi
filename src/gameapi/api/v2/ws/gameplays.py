from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, WebSocket
from fastapi.websockets import WebSocketDisconnect

from gameapi.api.v2.ws.auth import authenticate_websocket
from gameapi.api.v2.ws.manager import gameplays_manager
from gameapi.services.event_bus import event_bus

logger = logging.getLogger(__name__)

router = APIRouter()


async def _handle_message(
    user_id: str,
    message: dict[str, Any],
    websocket: WebSocket,
    current_game_id: str | None,
) -> str | None:
    event = message.get("event") if isinstance(message, dict) else None
    if event is None:
        await websocket.send_json(
            {
                "event": "error",
                "payload": {"code": "INVALID_EVENT", "message": "Missing 'event' field"},
            }
        )
        return current_game_id

    if event == "ping":
        await websocket.send_json({"event": "pong", "payload": {}})
        return current_game_id

    if event == "subscribe_game":
        payload = message.get("payload") if isinstance(message, dict) else {}
        if not isinstance(payload, dict):
            await websocket.send_json(
                {
                    "event": "error",
                    "payload": {"code": "INVALID_PAYLOAD", "message": "Missing 'payload'"},
                }
            )
            return current_game_id

        next_game_id = payload.get("game_id")
        if not isinstance(next_game_id, str):
            await websocket.send_json(
                {
                    "event": "error",
                    "payload": {"code": "INVALID_GAME_ID", "message": "Missing 'game_id'"},
                }
            )
            return current_game_id

        if current_game_id is not None and current_game_id != next_game_id:
            event_bus.unsubscribe(current_game_id, user_id)

        async def _callback(event: dict[str, Any]) -> None:
            try:
                await websocket.send_json(event)
            except (WebSocketDisconnect, RuntimeError):
                logger.info(
                    "WebSocket disconnected while sending gameplay event for user '%s'",
                    user_id,
                )

        event_bus.subscribe(next_game_id, user_id, _callback)
        await websocket.send_json({"event": "subscribed", "payload": {"game_id": next_game_id}})
        return next_game_id

    if event == "unsubscribe_game":
        payload = message.get("payload") if isinstance(message, dict) else {}
        if not isinstance(payload, dict):
            await websocket.send_json(
                {
                    "event": "error",
                    "payload": {"code": "INVALID_PAYLOAD", "message": "Missing 'payload'"},
                }
            )
            return current_game_id

        game_id = payload.get("game_id")
        if not isinstance(game_id, str):
            await websocket.send_json(
                {
                    "event": "error",
                    "payload": {"code": "INVALID_GAME_ID", "message": "Missing 'game_id'"},
                }
            )
            return current_game_id

        event_bus.unsubscribe(game_id, user_id)
        await websocket.send_json({"event": "unsubscribed", "payload": {"game_id": game_id}})
        if current_game_id == game_id:
            return None
        return current_game_id

    # TODO(B3): remove this synthetic event once real game events exist.
    if event == "broadcast_to_game":
        payload = message.get("payload") if isinstance(message, dict) else {}
        if not isinstance(payload, dict):
            await websocket.send_json(
                {
                    "event": "error",
                    "payload": {"code": "INVALID_PAYLOAD", "message": "Missing 'payload'"},
                }
            )
            return current_game_id

        game_id = payload.get("game_id")
        message_text = payload.get("message")
        if not isinstance(game_id, str) or not isinstance(message_text, str):
            await websocket.send_json(
                {
                    "event": "error",
                    "payload": {
                        "code": "INVALID_GAME_ID",
                        "message": "Missing 'game_id' or 'message'",
                    },
                }
            )
            return current_game_id

        await event_bus.publish(
            game_id,
            {"event": "game_message", "payload": {"from": user_id, "message": message_text}},
        )
        await websocket.send_json({"event": "broadcast_sent", "payload": {"game_id": game_id}})
        return current_game_id

    await websocket.send_json(
        {
            "event": "error",
            "payload": {
                "code": "NOT_IMPLEMENTED",
                "message": f"Event not implemented yet: {event}",
            },
        }
    )
    return current_game_id


@router.websocket("/gameplays")
async def gameplays_websocket(websocket: WebSocket) -> None:
    user_id = await authenticate_websocket(websocket)
    if user_id is None:
        return

    await gameplays_manager.connect(user_id, websocket)
    await websocket.send_json({"event": "auth_ok", "payload": {"user_id": user_id}})

    current_game_id: str | None = None

    try:
        while True:
            message = await websocket.receive_json()
            current_game_id = await _handle_message(user_id, message, websocket, current_game_id)
    except WebSocketDisconnect:
        pass
    finally:
        if current_game_id is not None:
            event_bus.unsubscribe(current_game_id, user_id)
        gameplays_manager.disconnect(user_id)
