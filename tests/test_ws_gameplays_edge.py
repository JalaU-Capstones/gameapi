from __future__ import annotations

import asyncio
from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest
from anyio import EndOfStream
from httpx import AsyncClient
from httpx_ws import aconnect_ws

from gameapi.api.v2.ws import gameplays


async def _send_recv(ws: object, event_dict: dict[str, object]) -> dict[str, object]:
    await ws.send_json(event_dict)
    return await ws.receive_json()


def _contains_end_of_stream(exc: BaseException) -> bool:
    if isinstance(exc, EndOfStream):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_contains_end_of_stream(sub) for sub in exc.exceptions)
    return False


async def test_schedule_abandon_abandons_when_player_does_not_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    abandon = AsyncMock()
    monkeypatch.setattr(gameplays, "ABANDON_GRACE_SECONDS", 0)
    monkeypatch.setattr(gameplays, "_abandon_game", abandon)

    gameplays._schedule_abandon("user-id", "game-id")
    await gameplays._pending_abandons["user-id"]

    abandon.assert_awaited_once_with("user-id", "game-id")
    assert "user-id" not in gameplays._pending_abandons


async def test_reset_pending_abandons_cancels_scheduled_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    abandon = AsyncMock()
    monkeypatch.setattr(gameplays, "ABANDON_GRACE_SECONDS", 60)
    monkeypatch.setattr(gameplays, "_abandon_game", abandon)

    gameplays._schedule_abandon("user-id", "game-id")
    task = gameplays._pending_abandons["user-id"]
    await asyncio.sleep(0)
    gameplays.reset_pending_abandons()

    with pytest.raises(asyncio.CancelledError):
        await task
    abandon.assert_not_awaited()
    assert gameplays._pending_abandons == {}


async def test_schedule_abandon_logs_failure_and_clears_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    abandon = AsyncMock(side_effect=RuntimeError("database unavailable"))
    monkeypatch.setattr(gameplays, "ABANDON_GRACE_SECONDS", 0)
    monkeypatch.setattr(gameplays, "_abandon_game", abandon)

    gameplays._schedule_abandon("user-id", "game-id")
    await gameplays._pending_abandons["user-id"]

    abandon.assert_awaited_once_with("user-id", "game-id")
    assert "user-id" not in gameplays._pending_abandons


async def test_schedule_abandon_keeps_game_when_player_resumes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    abandon = AsyncMock()
    monkeypatch.setattr(gameplays, "ABANDON_GRACE_SECONDS", 0)
    monkeypatch.setattr(gameplays, "_abandon_game", abandon)
    monkeypatch.setattr(gameplays.gameplays_manager, "is_online", lambda _: True)
    monkeypatch.setattr(gameplays.event_bus, "is_subscribed", lambda *_: True)

    gameplays._schedule_abandon("user-id", "game-id")
    await gameplays._pending_abandons["user-id"]

    abandon.assert_not_awaited()
    assert "user-id" not in gameplays._pending_abandons


async def test_schedule_abandon_replaces_previous_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gameplays, "ABANDON_GRACE_SECONDS", 60)
    gameplays._schedule_abandon("user-id", "first-game")
    previous_task = gameplays._pending_abandons["user-id"]

    gameplays._schedule_abandon("user-id", "second-game")
    current_task = gameplays._pending_abandons["user-id"]
    await asyncio.sleep(0)

    with pytest.raises(asyncio.CancelledError):
        await previous_task
    gameplays.reset_pending_abandons()
    with pytest.raises(asyncio.CancelledError):
        await current_task


