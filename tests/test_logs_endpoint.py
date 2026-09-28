import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from gameapi.api.deps import require_log_admin
from gameapi.core.config import LogSettings, settings
from gameapi.db.models.log_entry import LogEntry
from gameapi.repositories.log_repository import LogRepository


@pytest.fixture
async def admin_client(
    client: AsyncClient,
    registered_user: dict[str, object],
) -> AsyncIterator[AsyncClient]:
    from gameapi.main import app

    async def _allow_admin() -> dict[str, object]:
        return registered_user

    app.dependency_overrides[require_log_admin] = _allow_admin
    yield client
    app.dependency_overrides.pop(require_log_admin, None)


async def _seed_logs(session, entries: list[LogEntry]) -> None:
    await LogRepository(session).bulk_insert(entries)
    await session.commit()


def _log_entry(
    *,
    player_id: uuid.UUID,
    message: str,
    level: str = "INFO",
    event_type: str = "user_registered",
    timestamp: datetime | None = None,
) -> LogEntry:
    return LogEntry(
        level=level,
        event_type=event_type,
        message=message,
        player_id=player_id,
        gameplay_id=None,
        metadata_={},
        timestamp=timestamp or datetime.now(UTC),
    )


async def test_query_my_logs_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v2/logs/me")
    assert response.status_code == 401


async def test_query_my_logs_returns_only_own_logs(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
    registered_user: dict[str, object],
    registered_user_a: dict[str, object],
) -> None:
    player_id = uuid.UUID(str(registered_user["id"]))
    other_id = uuid.UUID(str(registered_user_a["id"]))
    await _seed_logs(
        db_session,
        [
            _log_entry(player_id=player_id, message="mine"),
            _log_entry(player_id=other_id, message="theirs"),
        ],
    )

    response = await client.get("/api/v2/logs/me", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["message"] for item in body["items"]] == ["mine"]
    assert body["items"][0]["playerId"] == str(player_id)


async def test_query_my_logs_ignores_player_id_param(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
    registered_user: dict[str, object],
    registered_user_a: dict[str, object],
) -> None:
    player_id = uuid.UUID(str(registered_user["id"]))
    other_id = uuid.UUID(str(registered_user_a["id"]))
    await _seed_logs(
        db_session,
        [
            _log_entry(player_id=player_id, message="mine"),
            _log_entry(player_id=other_id, message="theirs"),
        ],
    )

    response = await client.get(
        "/api/v2/logs/me",
        params={"player_id": str(other_id)},
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["playerId"] == str(player_id)


async def test_query_all_logs_rejects_non_admin(
    client: AsyncClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings.log, "admin_emails", [])

    response = await client.get("/api/v2/logs", headers=auth_headers)

    assert response.status_code == 403
    assert response.json()["message"] == "Admin access required"


async def test_query_all_logs_returns_all_for_admin(
    admin_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
    registered_user: dict[str, object],
    registered_user_a: dict[str, object],
) -> None:
    first_id = uuid.UUID(str(registered_user["id"]))
    second_id = uuid.UUID(str(registered_user_a["id"]))
    await _seed_logs(
        db_session,
        [
            _log_entry(player_id=first_id, message="first"),
            _log_entry(player_id=second_id, message="second"),
        ],
    )

    response = await admin_client.get("/api/v2/logs", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["total"] == 2


async def test_query_all_logs_filters_by_level(
    admin_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
    registered_user: dict[str, object],
) -> None:
    player_id = uuid.UUID(str(registered_user["id"]))
    await _seed_logs(
        db_session,
        [
            _log_entry(player_id=player_id, message="info"),
            _log_entry(player_id=player_id, message="error", level="ERROR"),
        ],
    )

    response = await admin_client.get(
        "/api/v2/logs?level=ERROR",
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["level"] == "ERROR"


async def test_query_all_logs_filters_by_player_id(
    admin_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
    registered_user: dict[str, object],
    registered_user_a: dict[str, object],
) -> None:
    player_id = uuid.UUID(str(registered_user["id"]))
    other_id = uuid.UUID(str(registered_user_a["id"]))
    await _seed_logs(
        db_session,
        [
            _log_entry(player_id=player_id, message="first"),
            _log_entry(player_id=other_id, message="second"),
        ],
    )

    response = await admin_client.get(
        f"/api/v2/logs?player_id={player_id}",
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["playerId"] == str(player_id)


async def test_query_all_logs_respects_limit_and_offset(
    admin_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
    registered_user: dict[str, object],
) -> None:
    player_id = uuid.UUID(str(registered_user["id"]))
    await _seed_logs(
        db_session,
        [_log_entry(player_id=player_id, message=f"entry-{index}") for index in range(10)],
    )

    response = await admin_client.get(
        "/api/v2/logs?limit=5&offset=5",
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 10
    assert len(body["items"]) == 5
    assert body["limit"] == 5
    assert body["offset"] == 5


async def test_query_all_logs_filter_by_date_range(
    admin_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
    registered_user: dict[str, object],
) -> None:
    player_id = uuid.UUID(str(registered_user["id"]))
    now = datetime.now(UTC)
    await _seed_logs(
        db_session,
        [
            _log_entry(
                player_id=player_id,
                message="old",
                timestamp=now - timedelta(days=5),
            ),
            _log_entry(
                player_id=player_id,
                message="new",
                timestamp=now - timedelta(hours=1),
            ),
        ],
    )

    response = await admin_client.get(
        "/api/v2/logs",
        params={
            "from": (now - timedelta(days=2)).isoformat(),
            "to": now.isoformat(),
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["message"] == "new"


async def test_query_all_logs_invalid_limit_returns_400(
    admin_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await admin_client.get("/api/v2/logs?limit=0", headers=auth_headers)

    assert response.status_code == 400


async def test_query_all_logs_allows_configured_admin_case_insensitively(
    client: AsyncClient,
    auth_headers: dict[str, str],
    registered_user: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = str(registered_user["email"])
    monkeypatch.setattr(settings.log, "admin_emails", [email.upper()])

    response = await client.get("/api/v2/logs", headers=auth_headers)

    assert response.status_code == 200


def test_log_settings_normalize_admin_email_csv() -> None:
    log_settings = LogSettings(admin_emails=" Admin@GameAPI.local, second@example.com ")

    assert log_settings.admin_emails == ["admin@gameapi.local", "second@example.com"]
