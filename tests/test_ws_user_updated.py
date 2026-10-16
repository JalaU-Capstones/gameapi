from __future__ import annotations

import asyncio
from collections.abc import Callable

from httpx import AsyncClient
from httpx_ws import aconnect_ws


async def test_name_change_broadcasts_user_updated(
    client: AsyncClient,
    ws_client_factory: Callable[[], AsyncClient],
    auth_token: str,
    auth_headers: dict[str, str],
    registered_user: dict[str, object],
) -> None:
    user_id = str(registered_user["id"])
    async with (
        ws_client_factory() as ws_http,
        aconnect_ws("ws://test/api/v2/ws/presence", client=ws_http) as ws,
    ):
        await ws.send_json({"event": "auth", "payload": {"token": auth_token}})
        assert (await ws.receive_json())["event"] == "auth_ok"

        response = await client.put(
            f"/api/v2/users/{user_id}",
            json={"name": "New Name"},
            headers=auth_headers,
        )
        assert response.status_code == 204

        message = await asyncio.wait_for(ws.receive_json(), timeout=3)
        assert message == {"event": "user_updated", "payload": {"user_id": user_id}}


async def test_password_change_does_not_broadcast_user_updated(
    client: AsyncClient,
    ws_client_factory: Callable[[], AsyncClient],
    auth_token: str,
    auth_headers: dict[str, str],
    registered_user: dict[str, object],
) -> None:
    user_id = str(registered_user["id"])
    async with (
        ws_client_factory() as ws_http,
        aconnect_ws("ws://test/api/v2/ws/presence", client=ws_http) as ws,
    ):
        await ws.send_json({"event": "auth", "payload": {"token": auth_token}})
        assert (await ws.receive_json())["event"] == "auth_ok"

        response = await client.put(
            f"/api/v2/users/{user_id}",
            json={"password": "newpassword123"},
            headers=auth_headers,
        )
        assert response.status_code == 204

        # If user_updated had been sent it would arrive before this pong.
        await ws.send_json({"event": "ping"})
        message = await asyncio.wait_for(ws.receive_json(), timeout=3)
        assert message == {"event": "pong", "payload": {}}
