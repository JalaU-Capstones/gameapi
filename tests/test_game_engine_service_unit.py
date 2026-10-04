from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from gameapi.schemas.user import UserCreate
from gameapi.services.event_bus import EventBus
from gameapi.services.exceptions import (
    GameNotActiveError,
    GameplayNotFoundError,
    InvitationNotPendingError,
    NotAParticipantError,
    NotYourTurnError,
)
from gameapi.services.game_engine_service import GameEngineService
from gameapi.services.gameplay_service import GameplayService
from gameapi.services.user_service import UserService


@pytest.fixture
def engine_service(db_session: AsyncSession) -> GameEngineService:
    return GameEngineService(
        GameplayService(db_session),
        UserService(db_session),
        EventBus(),
    )


async def _create_users(db_session: AsyncSession) -> tuple[str, str]:
    user_service = UserService(db_session)
    host = await user_service.create(
        UserCreate(name="Host", email="host@example.com", password="pw123456")
    )
    guest = await user_service.create(
        UserCreate(name="Guest", email="guest@example.com", password="pw123456")
    )
    await db_session.commit()
    return str(host.id), str(guest.id)


async def test_accept_invitation_by_non_participant_raises(
    engine_service: GameEngineService, db_session: AsyncSession
) -> None:
    host_id, guest_id = await _create_users(db_session)
    game_id = await engine_service.create_game(host_id, guest_id)

    with pytest.raises(NotAParticipantError):
        await engine_service.accept_invitation(game_id, "33333333-3333-4333-8333-333333333333")


async def test_reject_invitation_by_non_participant_raises(
    engine_service: GameEngineService, db_session: AsyncSession
) -> None:
    host_id, guest_id = await _create_users(db_session)
    game_id = await engine_service.create_game(host_id, guest_id)

    with pytest.raises(NotAParticipantError):
        await engine_service.reject_invitation(game_id, "33333333-3333-4333-8333-333333333333")


async def test_reject_invitation_when_not_pending_raises(
    engine_service: GameEngineService, db_session: AsyncSession
) -> None:
    host_id, guest_id = await _create_users(db_session)
    game_id = await engine_service.create_game(host_id, guest_id)
    await engine_service.accept_invitation(game_id, guest_id)

    with pytest.raises(InvitationNotPendingError):
        await engine_service.reject_invitation(game_id, guest_id)


async def test_accept_invitation_when_game_not_found_raises(
    engine_service: GameEngineService,
) -> None:
    with pytest.raises(GameplayNotFoundError):
        await engine_service.accept_invitation("00000000-0000-0000-0000-000000000000", "guest")


async def test_accept_invitation_when_not_pending_raises(
    engine_service: GameEngineService,
    db_session: AsyncSession,
) -> None:
    host_id, guest_id = await _create_users(db_session)
    game_id = await engine_service.create_game(host_id, guest_id)
    await engine_service.accept_invitation(game_id, guest_id)

    with pytest.raises(InvitationNotPendingError):
        await engine_service.accept_invitation(game_id, guest_id)


async def test_reject_invitation_when_game_not_found_raises(
    engine_service: GameEngineService,
) -> None:
    with pytest.raises(GameplayNotFoundError):
        await engine_service.reject_invitation("00000000-0000-0000-0000-000000000000", "guest")


async def test_play_move_when_game_not_found_raises(engine_service: GameEngineService) -> None:
    with pytest.raises(GameplayNotFoundError):
        await engine_service.play_move("00000000-0000-0000-0000-000000000000", "player", 0, 0)


async def test_leave_game_when_game_not_found_raises(engine_service: GameEngineService) -> None:
    with pytest.raises(GameplayNotFoundError):
        await engine_service.leave_game("00000000-0000-0000-0000-000000000000", "player")


async def test_play_move_by_non_participant_raises(
    engine_service: GameEngineService, db_session: AsyncSession
) -> None:
    host_id, guest_id = await _create_users(db_session)
    game_id = await engine_service.create_game(host_id, guest_id)
    await engine_service.accept_invitation(game_id, guest_id)

    with pytest.raises(NotAParticipantError):
        await engine_service.play_move(game_id, "33333333-3333-4333-8333-333333333333", 0, 0)


async def test_play_move_on_inactive_game_raises(
    engine_service: GameEngineService, db_session: AsyncSession
) -> None:
    host_id, guest_id = await _create_users(db_session)
    game_id = await engine_service.create_game(host_id, guest_id)
    await engine_service.accept_invitation(game_id, guest_id)

    await engine_service.play_move(game_id, host_id, 0, 0)
    await engine_service.play_move(game_id, guest_id, 1, 0)
    await engine_service.play_move(game_id, host_id, 0, 1)
    await engine_service.play_move(game_id, guest_id, 1, 1)
    await engine_service.play_move(game_id, host_id, 0, 2)

    with pytest.raises(GameNotActiveError):
        await engine_service.play_move(game_id, guest_id, 2, 2)


async def test_play_move_out_of_turn_raises(
    engine_service: GameEngineService, db_session: AsyncSession
) -> None:
    host_id, guest_id = await _create_users(db_session)
    game_id = await engine_service.create_game(host_id, guest_id)
    await engine_service.accept_invitation(game_id, guest_id)

    with pytest.raises(NotYourTurnError):
        await engine_service.play_move(game_id, guest_id, 0, 0)


