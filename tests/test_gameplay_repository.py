from __future__ import annotations

from datetime import UTC, datetime, timedelta

from gameapi.db.models.gameplay import Gameplay
from gameapi.db.models.user import User
from gameapi.repositories.gameplay_repository import GameplayRepository


async def test_find_next_queued_for_guest_returns_oldest_then_next(db_session) -> None:
    guest = User(name="Guest", email="guest@example.com", password_hash="hash")
    host_a = User(name="Host A", email="host-a@example.com", password_hash="hash")
    host_b = User(name="Host B", email="host-b@example.com", password_hash="hash")
    host_c = User(name="Host C", email="host-c@example.com", password_hash="hash")
    db_session.add_all([guest, host_a, host_b, host_c])
    await db_session.flush()

    guest_id = guest.id
    now = datetime.now(UTC)

    oldest = Gameplay(
        host_player=host_a.id,
        guest_player=guest_id,
        player_turn=host_a.id,
        invitation_state="queued",
        current_positions={},
        match_result=None,
        created_date=now - timedelta(days=3),
        updated_date=now - timedelta(days=3),
    )
    middle = Gameplay(
        host_player=host_b.id,
        guest_player=guest_id,
        player_turn=host_b.id,
        invitation_state="queued",
        current_positions={},
        match_result=None,
        created_date=now - timedelta(days=2),
        updated_date=now - timedelta(days=2),
    )
    newest = Gameplay(
        host_player=host_c.id,
        guest_player=guest_id,
        player_turn=host_c.id,
        invitation_state="queued",
        current_positions={},
        match_result=None,
        created_date=now - timedelta(days=1),
        updated_date=now - timedelta(days=1),
    )

    db_session.add_all([oldest, middle, newest])
    await db_session.commit()

    repo = GameplayRepository(db_session)
    upcoming = await repo.find_next_queued_for_guest(guest_id)
    assert upcoming is not None
    assert upcoming.id == oldest.id

    oldest.invitation_state = "expired"
    await db_session.commit()

    upcoming = await repo.find_next_queued_for_guest(guest_id)
    assert upcoming is not None
    assert upcoming.id == middle.id
