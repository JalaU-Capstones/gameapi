from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest
from anyio import EndOfStream
from httpx import AsyncClient
from httpx_ws import aconnect_ws


async def _send_recv(ws: object, event_dict: dict[str, object]) -> dict[str, object]:
    await ws.send_json(event_dict)
    return await ws.receive_json()


def _contains_end_of_stream(exc: BaseException) -> bool:
    if isinstance(exc, EndOfStream):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_contains_end_of_stream(sub) for sub in exc.exceptions)
    return False


@pytest.mark.asyncio
async def test_subscribe_game_missing_game_id(
    ws_client_factory: Callable[[], AsyncClient],
    auth_token: str,
) -> None:
    async with (
        ws_client_factory() as client,
        aconnect_ws("ws://test/api/v2/ws/gameplays", client=client) as ws,
    ):
        await ws.send_json({"event": "auth", "payload": {"token": auth_token}})
        await ws.receive_json()

        response = await _send_recv(ws, {"event": "subscribe_game", "payload": {}})
        assert response == {
            "event": "error",
            "payload": {"code": "INVALID_PAYLOAD", "message": "Missing 'game_id' field"},
        }


@pytest.mark.asyncio
async def test_subscribe_game_with_invalid_payload_type(
    ws_client_factory: Callable[[], AsyncClient],
    auth_token: str,
) -> None:
    async with (
        ws_client_factory() as client,
        aconnect_ws("ws://test/api/v2/ws/gameplays", client=client) as ws,
    ):
        await ws.send_json({"event": "auth", "payload": {"token": auth_token}})
        await ws.receive_json()

        response = await _send_recv(ws, {"event": "subscribe_game", "payload": "not-a-dict"})
        assert response == {
            "event": "error",
            "payload": {"code": "INVALID_PAYLOAD", "message": "Missing 'payload'"},
        }


@pytest.mark.asyncio
async def test_unsubscribe_game_missing_game_id(
    ws_client_factory: Callable[[], AsyncClient],
    auth_token: str,
) -> None:
    async with (
        ws_client_factory() as client,
        aconnect_ws("ws://test/api/v2/ws/gameplays", client=client) as ws,
    ):
        await ws.send_json({"event": "auth", "payload": {"token": auth_token}})
        await ws.receive_json()

        response = await _send_recv(ws, {"event": "unsubscribe_game", "payload": {}})
        assert response == {
            "event": "error",
            "payload": {"code": "INVALID_PAYLOAD", "message": "Missing 'game_id' field"},
        }


@pytest.mark.asyncio
async def test_unsubscribe_game_when_not_subscribed(
    ws_client_factory: Callable[[], AsyncClient],
    auth_token: str,
) -> None:
    async with (
        ws_client_factory() as client,
        aconnect_ws("ws://test/api/v2/ws/gameplays", client=client) as ws,
    ):
        await ws.send_json({"event": "auth", "payload": {"token": auth_token}})
        await ws.receive_json()

        response = await _send_recv(
            ws,
            {"event": "unsubscribe_game", "payload": {"game_id": "game-zzz"}},
        )
        assert response == {
            "event": "unsubscribed",
            "payload": {"game_id": "game-zzz"},
        }


@pytest.mark.asyncio
async def test_create_game_when_already_subscribed_to_other_game(
    ws_client_factory: Callable[[], AsyncClient],
    registered_user_a: dict[str, object],
    registered_user_b: dict[str, object],
    auth_token_a: str,
    auth_token_b: str,
) -> None:
    from gameapi.services.event_bus import event_bus

    async with (
        ws_client_factory() as ca,
        aconnect_ws("ws://test/api/v2/ws/gameplays", client=ca) as wsa,
        ws_client_factory() as cb,
        aconnect_ws("ws://test/api/v2/ws/gameplays", client=cb) as wsb,
    ):
        await _send_recv(wsa, {"event": "auth", "payload": {"token": auth_token_a}})
        await _send_recv(wsb, {"event": "auth", "payload": {"token": auth_token_b}})

        await wsa.send_json({"event": "subscribe_game", "payload": {"game_id": "game-old"}})
        assert await wsa.receive_json() == {
            "event": "subscribed",
            "payload": {"game_id": "game-old"},
        }
        assert event_bus.channel_subscriber_count("game-old") == 1

        response = await _send_recv(
            wsa,
            {"event": "create_game", "payload": {"guest_id": str(registered_user_b["id"])}},
        )
        assert response["event"] == "game_created"
        game_id = response["payload"]["game_id"]

        assert event_bus.channel_subscriber_count("game-old") == 0
        assert event_bus.channel_subscriber_count(game_id) == 1
        assert str(registered_user_a["id"]) != str(registered_user_b["id"])


@pytest.mark.asyncio
async def test_accept_invitation_switches_channel(
    ws_client_factory: Callable[[], AsyncClient],
    registered_user_b: dict[str, object],
    auth_token_a: str,
    auth_token_b: str,
) -> None:
    from gameapi.services.event_bus import event_bus

    async with (
        ws_client_factory() as ca,
        aconnect_ws("ws://test/api/v2/ws/gameplays", client=ca) as wsa,
        ws_client_factory() as cb,
        aconnect_ws("ws://test/api/v2/ws/gameplays", client=cb) as wsb,
    ):
        await _send_recv(wsa, {"event": "auth", "payload": {"token": auth_token_a}})
        await _send_recv(wsb, {"event": "auth", "payload": {"token": auth_token_b}})

        await wsb.send_json({"event": "subscribe_game", "payload": {"game_id": "game-x"}})
        assert await wsb.receive_json() == {"event": "subscribed", "payload": {"game_id": "game-x"}}

        res_created = await _send_recv(
            wsa,
            {"event": "create_game", "payload": {"guest_id": str(registered_user_b["id"])}},
        )
        game_id = res_created["payload"]["game_id"]
        assert (await wsb.receive_json())["event"] == "invitation_received"

        await wsb.send_json({"event": "accept_invitation", "payload": {"game_id": game_id}})
        await wsb.receive_json()
        await wsa.receive_json()

        assert event_bus.channel_subscriber_count("game-x") == 0
        assert event_bus.channel_subscriber_count(game_id) == 2


