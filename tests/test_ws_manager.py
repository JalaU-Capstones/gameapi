from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from gameapi.api.v2.ws.manager import ConnectionManager


@pytest.mark.asyncio
async def test_send_to_unknown_user_returns_false() -> None:
    manager = ConnectionManager()

    result = await manager.send_to("offline-user", {"event": "update"})

    assert result is False
    assert manager.online_user_ids() == []


@pytest.mark.asyncio
async def test_manager_tracks_multiple_sockets_and_replaces_single_disconnect() -> None:
    manager = ConnectionManager()
    first = AsyncMock()
    second = AsyncMock()

    await manager.connect("user", first)
    await manager.connect("user", second)

    assert manager.get_user_socket("user") in {first, second}
    assert manager.is_online("user") is True
    assert manager.online_user_ids() == ["user"]

    manager.disconnect("user", first)
    assert manager.get_user_socket("user") in {second, None}

    manager.disconnect("user")
    assert not manager.is_online("user")
    assert manager.online_user_ids() == []


@pytest.mark.asyncio
async def test_manager_revoke_methods_close_every_socket_for_user() -> None:
    manager = ConnectionManager()
    first = AsyncMock()
    second = AsyncMock()
    await manager.connect("user", first)
    await manager.connect("user", second)

    assert await manager.revoke_user_socket("user", "session_replaced") is True
    first.close.assert_awaited_once_with(code=4409, reason="session_replaced")
    second.close.assert_awaited_once_with(code=4409, reason="session_replaced")
    assert manager.online_user_ids() == []
    assert await manager.revoke_user_socket("missing", "session_replaced") is False

    await manager.connect("user", first)
    await manager.connect("user", second)
    assert await manager.revoke_all_user_sockets("user") == 2
    first.close.assert_awaited_with(code=4409, reason="session_replaced")
    second.close.assert_awaited_with(code=4409, reason="session_replaced")
    assert await manager.revoke_all_user_sockets("missing") == 0


@pytest.mark.asyncio
async def test_send_to_disconnects_socket_that_raises_runtime_error() -> None:
    manager = ConnectionManager()
    websocket = AsyncMock()
    websocket.send_json.side_effect = RuntimeError("socket closed")
    await manager.connect("user", websocket)

    result = await manager.send_to("user", {"event": "update"})

    assert result is False
    assert not manager.is_online("user")
    websocket.send_json.assert_awaited_once_with({"event": "update"})


@pytest.mark.asyncio
async def test_broadcast_uses_active_connections_only() -> None:
    manager = ConnectionManager()
    alive = AsyncMock()
    closed = AsyncMock()
    closed.send_json.side_effect = RuntimeError("socket closed")

    await manager.connect("user", alive)
    await manager.connect("user", closed)

    await manager.broadcast({"event": "update"})

    alive.send_json.assert_awaited_once_with({"event": "update"})
    closed.send_json.assert_awaited_once_with({"event": "update"})
    assert manager.online_user_ids() == ["user"]
    assert manager.get_user_socket("user") is alive


async def test_session_takeover_revokes_every_active_socket_for_current_user(
    client: AsyncClient,
    registered_user: dict[str, object],
) -> None:
    from gameapi.api.v2.ws.manager import gameplays_manager, presence_manager

    login = await client.post(
        "/api/v2/auth/login",
        json={"email": registered_user["email"], "password": "password123"},
    )
    assert login.status_code == 200, login.text

    gameplay_socket = AsyncMock()
    presence_socket = AsyncMock()
    await gameplays_manager.connect(str(registered_user["id"]), gameplay_socket)
    await presence_manager.connect(str(registered_user["id"]), presence_socket)

    response = await client.post("/api/v2/auth/session/takeover")

    assert response.status_code == 204, response.text
    gameplay_socket.close.assert_awaited_once_with(code=4409, reason="session_replaced")
    presence_socket.close.assert_awaited_once_with(code=4409, reason="session_replaced")
    assert gameplays_manager.online_user_ids() == []
    assert presence_manager.online_user_ids() == []
