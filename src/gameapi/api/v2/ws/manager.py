from __future__ import annotations

from typing import Any

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}

    def get_user_socket(self, user_id: str) -> WebSocket | None:
        sockets = self._connections.get(user_id)
        if not sockets:
            return None
        return next(iter(sockets))

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        self._connections.setdefault(user_id, set()).add(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket | None = None) -> None:
        sockets = self._connections.get(user_id)
        if sockets is None:
            return

        if websocket is not None:
            sockets.discard(websocket)
        else:
            sockets.clear()

        if not sockets:
            self._connections.pop(user_id, None)

    def is_online(self, user_id: str) -> bool:
        return user_id in self._connections and bool(self._connections[user_id])

    def online_user_ids(self) -> list[str]:
        return [user_id for user_id, sockets in self._connections.items() if sockets]

    async def revoke_user_socket(self, user_id: str, reason: str) -> bool:
        sockets = self._connections.pop(user_id, None)
        if not sockets:
            return False

        closed = 0
        for websocket in list(sockets):
            try:
                await websocket.close(code=4409, reason=reason)
                closed += 1
            except Exception:
                pass
        return closed > 0

    async def revoke_all_user_sockets(self, user_id: str) -> int:
        sockets = self._connections.pop(user_id, None)
        if not sockets:
            return 0

        closed = 0
        for websocket in list(sockets):
            try:
                await websocket.close(code=4409, reason="session_replaced")
                closed += 1
            except Exception:
                pass
        return closed

    async def send_to(self, user_id: str, message: dict[str, Any]) -> bool:
        sockets = self._connections.get(user_id)
        if not sockets:
            return False

        delivered = False
        for websocket in list(sockets):
            try:
                await websocket.send_json(message)
                delivered = True
            except (WebSocketDisconnect, RuntimeError):
                self.disconnect(user_id, websocket)
        return delivered

    async def broadcast(self, message: dict[str, Any], exclude: set[str] | None = None) -> None:
        exclude = exclude or set()
        for user_id in list(self._connections):
            if user_id in exclude:
                continue
            await self.send_to(user_id, message)


gameplays_manager = ConnectionManager()
presence_manager = ConnectionManager()