@pytest.mark.asyncio
async def test_play_move_on_finished_game_returns_error(
    ws_client_factory: Callable[[], AsyncClient],
    registered_user_b: dict[str, object],
    auth_token_a: str,
    auth_token_b: str,
) -> None:
    async with (
        ws_client_factory() as ca,
        aconnect_ws("ws://test/api/v2/ws/gameplays", client=ca) as wsa,
        ws_client_factory() as cb,
        aconnect_ws("ws://test/api/v2/ws/gameplays", client=cb) as wsb,
    ):
        await _send_recv(wsa, {"event": "auth", "payload": {"token": auth_token_a}})
        await _send_recv(wsb, {"event": "auth", "payload": {"token": auth_token_b}})

        response = await _send_recv(
            wsa,
            {"event": "create_game", "payload": {"guest_id": str(registered_user_b["id"])}},
        )
        game_id = response["payload"]["game_id"]
        await wsb.receive_json()

        await wsb.send_json({"event": "accept_invitation", "payload": {"game_id": game_id}})
        await wsb.receive_json()
        await wsa.receive_json()

        for move in [
            (0, 0),
            (1, 0),
            (0, 1),
            (1, 1),
            (0, 2),
        ]:
            sender = wsa if move[0] in (0, 0, 0, 1, 0) and move[1] in (0, 0, 1, 1, 2) else wsb
            pass

        sequence = [
            (wsa, 0, 0),
            (wsb, 1, 0),
            (wsa, 0, 1),
            (wsb, 1, 1),
            (wsa, 0, 2),
        ]
        for sender, row, col in sequence:
            await sender.send_json(
                {"event": "play_move", "payload": {"game_id": game_id, "row": row, "col": col}}
            )
            await sender.receive_json()
            await (wsb if sender is wsa else wsa).receive_json()

        error = await _send_recv(
            wsa,
            {"event": "play_move", "payload": {"game_id": game_id, "row": 2, "col": 2}},
        )
        assert error["event"] == "error"
        assert error["payload"]["code"] == "GAME_NOT_ACTIVE"


@pytest.mark.asyncio
async def test_disconnect_during_active_game_publishes_abandon(
    ws_client_factory: Callable[[], AsyncClient],
    registered_user_b: dict[str, object],
    auth_token_a: str,
    auth_token_b: str,
) -> None:
    try:
        async with (
            ws_client_factory() as ca,
            aconnect_ws("ws://test/api/v2/ws/gameplays", client=ca) as wsa,
            ws_client_factory() as cb,
            aconnect_ws("ws://test/api/v2/ws/gameplays", client=cb) as wsb,
        ):
            await _send_recv(wsa, {"event": "auth", "payload": {"token": auth_token_a}})
            await _send_recv(wsb, {"event": "auth", "payload": {"token": auth_token_b}})

            response = await _send_recv(
                wsa,
                {"event": "create_game", "payload": {"guest_id": str(registered_user_b["id"])}},
            )
            game_id = response["payload"]["game_id"]
            await wsb.receive_json()

            await wsb.send_json({"event": "accept_invitation", "payload": {"game_id": game_id}})
            await wsb.receive_json()
            await wsa.receive_json()

            await wsb.close()
            res_end = await wsa.receive_json()
            assert res_end["event"] == "game_ended"
            assert res_end["payload"]["reason"] == "abandon"
    except BaseExceptionGroup as exc:
        if not _contains_end_of_stream(exc):
            raise


@pytest.mark.asyncio
async def test_disconnect_during_pending_invitation_is_silent(
    ws_client_factory: Callable[[], AsyncClient],
    registered_user_b: dict[str, object],
    auth_token_a: str,
    auth_token_b: str,
) -> None:
    try:
        async with (
            ws_client_factory() as ca,
            aconnect_ws("ws://test/api/v2/ws/gameplays", client=ca) as wsa,
            ws_client_factory() as cb,
            aconnect_ws("ws://test/api/v2/ws/gameplays", client=cb) as wsb,
        ):
            await _send_recv(wsa, {"event": "auth", "payload": {"token": auth_token_a}})
            await _send_recv(wsb, {"event": "auth", "payload": {"token": auth_token_b}})

            response = await _send_recv(
                wsa,
                {"event": "create_game", "payload": {"guest_id": str(registered_user_b["id"])}},
            )
            game_id = response["payload"]["game_id"]
            await wsb.receive_json()

            await wsb.close()
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(wsa.receive_json(), timeout=0.5)

            assert game_id
    except BaseExceptionGroup as exc:
        if not _contains_end_of_stream(exc):
            raise


@pytest.mark.asyncio
async def test_disconnect_without_subscription_is_safe(
    ws_client_factory: Callable[[], AsyncClient],
    auth_token: str,
    registered_user: dict[str, object],
) -> None:
    try:
        async with (
            ws_client_factory() as client,
            aconnect_ws("ws://test/api/v2/ws/gameplays", client=client) as ws,
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
