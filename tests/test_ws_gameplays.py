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


async def test_ws_gameplays_subscribe_game_and_broadcast(
    ws_client_factory: Callable[[], AsyncClient],
    auth_token: str,
    registered_user: dict[str, object],
) -> None:
    from gameapi.services.event_bus import event_bus

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

        await ws.send_json({"event": "subscribe_game", "payload": {"game_id": "game-123"}})
        assert await ws.receive_json() == {
            "event": "subscribed",
            "payload": {"game_id": "game-123"},
        }
        assert event_bus.channel_subscriber_count("game-123") == 1

        async with (
            ws_client_factory() as client_2,
            aconnect_ws(
                "ws://test/api/v2/ws/gameplays",
                client=client_2,
            ) as ws_2,
        ):
            await ws_2.send_json({"event": "auth", "payload": {"token": auth_token}})
            assert await ws_2.receive_json() == {
                "event": "auth_ok",
                "payload": {"user_id": str(registered_user["id"])},
            }
            await ws_2.send_json(
                {
                    "event": "broadcast_to_game",
                    "payload": {"game_id": "game-123", "message": "hello"},
                }
            )
            assert await ws_2.receive_json() == {
                "event": "broadcast_sent",
                "payload": {"game_id": "game-123"},
            }
            assert await ws.receive_json() == {
                "event": "game_message",
                "payload": {"from": str(registered_user["id"]), "message": "hello"},
            }


async def test_ws_gameplays_unsubscribe_game(
    ws_client_factory: Callable[[], AsyncClient],
    auth_token: str,
    registered_user: dict[str, object],
) -> None:
    from gameapi.services.event_bus import event_bus

    async with (
        ws_client_factory() as client,
        aconnect_ws(
            "ws://test/api/v2/ws/gameplays",
            client=client,
        ) as ws,
    ):
        await ws.send_json({"event": "auth", "payload": {"token": auth_token}})
        await ws.receive_json()

        await ws.send_json({"event": "subscribe_game", "payload": {"game_id": "game-abc"}})
        assert await ws.receive_json() == {
            "event": "subscribed",
            "payload": {"game_id": "game-abc"},
        }
        assert event_bus.channel_subscriber_count("game-abc") == 1

        await ws.send_json({"event": "unsubscribe_game", "payload": {"game_id": "game-abc"}})
        assert await ws.receive_json() == {
            "event": "unsubscribed",
            "payload": {"game_id": "game-abc"},
        }
        assert event_bus.channel_subscriber_count("game-abc") == 0


async def test_ws_gameplays_switch_game_auto_unsubscribes_previous(
    ws_client_factory: Callable[[], AsyncClient],
    auth_token: str,
    registered_user: dict[str, object],
) -> None:
    from gameapi.services.event_bus import event_bus

    async with (
        ws_client_factory() as client,
        aconnect_ws(
            "ws://test/api/v2/ws/gameplays",
            client=client,
        ) as ws,
    ):
        await ws.send_json({"event": "auth", "payload": {"token": auth_token}})
        await ws.receive_json()

        await ws.send_json({"event": "subscribe_game", "payload": {"game_id": "game-1"}})
        await ws.receive_json()
        assert event_bus.channel_subscriber_count("game-1") == 1

        await ws.send_json({"event": "subscribe_game", "payload": {"game_id": "game-2"}})
        assert await ws.receive_json() == {
            "event": "subscribed",
            "payload": {"game_id": "game-2"},
        }
        assert event_bus.channel_subscriber_count("game-1") == 0
        assert event_bus.channel_subscriber_count("game-2") == 1


async def test_ws_gameplays_disconnect_cleanup(
    ws_client_factory: Callable[[], AsyncClient],
    auth_token: str,
    registered_user: dict[str, object],
) -> None:
    from gameapi.api.v2.ws.manager import gameplays_manager
    from gameapi.services.event_bus import event_bus

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
            await ws.send_json(
                {
                    "event": "subscribe_game",
                    "payload": {"game_id": "game-disconnect"},
                }
            )
            assert await ws.receive_json() == {
                "event": "subscribed",
                "payload": {"game_id": "game-disconnect"},
            }
            assert event_bus.channel_subscriber_count("game-disconnect") == 1
            await ws.close()
    except BaseExceptionGroup as exc:
        if not _contains_end_of_stream(exc):
            raise

    assert str(registered_user["id"]) not in gameplays_manager._connections
    assert event_bus.channel_subscriber_count("game-disconnect") == 0
