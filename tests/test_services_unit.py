import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from gameapi.core.config import AppSettings, LogSettings, settings
from gameapi.core.idempotency import (
    InMemoryIdempotencyStore,
    lookup_ws_create_game,
    normalize_registration_identity,
    remember_response,
    remember_ws_create_game,
    replay_response_for,
)
from gameapi.db.models.log_entry import LogEntry
from gameapi.repositories.log_repository import LogRepository
from gameapi.schemas.gameplay import GameplayUpdate
from gameapi.schemas.user import UserUpdate
from gameapi.services import GameplayService, UserService
from gameapi.services.exceptions import (
    GameplayNotFoundError,
    UserNotFoundError,
)
from gameapi.services.gameplay_service import _legacy_json_string
from gameapi.services.invitation_expiry import run_pending_expiry_loop, run_queued_expiry_loop


def test_module_entrypoint_uses_configured_server_settings(monkeypatch) -> None:
    from gameapi import __main__ as entrypoint

    calls: list[tuple[str, dict[str, object]]] = []

    def _run(application: str, **options: object) -> None:
        calls.append((application, options))

    monkeypatch.setattr(entrypoint.uvicorn, "run", _run)
    entrypoint.main()

    assert calls == [
        (
            "gameapi.main:app",
            {
                "host": settings.app.host,
                "port": settings.app.port,
                "reload": settings.app.env == "development",
                "log_level": "info",
            },
        )
    ]


def test_app_settings_accepts_existing_origin_list() -> None:
    app_settings = AppSettings(cors_origins=["https://one.example", "https://two.example"])

    assert app_settings.cors_origins == ["https://one.example", "https://two.example"]


def test_log_settings_admin_emails_default_to_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOG_ADMIN_EMAILS", raising=False)

    assert LogSettings(_env_file=None).admin_emails == []


def test_log_settings_normalizes_admin_email_list() -> None:
    log_settings = LogSettings(admin_emails=["ADMIN@EXAMPLE.COM", " second@example.com "])

    assert log_settings.admin_emails == ["admin@example.com", "second@example.com"]


async def test_gameplay_service_legacy_json_string_handles_bool_str_and_fallback_types() -> None:
    assert _legacy_json_string(True) == "true"
    assert _legacy_json_string(False) == "false"
    assert _legacy_json_string("hello") == '"hello"'
    assert _legacy_json_string(None) == "null"
    assert _legacy_json_string(3) == "3"
    assert _legacy_json_string([True, None, 3, "x"]) == '[true,null,3,"x"]'
    with pytest.raises(TypeError):
        _legacy_json_string(set())


async def test_gameplay_service_get_by_id_invalid_uuid(db_session) -> None:
    service = GameplayService(db_session)
    assert await service.get_by_id("not-a-uuid") is None


async def test_gameplay_service_busy_checks_reject_invalid_uuid(db_session) -> None:
    service = GameplayService(db_session)

    assert await service.find_active_game_for_user("not-a-uuid") is None
    assert await service.has_pending_or_queued_invitation("not-a-uuid") is False