async def test_play_move_guest_wins_returns_guest_winner(
    engine_service: GameEngineService, db_session: AsyncSession
) -> None:
    host_id, guest_id = await _create_users(db_session)
    game_id = await engine_service.create_game(host_id, guest_id)
    await engine_service.accept_invitation(game_id, guest_id)

    await engine_service.play_move(game_id, host_id, 0, 0)
    await engine_service.play_move(game_id, guest_id, 1, 0)
    await engine_service.play_move(game_id, host_id, 0, 1)
    await engine_service.play_move(game_id, guest_id, 1, 1)
    await engine_service.play_move(game_id, host_id, 2, 0)
    result = await engine_service.play_move(game_id, guest_id, 1, 2)

    assert result["event"] == "game_ended"
    assert result["payload"]["winner"] == guest_id
    assert result["payload"]["reason"] == "line"
    assert result["payload"]["board"][1] == [2, 2, 2]
    assert result["payload"]["winner_line"] == [[1, 0], [1, 1], [1, 2]]


async def test_play_move_returns_board_and_winner_line_on_win(
    engine_service: GameEngineService, db_session: AsyncSession
) -> None:
    host_id, guest_id = await _create_users(db_session)
    game_id = await engine_service.create_game(host_id, guest_id)
    await engine_service.accept_invitation(game_id, guest_id)

    await engine_service.play_move(game_id, host_id, 0, 0)
    await engine_service.play_move(game_id, guest_id, 1, 1)
    await engine_service.play_move(game_id, host_id, 0, 1)
    await engine_service.play_move(game_id, guest_id, 1, 0)

    result = await engine_service.play_move(game_id, host_id, 0, 2)

    assert result["event"] == "game_ended"
    payload = result["payload"]
    assert payload["reason"] == "line"
    assert payload["winner"] == host_id
    assert payload["board"] == [[1, 1, 1], [2, 2, 0], [0, 0, 0]]
    assert payload["winner_line"] == [[0, 0], [0, 1], [0, 2]]


async def test_play_move_returns_board_and_no_winner_line_on_draw(
    engine_service: GameEngineService, db_session: AsyncSession
) -> None:
    host_id, guest_id = await _create_users(db_session)
    game_id = await engine_service.create_game(host_id, guest_id)
    await engine_service.accept_invitation(game_id, guest_id)

    moves = [
        (host_id, 0, 0),
        (guest_id, 0, 1),
        (host_id, 1, 2),
        (guest_id, 1, 0),
        (host_id, 1, 1),
        (guest_id, 2, 2),
        (host_id, 2, 1),
        (guest_id, 0, 2),
        (host_id, 2, 0),
    ]

    result: dict[str, Any] = {}
    for player_id, row, col in moves:
        result = await engine_service.play_move(game_id, player_id, row, col)

    assert result["event"] == "game_ended"
    payload = result["payload"]
    assert payload["reason"] == "draw"
    assert payload["winner"] is None
    assert payload["winner_line"] is None
    assert payload["board"] == [[1, 2, 2], [2, 1, 1], [1, 1, 2]]


async def test_leave_game_by_guest_opponent_is_host(
    engine_service: GameEngineService, db_session: AsyncSession
) -> None:
    host_id, guest_id = await _create_users(db_session)
    game_id = await engine_service.create_game(host_id, guest_id)
    await engine_service.accept_invitation(game_id, guest_id)

    await engine_service.leave_game(game_id, guest_id)
    gameplay = await engine_service.gameplay_service.get_by_id(game_id)

    assert gameplay is not None
    assert json.loads(gameplay.match_result) == {"winner": host_id, "reason": "abandon"}


async def test_leave_game_payload_includes_current_board(
    engine_service: GameEngineService, db_session: AsyncSession
) -> None:
    host_id, guest_id = await _create_users(db_session)
    game_id = await engine_service.create_game(host_id, guest_id)
    await engine_service.accept_invitation(game_id, guest_id)
    await engine_service.play_move(game_id, host_id, 0, 0)

    await engine_service.leave_game(game_id, host_id)
    gameplay = await engine_service.gameplay_service.get_by_id(game_id)

    assert gameplay is not None
    assert json.loads(gameplay.match_result) == {"winner": guest_id, "reason": "abandon"}
    assert json.loads(gameplay.current_positions)["board"] == [[1, 0, 0], [0, 0, 0], [0, 0, 0]]


async def test_reject_invitation_persists_rejection(
    engine_service: GameEngineService, db_session: AsyncSession
) -> None:
    host_id, guest_id = await _create_users(db_session)
    game_id = await engine_service.create_game(host_id, guest_id)

    await engine_service.reject_invitation(game_id, guest_id)
    gameplay = await engine_service.gameplay_service.get_by_id(game_id)

    assert gameplay is not None
    assert json.loads(gameplay.match_result) == {"winner": None, "reason": "rejected"}


async def test_leave_game_on_finished_game_is_noop(
    engine_service: GameEngineService, db_session: AsyncSession
) -> None:
    host_id, guest_id = await _create_users(db_session)
    game_id = await engine_service.create_game(host_id, guest_id)
    await engine_service.accept_invitation(game_id, guest_id)

    await engine_service.play_move(game_id, host_id, 0, 0)
    await engine_service.play_move(game_id, guest_id, 1, 0)
    await engine_service.play_move(game_id, host_id, 0, 1)
    await engine_service.play_move(game_id, guest_id, 1, 1)
    await engine_service.play_move(game_id, host_id, 0, 2)

    before = await engine_service.gameplay_service.get_by_id(game_id)
    await engine_service.leave_game(game_id, host_id)
    await db_session.commit()
    after = await engine_service.gameplay_service.get_by_id(game_id)

    assert before is not None
    assert after is not None
    assert before.match_result == after.match_result
