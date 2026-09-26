from __future__ import annotations

from typing import Any

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        self._connections[user_id] = websocket

    def disconnect(self, user_id: str) -> None:
        self._connections.pop(user_id, None)

    def is_online(self, user_id: str) -> bool:
        return user_id in self._connections

    def online_user_ids(self) -> list[str]:
        return list(self._connections)

    async def send_to(self, user_id: str, message: dict[str, Any]) -> bool:
        websocket = self._connections.get(user_id)
        if websocket is None:
            return False
        try:
            await websocket.send_json(message)
            return True
        except (WebSocketDisconnect, RuntimeError):
            self.disconnect(user_id)
            return False

    async def broadcast(self, message: dict[str, Any], exclude: set[str] | None = None) -> None:
        exclude = exclude or set()
        for user_id in list(self._connections):
            if user_id in exclude:
                continue
            await self.send_to(user_id, message)


gameplays_manager = ConnectionManager()
presence_manager = ConnectionManager()
