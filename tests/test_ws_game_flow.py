from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from anyio import EndOfStream
from httpx import AsyncClient
from httpx_ws import aconnect_ws


async def _send_recv(ws: Any, event_dict: dict) -> dict:
    """Send a JSON message and wait for the immediate response."""
    await ws.send_json(event_dict)
    return await ws.receive_json()


# ---------------------------------------------------------------------------
# Happy path: full game won by host (row 0)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_happy_path(
    ws_client_factory: Callable[[], AsyncClient],
    registered_user_a: dict,
    registered_user_b: dict,
    auth_token_a: str,
    auth_token_b: str,
) -> None:
    user_a_id = registered_user_a["id"]
    user_b_id = registered_user_b["id"]

    async with (
        ws_client_factory() as ca,
        aconnect_ws("ws://test/api/v2/ws/gameplays", client=ca) as wsa,
        ws_client_factory() as cb,
        aconnect_ws("ws://test/api/v2/ws/gameplays", client=cb) as wsb,
    ):
        res_a = await _send_recv(wsa, {"event": "auth", "payload": {"token": auth_token_a}})
        assert res_a["event"] == "auth_ok"
        res_b = await _send_recv(wsb, {"event": "auth", "payload": {"token": auth_token_b}})
        assert res_b["event"] == "auth_ok"

        res_a_created = await _send_recv(
            wsa,
            {"event": "create_game", "payload": {"guest_id": user_b_id}},
        )
        assert res_a_created["event"] == "game_created"
        game_id = res_a_created["payload"]["game_id"]

        res_b_invite = await wsb.receive_json()
        assert res_b_invite["event"] == "invitation_received"
        assert res_b_invite["payload"]["game_id"] == game_id

        await wsb.send_json({"event": "accept_invitation", "payload": {"game_id": game_id}})
        res_b_accepted = await wsb.receive_json()
        assert res_b_accepted["event"] == "invitation_accepted"

        res_a_accepted = await wsa.receive_json()
        assert res_a_accepted["event"] == "invitation_accepted"

        # A plays: (0,0), (0,1), (0,2); B plays: (1,1), (1,0).
        await wsa.send_json(
            {"event": "play_move", "payload": {"game_id": game_id, "row": 0, "col": 0}}
        )
        assert (await wsa.receive_json())["event"] == "board_updated"
        res_b_board = await wsb.receive_json()
        assert res_b_board["event"] == "board_updated"

        await wsb.send_json(
            {"event": "play_move", "payload": {"game_id": game_id, "row": 1, "col": 1}}
        )
        assert (await wsb.receive_json())["event"] == "board_updated"
        assert (await wsa.receive_json())["event"] == "board_updated"

        await wsa.send_json(
            {"event": "play_move", "payload": {"game_id": game_id, "row": 0, "col": 1}}
        )
        assert (await wsa.receive_json())["event"] == "board_updated"
        assert (await wsb.receive_json())["event"] == "board_updated"

        await wsb.send_json(
            {"event": "play_move", "payload": {"game_id": game_id, "row": 1, "col": 0}}
        )
        assert (await wsb.receive_json())["event"] == "board_updated"
        assert (await wsa.receive_json())["event"] == "board_updated"

        await wsa.send_json(
            {"event": "play_move", "payload": {"game_id": game_id, "row": 0, "col": 2}}
        )
        res_a_win = await wsa.receive_json()
        assert res_a_win["event"] == "game_ended"
        assert res_a_win["payload"]["winner"] == user_a_id
        assert res_a_win["payload"]["board"][0] == [1, 1, 1]
        assert res_a_win["payload"]["winner_line"] == [[0, 0], [0, 1], [0, 2]]

        res_b_win = await wsb.receive_json()
        assert res_b_win["event"] == "game_ended"
        assert res_b_win["payload"]["winner"] == user_a_id
        assert res_b_win["payload"]["board"][0] == [1, 1, 1]
        assert res_b_win["payload"]["winner_line"] == [[0, 0], [0, 1], [0, 2]]


# ---------------------------------------------------------------------------
# Rejection flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rejection_flow(
    ws_client_factory: Callable[[], AsyncClient],
    registered_user_b: dict,
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

        res_created = await _send_recv(
            wsa,
            {"event": "create_game", "payload": {"guest_id": registered_user_b["id"]}},
        )
        game_id = res_created["payload"]["game_id"]
        await wsb.receive_json()  # invitation_received

        await wsb.send_json({"event": "reject_invitation", "payload": {"game_id": game_id}})
        res_a = await wsa.receive_json()
        assert res_a["event"] == "invitation_rejected"