async def test_rebuild_playing_cache_from_active_games(
    db_session,
    db_engine,
    registered_user_a: dict[str, object],
    registered_user_b: dict[str, object],
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from gameapi.db.models.gameplay import Gameplay
    from gameapi.main import rebuild_playing_cache
    from gameapi.services.player_status import _playing_users

    host_id = uuid.UUID(str(registered_user_a["id"]))
    guest_id = uuid.UUID(str(registered_user_b["id"]))
    db_session.add(
        Gameplay(
            current_positions={"board": [[0, 0, 0], [0, 0, 0], [0, 0, 0]]},
            host_player=host_id,
            guest_player=guest_id,
            player_turn=host_id,
            invitation_state="accepted",
            match_result=None,
        )
    )
    await db_session.commit()

    rebuilt = await rebuild_playing_cache(async_sessionmaker(db_engine, expire_on_commit=False))

    assert rebuilt == 2
    assert _playing_users == {str(host_id), str(guest_id)}


async def test_player_status_cache_tracks_playing_users() -> None:
    from gameapi.services import player_status

    player_status._playing_users.clear()
    player_status._playing_users.update({"user-1", "user-2"})

    assert player_status.is_playing("user-1") is True
    assert player_status.is_playing("missing") is False
    assert player_status.playing_user_ids() == []
    player_status.reset_player_status()
    assert player_status.is_playing("user-1") is False


async def test_gameplay_service_list_by_player_invalid_uuid(db_session) -> None:
    service = GameplayService(db_session)
    assert await service.list_by_player("not-a-uuid") == []


async def test_gameplay_service_update_nonexistent_uuid(db_session) -> None:
    service = GameplayService(db_session)
    with pytest.raises(GameplayNotFoundError):
        await service.update(str(uuid.uuid4()), GameplayUpdate(match_result='{"winner": "X"}'))


async def test_player_status_set_players_status_broadcasts_and_clears_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from gameapi.services import player_status

    player_status._playing_users.clear()
    monkeypatch.setattr(player_status.presence_manager, "broadcast", AsyncMock())

    await player_status.set_players_status(["a", "b", None], playing=True)
    await player_status.set_players_status(["a"], playing=False)
    await player_status.set_players_status([], playing=True)
    await player_status.set_players_status(["missing"], playing=False)

    assert player_status.is_playing("a") is False
    assert player_status.is_playing("b") is True
    assert player_status.presence_manager.broadcast.call_count == 3


async def test_gameplay_service_delete_nonexistent_uuid(db_session) -> None:
    service = GameplayService(db_session)
    with pytest.raises(GameplayNotFoundError):
        await service.delete(str(uuid.uuid4()))


async def test_log_repository_bulk_insert_empty_is_noop(db_session) -> None:
    assert await LogRepository(db_session).bulk_insert([]) is None


async def test_log_repository_delete_older_than_returns_zero_when_no_rows_match(
    db_session,
) -> None:
    cutoff = datetime.now(UTC) - timedelta(days=9999)

    deleted = await LogRepository(db_session).delete_older_than(cutoff)

    assert deleted == 0


async def test_log_repository_delete_older_than_includes_exact_cutoff(db_session) -> None:
    cutoff = datetime.now(UTC)
    repo = LogRepository(db_session)
    await repo.bulk_insert(
        [
            LogEntry(
                level="INFO",
                event_type="old_event",
                message="at_cutoff",
                metadata_={},
                timestamp=cutoff,
            ),
            LogEntry(
                level="INFO",
                event_type="new_event",
                message="new",
                metadata_={},
                timestamp=cutoff + timedelta(minutes=1),
            ),
        ]
    )
    await db_session.commit()

    deleted = await repo.delete_older_than(cutoff)

    assert deleted == 1


async def test_log_repository_query_filters_by_event_type(db_session) -> None:
    repository = LogRepository(db_session)
    await repository.bulk_insert(
        [
            LogEntry(
                level="INFO",
                event_type="wanted",
                message="match",
                metadata_={},
                timestamp=datetime.now(UTC),
            ),
            LogEntry(
                level="INFO",
                event_type="other",
                message="non-match",
                metadata_={},
                timestamp=datetime.now(UTC),
            ),
        ]
    )
    await db_session.commit()

    entries, total = await repository.query(event_type="wanted")

    assert total == 1
    assert [entry.message for entry in entries] == ["match"]


async def test_user_service_get_by_id_invalid_uuid(db_session) -> None:
    service = UserService(db_session)
    assert await service.get_by_id("not-a-uuid") is None


async def test_user_service_update_nonexistent_uuid(db_session) -> None:
    service = UserService(db_session)
    with pytest.raises(UserNotFoundError):
        await service.update(str(uuid.uuid4()), UserUpdate(name="Updated-Name"))


async def test_user_service_delete_nonexistent_uuid(db_session) -> None:
    service = UserService(db_session)
    with pytest.raises(UserNotFoundError):
        await service.delete(str(uuid.uuid4()))


async def test_user_service_ensure_indexes_returns_none(db_session) -> None:
    service = UserService(db_session)
    assert await service.ensure_indexes() is None


def test_in_memory_store_key_for_normalizes_and_deduplicates() -> None:
    store = InMemoryIdempotencyStore(ttl_seconds=60)

    assert (
        store.key_for("ws:create_game", " Alice ", "request-1") == "ws:create_game:Alice:request-1"
    )
    assert store.key_for("auth", "USER@EXAMPLE.com", "", "abc") == "auth:USER@EXAMPLE.com:abc"

    remembered = remember_response(
        store=store,
        namespace="register",
        key_parts=("USER@EXAMPLE.com", "request-1"),
        value={"ok": True},
    )
    assert remembered == {"ok": True}
    assert replay_response_for(
        store=store,
        namespace="register",
        key_parts=("user@example.com", "request-1"),
    ) == {"ok": True}


def test_in_memory_store_replays_only_until_ttl_expiry() -> None:
    store = InMemoryIdempotencyStore(ttl_seconds=1)
    remember_ws_create_game(host_id="u-1", request_id="abc", game_id="game-1", store=store)

    assert lookup_ws_create_game(host_id="u-1", request_id="abc", store=store) == "game-1"

    key = store.key_for("ws:create_game", "u-1", "abc")
    store._values[key] = (time.monotonic() - 1, "stale")
    assert lookup_ws_create_game(host_id="u-1", request_id="abc", store=store) is None


def test_normalize_registration_identity_uses_case_insensitive_trimmed_email() -> None:
    assert normalize_registration_identity("  User@Example.com  ") == "user@example.com"


async def test_expiry_loops_cancel_gracefully() -> None:
    class DummyEngine:
        async def expire_pending_invitations(self, older_than_seconds: int) -> int:
            return older_than_seconds

        async def expire_queued_invitations(self, older_than_seconds: int) -> int:
            return older_than_seconds

    engine = DummyEngine()

    pending_task = asyncio.create_task(
        run_pending_expiry_loop(engine, interval_seconds=0.01, ttl_seconds=30)
    )
    queued_task = asyncio.create_task(
        run_queued_expiry_loop(engine, interval_seconds=0.01, ttl_seconds=60)
    )

    await asyncio.sleep(0.03)
    pending_task.cancel()
    queued_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await pending_task
    with pytest.raises(asyncio.CancelledError):
        await queued_task
