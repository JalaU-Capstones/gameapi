from __future__ import annotations

from collections.abc import Callable

import pytest
from anyio import EndOfStream
from httpx import AsyncClient
from httpx_ws import WebSocketDisconnect, aconnect_ws


def _contains_end_of_stream(exc: BaseException) -> bool:
    if isinstance(exc, EndOfStream):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_contains_end_of_stream(sub) for sub in exc.exceptions)
    return False


async def test_ws_gameplays_auth_timeout(
    ws_client_factory: Callable[[], AsyncClient],
) -> None:
    async with (
        ws_client_factory() as client,
        aconnect_ws(
            "ws://test/api/v2/ws/gameplays",
            client=client,
        ) as ws,
    ):
        with pytest.raises(WebSocketDisconnect) as exc:
            await ws.receive_json()
        assert exc.value.code == 4408


async def test_ws_gameplays_wrong_first_event(
    ws_client_factory: Callable[[], AsyncClient],
) -> None:
    async with (
        ws_client_factory() as client,
        aconnect_ws(
            "ws://test/api/v2/ws/gameplays",
            client=client,
        ) as ws,
    ):
        await ws.send_json({"event": "not_auth"})
        assert await ws.receive_json() == {
            "event": "auth_error",
            "payload": {"reason": "expected_auth_event"},
        }
        with pytest.raises(WebSocketDisconnect) as exc:
            await ws.receive_json()
        assert exc.value.code == 4401


async def test_ws_gameplays_invalid_jwt(
    ws_client_factory: Callable[[], AsyncClient],
) -> None:
    async with (
        ws_client_factory() as client,
        aconnect_ws(
            "ws://test/api/v2/ws/gameplays",
            client=client,
        ) as ws,
    ):
        await ws.send_json({"event": "auth", "payload": {"token": "invalid"}})
        assert await ws.receive_json() == {
            "event": "auth_error",
            "payload": {"reason": "invalid_token"},
        }
        with pytest.raises(WebSocketDisconnect) as exc:
            await ws.receive_json()
        assert exc.value.code == 4401


async def test_ws_gameplays_valid_auth(
    ws_client_factory: Callable[[], AsyncClient],
    auth_token: str,
    registered_user: dict[str, object],
) -> None:
    async with (
        ws_client_factory() as client,
        aconnect_ws(
            "ws://test/api/v2/ws/gameplays",
            client=client,
        ) as ws,
    ):
        await ws.send_json({"event": "auth", "payload": {"token": auth_token}})
        msg = await ws.receive_json()
        assert msg == {
            "event": "auth_ok",
            "payload": {"user_id": str(registered_user["id"])},
        }


async def test_ws_gameplays_ping_pong(
    ws_client_factory: Callable[[], AsyncClient],
    auth_token: str,
    registered_user: dict[str, object],
) -> None:
    async with (
        ws_client_factory() as client,
        aconnect_ws(
            "ws://test/api/v2/ws/gameplays",
            client=client,
        ) as ws,
    ):
        await ws.send_json({"event": "auth", "payload": {"token": auth_token}})
        await ws.receive_json()
        await ws.send_json({"event": "ping"})
        assert await ws.receive_json() == {"event": "pong", "payload": {}}


async def test_ws_gameplays_unknown_event(
    ws_client_factory: Callable[[], AsyncClient],
    auth_token: str,
    registered_user: dict[str, object],
) -> None:
    async with (
        ws_client_factory() as client,
        aconnect_ws(
            "ws://test/api/v2/ws/gameplays",
            client=client,
        ) as ws,
    ):
        await ws.send_json({"event": "auth", "payload": {"token": auth_token}})
        await ws.receive_json()

        await ws.send_json({"event": "unknown"})
        assert await ws.receive_json() == {
            "event": "error",
            "payload": {
                "code": "NOT_IMPLEMENTED",
                "message": "Event not implemented yet: unknown",
            },
        }


async def test_ws_gameplays_missing_event_field(
    ws_client_factory: Callable[[], AsyncClient],
    auth_token: str,
    registered_user: dict[str, object],
) -> None:
    async with (
        ws_client_factory() as client,
        aconnect_ws(
            "ws://test/api/v2/ws/gameplays",
            client=client,
        ) as ws,
    ):
        await ws.send_json({"event": "auth", "payload": {"token": auth_token}})
        await ws.receive_json()

        await ws.send_json({"not_event": "x"})
        assert await ws.receive_json() == {
            "event": "error",
            "payload": {"code": "INVALID_EVENT", "message": "Missing 'event' field"},
        }


async def test_ws_gameplays_disconnect_cleanup(
    ws_client_factory: Callable[[], AsyncClient],
    auth_token: str,
    registered_user: dict[str, object],
) -> None:
    from gameapi.api.v2.ws.manager import gameplays_manager

    try:
        async with (
            ws_client_factory() as client,
            aconnect_ws(
                "ws://test/api/v2/ws/gameplays",
                client=client,
            ) as ws,
        ):
            await ws.send_json({"event": "auth", "payload": {"token": auth_token}})
            assert await ws.receive_json() == {
                "event": "auth_ok",
                "payload": {"user_id": str(registered_user["id"])},
            }
            await ws.close()
    except BaseExceptionGroup as exc:
        if not _contains_end_of_stream(exc):
            raise

    assert str(registered_user["id"]) not in gameplays_manager._connections