# ---------------------------------------------------------------------------
# NOT_YOUR_TURN error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_not_your_turn(
    ws_client_factory: Callable[[], AsyncClient],
    registered_user_b: dict,
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

        res_created = await _send_recv(
            wsa,
            {"event": "create_game", "payload": {"guest_id": registered_user_b["id"]}},
        )
        game_id = res_created["payload"]["game_id"]
        await wsb.receive_json()  # invitation_received

        await wsb.send_json({"event": "accept_invitation", "payload": {"game_id": game_id}})
        await wsb.receive_json()  # invitation_accepted (B)
        await wsa.receive_json()  # invitation_accepted (A)

        # A plays first.
        await wsa.send_json(
            {"event": "play_move", "payload": {"game_id": game_id, "row": 0, "col": 0}}
        )
        await wsa.receive_json()
        await wsb.receive_json()

        # A tries to play again → NOT_YOUR_TURN.
        res_err = await _send_recv(
            wsa,
            {"event": "play_move", "payload": {"game_id": game_id, "row": 1, "col": 1}},
        )
        assert res_err["event"] == "error"
        assert res_err["payload"]["code"] == "NOT_YOUR_TURN"


# ---------------------------------------------------------------------------
# INVALID_MOVE: cell already occupied
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_move(
    ws_client_factory: Callable[[], AsyncClient],
    registered_user_b: dict,
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

        res_created = await _send_recv(
            wsa,
            {"event": "create_game", "payload": {"guest_id": registered_user_b["id"]}},
        )
        game_id = res_created["payload"]["game_id"]
        await wsb.receive_json()

        await wsb.send_json({"event": "accept_invitation", "payload": {"game_id": game_id}})
        await wsb.receive_json()
        await wsa.receive_json()

        # A plays (0,0).
        await wsa.send_json(
            {"event": "play_move", "payload": {"game_id": game_id, "row": 0, "col": 0}}
        )
        await wsa.receive_json()
        await wsb.receive_json()

        # B tries same cell → INVALID_MOVE.
        res_err = await _send_recv(
            wsb,
            {"event": "play_move", "payload": {"game_id": game_id, "row": 0, "col": 0}},
        )
        assert res_err["event"] == "error"
        assert res_err["payload"]["code"] == "INVALID_MOVE"


# ---------------------------------------------------------------------------
# INVALID_PAYLOAD: row/col out of bounds (validated by Pydantic)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_out_of_bounds(
    ws_client_factory: Callable[[], AsyncClient],
    registered_user_b: dict,
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

        res_created = await _send_recv(
            wsa,
            {"event": "create_game", "payload": {"guest_id": registered_user_b["id"]}},
        )
        game_id = res_created["payload"]["game_id"]
        await wsb.receive_json()

        await wsb.send_json({"event": "accept_invitation", "payload": {"game_id": game_id}})
        await wsb.receive_json()
        await wsa.receive_json()

        res_err = await _send_recv(
            wsa,
            {"event": "play_move", "payload": {"game_id": game_id, "row": 5, "col": 5}},
        )
        assert res_err["event"] == "error"
        assert res_err["payload"]["code"] == "INVALID_PAYLOAD"


# ---------------------------------------------------------------------------
# NOT_A_PARTICIPANT: host tries to accept their own invitation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_not_a_participant(
    ws_client_factory: Callable[[], AsyncClient],
    registered_user_b: dict,
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

        res_created = await _send_recv(
            wsa,
            {"event": "create_game", "payload": {"guest_id": registered_user_b["id"]}},
        )
        game_id = res_created["payload"]["game_id"]
        await wsb.receive_json()  # invitation_received

        # Host A tries to accept their own invitation → NOT_A_PARTICIPANT.
        res_err = await _send_recv(
            wsa,
            {"event": "accept_invitation", "payload": {"game_id": game_id}},
        )
        assert res_err["event"] == "error"
        assert res_err["payload"]["code"] == "NOT_A_PARTICIPANT"


# ---------------------------------------------------------------------------
# Abandonment: guest disconnects, host receives game_ended / abandon
# ---------------------------------------------------------------------------


def _contains_end_of_stream(exc: BaseException) -> bool:
    if isinstance(exc, EndOfStream):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_contains_end_of_stream(sub) for sub in exc.exceptions)
    return False


