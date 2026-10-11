from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from gameapi.schemas.user import UserCreate
from gameapi.services.event_bus import EventBus
from gameapi.services.exceptions import (
    GameNotActiveError,
    GameplayNotFoundError,
    HostBusyError,
    InvitationNotPendingError,
    NotAParticipantError,
    NotYourTurnError,
    UserBusyError,
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


async def test_create_game_rejects_host_busy_and_active_guest_game(
    engine_service: GameEngineService, db_session: AsyncSession
) -> None:
    host_id, guest_id = await _create_users(db_session)
    user_service = UserService(db_session)
    other_host = await user_service.create(
        UserCreate(name="Other Host", email="otherhost@example.com", password="password123")
    )
    other_guest = await user_service.create(
        UserCreate(name="Other Guest", email="otherguest@example.com", password="password123")
    )
    await db_session.commit()

    first_game = await engine_service.create_game(host_id, guest_id)
    second_game = await engine_service.create_game(str(other_host.id), guest_id)
    queued = await engine_service.gameplay_service.get_by_id(second_game)
    assert queued is not None
    assert queued.invitation_state == "queued"

    with pytest.raises(HostBusyError):
        await engine_service.create_game(host_id, str(other_guest.id))

    await engine_service.accept_invitation(first_game, guest_id)
    with pytest.raises(UserBusyError):
        await engine_service.create_game(str(other_host.id), guest_id)


async def test_accept_invitation_expires_other_pending_requests_for_guest(
    engine_service: GameEngineService, db_session: AsyncSession
) -> None:
    host_id, guest_id = await _create_users(db_session)
    user_service = UserService(db_session)
    other_host = await user_service.create(
        UserCreate(name="Other Host", email="otherhost2@example.com", password="strongpass")
    )
    await db_session.commit()

    first_game = await engine_service.create_game(host_id, guest_id)
    second_game = await engine_service.create_game(str(other_host.id), guest_id)

    await engine_service.accept_invitation(second_game, guest_id)

    first = await engine_service.gameplay_service.get_by_id(first_game)
    assert first is not None
    assert first.invitation_state == "expired"
    assert json.loads(first.match_result) == {"winner": None, "reason": "target_busy"}


async def test_reject_invitation_promotes_next_queued_game_for_guest(
    engine_service: GameEngineService, db_session: AsyncSession
) -> None:
    _, guest_id = await _create_users(db_session)
    user_service = UserService(db_session)
    first_host = await user_service.create(
        UserCreate(name="First Host", email="firsthost@example.com", password="supersecret")
    )
    second_host = await user_service.create(
        UserCreate(name="Second Host", email="secondhost@example.com", password="supersecret")
    )
    await db_session.commit()

    first_invite = await engine_service.create_game(str(first_host.id), guest_id)
    second_invite = await engine_service.create_game(str(second_host.id), guest_id)
    third_invite = await engine_service.create_game(str(second_host.id), guest_id)

    first = await engine_service.gameplay_service.get_by_id(first_invite)
    second = await engine_service.gameplay_service.get_by_id(second_invite)
    third = await engine_service.gameplay_service.get_by_id(third_invite)
    assert first is not None and second is not None and third is not None
    assert first.invitation_state == "pending"
    assert second.invitation_state == "queued"
    assert third.invitation_state == "queued"

    await engine_service.reject_invitation(third_invite, guest_id)

    refreshed = await engine_service.gameplay_service.get_by_id(second_invite)
    assert refreshed is not None
    assert refreshed.invitation_state == "pending"


async def test_leave_game_pending_cancels_invitation_for_other_player(
    engine_service: GameEngineService, db_session: AsyncSession
) -> None:
    host_id, guest_id = await _create_users(db_session)
    game_id = await engine_service.create_game(host_id, guest_id)

    await engine_service.leave_game(game_id, host_id)

    gameplay = await engine_service.gameplay_service.get_by_id(game_id)
    assert gameplay is not None
    assert gameplay.invitation_state == "canceled"
    assert json.loads(gameplay.match_result) == {"winner": None, "reason": "host_left"}


async def test_expire_pending_and_queued_invitations_marks_them_expired(
    engine_service: GameEngineService, db_session: AsyncSession
) -> None:
    host_id, guest_id = await _create_users(db_session)
    user_service = UserService(db_session)
    queued_host = await user_service.create(
        UserCreate(name="Queued", email="queued@example.com", password="strongpass")
    )
    active_host = await user_service.create(
        UserCreate(name="Active", email="active@example.com", password="strongpass")
    )
    await db_session.commit()

    pending_game = await engine_service.create_game(host_id, guest_id)
    queued_game = await engine_service.create_game(str(active_host.id), str(queued_host.id))
    await engine_service.accept_invitation(str(queued_game), str(queued_host.id))

    pending = await engine_service.gameplay_service.get_by_id(pending_game)
    assert pending is not None
    pending.updated_date = pending.updated_date - timedelta(days=2)
    pending.invitation_state = "pending"
    await db_session.execute(
        text(
            "UPDATE gameplays SET updated_date = :updated_date,"
            "invitation_state = :state WHERE id = :game_id"
        ),
        {
            "updated_date": pending.updated_date,
            "state": pending.invitation_state,
            "game_id": pending.id,
        },
    )
    queued = await engine_service.gameplay_service.get_by_id(queued_game)
    assert queued is not None
    queued.updated_date = queued.updated_date - timedelta(days=2)
    queued.invitation_state = "queued"
    await db_session.execute(
        text(
            "UPDATE gameplays SET updated_date = :updated_date, "
            "invitation_state = :state WHERE id = :game_id"
        ),
        {
            "updated_date": queued.updated_date,
            "state": queued.invitation_state,
            "game_id": queued.id,
        },
    )
    await db_session.commit()

    await engine_service.expire_pending_invitations(older_than_seconds=1)
    await engine_service.expire_queued_invitations(older_than_seconds=1)

    pending_after = await engine_service.gameplay_service.get_by_id(pending_game)
    queued_after = await engine_service.gameplay_service.get_by_id(queued_game)
    assert pending_after is not None and queued_after is not None
    assert pending_after.invitation_state == "expired"
    assert queued_after.invitation_state == "expired"
