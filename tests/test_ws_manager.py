import asyncio
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
async def test_revoke_all_keeps_socket_registered_until_close_finishes() -> None:
    manager = ConnectionManager()
    websocket = AsyncMock()
    finish_close = asyncio.Event()

    async def delayed_close(*, code: int, reason: str) -> None:
        assert code == 4409
        assert reason == "session_replaced"
        await finish_close.wait()

    websocket.close.side_effect = delayed_close
    await manager.connect("user", websocket)

    revoke = asyncio.create_task(manager.revoke_all_user_sockets("user"))
    await asyncio.sleep(0)

    assert manager.get_user_socket("user") is websocket
    assert revoke.done() is False

    finish_close.set()
    assert await revoke == 1
    assert manager.get_user_socket("user") is None


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


@pytest.mark.asyncio
async def test_disconnect_ignores_stale_socket_for_active_user() -> None:
    manager = ConnectionManager()
    active = AsyncMock()
    stale = AsyncMock()

    await manager.connect("user", active)

    manager.disconnect("user", stale)
    assert manager.is_online("user") is True
    assert manager.get_user_socket("user") is active

    manager.disconnect("user", active)
    assert not manager.is_online("user")
    assert manager.online_user_ids() == []


@pytest.mark.asyncio
async def test_revoke_user_socket_false_for_unknown_user() -> None:
    manager = ConnectionManager()

    result = await manager.revoke_user_socket("missing", "session_replaced")

    assert result is False
    assert manager.online_user_ids() == []


@pytest.mark.asyncio
async def test_manager_handles_concurrent_register_and_remove_edge_cases() -> None:
    manager = ConnectionManager()
    first = AsyncMock()
    second = AsyncMock()
    third = AsyncMock()

    await manager.connect("user", first)
    manager.disconnect("user", second)
    assert manager.get_user_socket("user") is first

    await manager.connect("user", second)
    manager.disconnect("user", first)
    assert manager.get_user_socket("user") in {second, None}

    await manager.connect("user", third)
    manager.disconnect("user", second)
    assert manager.get_user_socket("user") in {third, None}

    manager.disconnect("user", third)
    assert not manager.is_online("user")
    assert manager.online_user_ids() == []


@pytest.mark.asyncio
async def test_get_user_socket_and_disconnect_ignore_missing_entries() -> None:
    manager = ConnectionManager()

    assert manager.get_user_socket("missing") is None
    manager.disconnect("missing")
    assert manager.online_user_ids() == []


@pytest.mark.asyncio
async def test_revoke_methods_handle_close_failures_and_broadcast_excludes_users() -> None:
    manager = ConnectionManager()
    left = AsyncMock()
    left.close.side_effect = RuntimeError("close failed")
    right = AsyncMock()
    right.close.side_effect = RuntimeError("close failed")

    await manager.connect("user", left)
    await manager.connect("user", right)
    assert await manager.revoke_user_socket("user", "session_replaced") is False
    assert await manager.revoke_all_user_sockets("user") == 0

    await manager.connect("user", left)
    await manager.connect("user", right)
    await manager.broadcast({"event": "ping"}, exclude={"user"})
    left.send_json.assert_not_awaited()
    right.send_json.assert_not_awaited()


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