@pytest.mark.asyncio
async def test_abandonment(
    ws_client_factory: Callable[[], AsyncClient],
    registered_user_b: dict,
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

            res_created = await _send_recv(
                wsa,
                {"event": "create_game", "payload": {"guest_id": registered_user_b["id"]}},
            )
            game_id = res_created["payload"]["game_id"]
            await wsb.receive_json()

            await wsb.send_json({"event": "accept_invitation", "payload": {"game_id": game_id}})
            await wsb.receive_json()
            await wsa.receive_json()

            await wsb.close()
            res_end = await wsa.receive_json()
            assert res_end["event"] == "game_ended"
            assert res_end["payload"]["reason"] == "abandon"
            assert res_end["payload"]["board"] == [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
    except BaseExceptionGroup as exc:
        if not _contains_end_of_stream(exc):
            raise


@pytest.mark.asyncio
async def test_leave_game_ws_emits_game_ended_with_board(
    ws_client_factory: Callable[[], AsyncClient],
    registered_user_b: dict,
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

        res_created = await _send_recv(
            wsa,
            {"event": "create_game", "payload": {"guest_id": registered_user_b["id"]}},
        )
        game_id = res_created["payload"]["game_id"]
        await wsb.receive_json()

        await wsb.send_json({"event": "accept_invitation", "payload": {"game_id": game_id}})
        await wsb.receive_json()
        await wsa.receive_json()

        await wsa.send_json(
            {"event": "play_move", "payload": {"game_id": game_id, "row": 0, "col": 0}}
        )
        await wsa.receive_json()
        await wsb.receive_json()

        await wsa.send_json({"event": "leave_game", "payload": {"game_id": game_id}})
        res_b = await wsb.receive_json()

        assert res_b["event"] == "game_ended"
        assert res_b["payload"]["reason"] == "abandon"
        assert res_b["payload"]["winner"] == registered_user_b["id"]
        assert res_b["payload"]["board"] == [[1, 0, 0], [0, 0, 0], [0, 0, 0]]


# ---------------------------------------------------------------------------
# Draw
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_draw(
    ws_client_factory: Callable[[], AsyncClient],
    registered_user_b: dict,
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

        res_created = await _send_recv(
            wsa,
            {"event": "create_game", "payload": {"guest_id": registered_user_b["id"]}},
        )
        game_id = res_created["payload"]["game_id"]
        await wsb.receive_json()

        await wsb.send_json({"event": "accept_invitation", "payload": {"game_id": game_id}})
        await wsb.receive_json()
        await wsa.receive_json()

        # Draw sequence with no winner on the final move.
        # A: (0,0) B: (0,1) A: (1,2) B: (1,0)
        # A: (1,1) B: (2,2) A: (2,1) B: (0,2)
        # A: (2,0) → draw.
        moves = [
            (wsa, 0, 0),
            (wsb, 0, 1),
            (wsa, 1, 2),
            (wsb, 1, 0),
            (wsa, 1, 1),
            (wsb, 2, 2),
            (wsa, 2, 1),
            (wsb, 0, 2),
            (wsa, 2, 0),
        ]

        for player_ws, row, col in moves:
            await player_ws.send_json(
                {"event": "play_move", "payload": {"game_id": game_id, "row": row, "col": col}}
            )
            msg_a = await wsa.receive_json()
            msg_b = await wsb.receive_json()

        # Last move should end with draw.
        assert msg_a["event"] == "game_ended"
        assert msg_a["payload"]["reason"] == "draw"
        assert msg_b["event"] == "game_ended"
        assert msg_b["payload"]["reason"] == "draw"


# ---------------------------------------------------------------------------
# CANNOT_INVITE_SELF
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invite_self(
    ws_client_factory: Callable[[], AsyncClient],
    registered_user_a: dict,
    auth_token_a: str,
) -> None:
    async with (
        ws_client_factory() as ca,
        aconnect_ws("ws://test/api/v2/ws/gameplays", client=ca) as wsa,
    ):
        await _send_recv(wsa, {"event": "auth", "payload": {"token": auth_token_a}})
        res_err = await _send_recv(
            wsa,
            {"event": "create_game", "payload": {"guest_id": registered_user_a["id"]}},
        )
        assert res_err["event"] == "error"
        assert res_err["payload"]["code"] == "CANNOT_INVITE_SELF"


# ---------------------------------------------------------------------------
# OPPONENT_OFFLINE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_opponent_offline(
    ws_client_factory: Callable[[], AsyncClient],
    registered_user_b: dict,
    auth_token_a: str,
) -> None:
    # B is registered but NOT connected via WS → offline.
    async with (
        ws_client_factory() as ca,
        aconnect_ws("ws://test/api/v2/ws/gameplays", client=ca) as wsa,
    ):
        await _send_recv(wsa, {"event": "auth", "payload": {"token": auth_token_a}})
        res_err = await _send_recv(
            wsa,
            {"event": "create_game", "payload": {"guest_id": registered_user_b["id"]}},
        )
        assert res_err["event"] == "error"
        assert res_err["payload"]["code"] == "OPPONENT_OFFLINE"


# ---------------------------------------------------------------------------
# GAME_NOT_FOUND
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_game_not_found(
    ws_client_factory: Callable[[], AsyncClient],
    auth_token_a: str,
) -> None:
    async with (
        ws_client_factory() as ca,
        aconnect_ws("ws://test/api/v2/ws/gameplays", client=ca) as wsa,
    ):
        await _send_recv(wsa, {"event": "auth", "payload": {"token": auth_token_a}})
        res_err = await _send_recv(
            wsa,
            {
                "event": "play_move",
                "payload": {"game_id": str(uuid.uuid4()), "row": 0, "col": 0},
            },
        )
        assert res_err["event"] == "error"
        assert res_err["payload"]["code"] == "GAME_NOT_FOUND"
