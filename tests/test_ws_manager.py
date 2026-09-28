from unittest.mock import AsyncMock

import pytest

from gameapi.api.v2.ws.manager import ConnectionManager


@pytest.mark.asyncio
async def test_send_to_unknown_user_returns_false() -> None:
    manager = ConnectionManager()

    result = await manager.send_to("offline-user", {"event": "update"})

    assert result is False
    assert manager.online_user_ids() == []


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
