import uuid
from datetime import UTC, datetime, timedelta

import pytest

from gameapi.core.config import AppSettings, LogSettings, settings
from gameapi.db.models.log_entry import LogEntry
from gameapi.repositories.log_repository import LogRepository
from gameapi.schemas.gameplay import GameplayUpdate
from gameapi.schemas.user import UserUpdate
from gameapi.services import GameplayService, UserService
from gameapi.services.exceptions import GameplayNotFoundError, UserNotFoundError
from gameapi.services.gameplay_service import _legacy_json_string


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


async def test_gameplay_service_list_by_player_invalid_uuid(db_session) -> None:
    service = GameplayService(db_session)
    assert await service.list_by_player("not-a-uuid") == []


async def test_gameplay_service_update_nonexistent_uuid(db_session) -> None:
    service = GameplayService(db_session)
    with pytest.raises(GameplayNotFoundError):
        await service.update(str(uuid.uuid4()), GameplayUpdate(match_result='{"winner": "X"}'))


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
        await service.update(str(uuid.uuid4()), UserUpdate(name="Updated Name"))


async def test_user_service_delete_nonexistent_uuid(db_session) -> None:
    service = UserService(db_session)
    with pytest.raises(UserNotFoundError):
        await service.delete(str(uuid.uuid4()))


async def test_user_service_ensure_indexes_returns_none(db_session) -> None:
    service = UserService(db_session)
    assert await service.ensure_indexes() is None
