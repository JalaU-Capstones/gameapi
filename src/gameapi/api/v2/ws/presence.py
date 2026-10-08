from __future__ import annotations

from typing import Any

from fastapi import APIRouter, WebSocket
from fastapi.websockets import WebSocketDisconnect

from gameapi.api.v2.ws.auth import authenticate_websocket
from gameapi.api.v2.ws.manager import presence_manager

router = APIRouter()


async def _handle_message(user_id: str, message: dict[str, Any], websocket: WebSocket) -> None:
    event = message.get("event") if isinstance(message, dict) else None
    if event is None:
        await websocket.send_json(
            {
                "event": "error",
                "payload": {"code": "INVALID_EVENT", "message": "Missing 'event' field"},
            }
        )
        return

    if event == "ping":
        await websocket.send_json({"event": "pong", "payload": {}})
        return

    if event == "list_online_users":
        await websocket.send_json(
            {"event": "online_users", "payload": {"users": presence_manager.online_user_ids()}}
        )
        return

    await websocket.send_json(
        {
            "event": "error",
            "payload": {
                "code": "NOT_IMPLEMENTED",
                "message": f"Event not implemented yet: {event}",
            },
        }
    )


@router.websocket("/presence")
async def presence_websocket(websocket: WebSocket) -> None:
    user_id = await authenticate_websocket(websocket)
    if user_id is None:
        return

    await presence_manager.connect(user_id, websocket)
    await websocket.send_json({"event": "auth_ok", "payload": {"user_id": user_id}})
    await presence_manager.broadcast(
        {"event": "user_online", "payload": {"user_id": user_id}},
        exclude={user_id},
    )

    try:
        while True:
            message = await websocket.receive_json()
            await _handle_message(user_id, message, websocket)
    except WebSocketDisconnect:
        pass
    finally:
        presence_manager.disconnect(user_id, websocket)
        await presence_manager.broadcast(
            {"event": "user_offline", "payload": {"user_id": user_id}},
            exclude={user_id},
        )