async def test_create_game_uses_database_for_busy_checks(
    ws_client_factory: Callable[[], AsyncClient],
    db_session,
    registered_user: dict[str, object],
    registered_user_a: dict[str, object],
    registered_user_b: dict[str, object],
    auth_token: str,
    auth_token_a: str,
    auth_token_b: str,
) -> None:
    import uuid

    from gameapi.db.models.gameplay import Gameplay
    from gameapi.services.player_status import is_playing

    host_id = uuid.UUID(str(registered_user_a["id"]))
    busy_guest_id = uuid.UUID(str(registered_user_b["id"]))
    db_session.add(
        Gameplay(
            current_positions={"board": [[0, 0, 0], [0, 0, 0], [0, 0, 0]]},
            host_player=host_id,
            guest_player=busy_guest_id,
            player_turn=host_id,
            invitation_state="accepted",
            match_result=None,
        )
    )
    await db_session.commit()

    async with (
        ws_client_factory() as host_client,
        aconnect_ws("ws://test/api/v2/ws/gameplays", client=host_client) as host_ws,
        ws_client_factory() as busy_guest_client,
        aconnect_ws(
            "ws://test/api/v2/ws/gameplays",
            client=busy_guest_client,
        ) as busy_guest_ws,
        ws_client_factory() as available_guest_client,
        aconnect_ws(
            "ws://test/api/v2/ws/gameplays",
            client=available_guest_client,
        ) as available_guest_ws,
    ):
        await host_ws.send_json({"event": "auth", "payload": {"token": auth_token_a}})
        await host_ws.receive_json()
        await busy_guest_ws.send_json({"event": "auth", "payload": {"token": auth_token_b}})
        await busy_guest_ws.receive_json()
        await available_guest_ws.send_json({"event": "auth", "payload": {"token": auth_token}})
        await available_guest_ws.receive_json()

        busy_guest_response = await _send_recv(
            available_guest_ws,
            {"event": "create_game", "payload": {"guest_id": str(busy_guest_id)}},
        )
        assert busy_guest_response["payload"]["code"] == "USER_BUSY"
        assert is_playing(str(busy_guest_id))

        host_busy_response = await _send_recv(
            host_ws,
            {
                "event": "create_game",
                "payload": {"guest_id": str(registered_user["id"])},
            },
        )
        assert host_busy_response["payload"]["code"] == "HOST_BUSY"


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


async def _start_active_game(
    wsa: object, wsb: object, guest_id: str, token_a: str, token_b: str
) -> str:
    await _send_recv(wsa, {"event": "auth", "payload": {"token": token_a}})
    await _send_recv(wsb, {"event": "auth", "payload": {"token": token_b}})
    response = await _send_recv(wsa, {"event": "create_game", "payload": {"guest_id": guest_id}})
    game_id = str(response["payload"]["game_id"])
    await wsb.receive_json()
    await wsb.send_json({"event": "accept_invitation", "payload": {"game_id": game_id}})
    await wsb.receive_json()
    await wsa.receive_json()
    return game_id


@pytest.mark.asyncio
async def test_session_handover_keeps_game_and_new_tab_resumes(
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
        ):
            async with aconnect_ws("ws://test/api/v2/ws/gameplays", client=cb) as wsb:
                game_id = await _start_active_game(
                    wsa, wsb, str(registered_user_b["id"]), auth_token_a, auth_token_b
                )
                await wsb.close(reason="session_handover")

            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(wsa.receive_json(), timeout=0.5)

            async with aconnect_ws("ws://test/api/v2/ws/gameplays", client=cb) as wsb2:
                await _send_recv(wsb2, {"event": "auth", "payload": {"token": auth_token_b}})
                subscribed = await _send_recv(
                    wsb2, {"event": "subscribe_game", "payload": {"game_id": game_id}}
                )
                assert subscribed["event"] == "subscribed"

                await wsa.send_json(
                    {"event": "play_move", "payload": {"game_id": game_id, "row": 0, "col": 0}}
                )
                assert (await wsb2.receive_json())["event"] == "board_updated"
    except BaseExceptionGroup as exc:
        if not _contains_end_of_stream(exc):
            raise


@pytest.mark.asyncio
async def test_session_handover_without_resume_abandons_after_grace(
    ws_client_factory: Callable[[], AsyncClient],
    registered_user_b: dict[str, object],
    auth_token_a: str,
    auth_token_b: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gameapi.api.v2.ws import gameplays as ws_gameplays

    monkeypatch.setattr(ws_gameplays, "ABANDON_GRACE_SECONDS", 0.2)
    try:
        async with (
            ws_client_factory() as ca,
            aconnect_ws("ws://test/api/v2/ws/gameplays", client=ca) as wsa,
            ws_client_factory() as cb,
        ):
            async with aconnect_ws("ws://test/api/v2/ws/gameplays", client=cb) as wsb:
                await _start_active_game(
                    wsa, wsb, str(registered_user_b["id"]), auth_token_a, auth_token_b
                )
                await wsb.close(reason="session_handover")

            res_end = await asyncio.wait_for(wsa.receive_json(), timeout=3)
            assert res_end["event"] == "game_ended"
            assert res_end["payload"]["reason"] == "abandon"
    except BaseExceptionGroup as exc:
        if not _contains_end_of_stream(exc):
            raise
