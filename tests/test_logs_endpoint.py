import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient

from gameapi.db.models.log_entry import LogEntry
from gameapi.repositories.log_repository import LogRepository


async def _seed_logs(
    session,
    count: int = 10,
    *,
    level: str = "INFO",
    event_type: str = "user_registered",
) -> None:
    repo = LogRepository(session)
    entries = []
    for index in range(count):
        entries.append(
            LogEntry(
                level=level,
                event_type=event_type,
                message=f"entry {index}",
                player_id=None,
                gameplay_id=None,
                metadata_={"index": index},
                timestamp=datetime.now(UTC) - timedelta(minutes=index),
            )
        )
    await repo.bulk_insert(entries)
    await session.commit()


async def test_query_logs_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v2/logs")
    assert response.status_code == 401


async def test_query_logs_returns_empty_for_fresh_db(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await client.get("/api/v2/logs", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["items"] == []


async def test_query_logs_filters_by_level(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
) -> None:
    await _seed_logs(db_session, count=2, level="INFO", event_type="user_registered")
    await _seed_logs(db_session, count=2, level="ERROR", event_type="login_failed")
    response = await client.get("/api/v2/logs?level=ERROR", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert all(item["level"] == "ERROR" for item in body["items"])


async def test_query_logs_filters_by_event_type(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
) -> None:
    await _seed_logs(db_session, count=3, level="INFO", event_type="user_registered")
    await _seed_logs(db_session, count=2, level="INFO", event_type="gameplay_created")
    response = await client.get("/api/v2/logs?event_type=user_registered", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert all(item["eventType"] == "user_registered" for item in body["items"])


async def test_query_logs_respects_limit_and_offset(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
) -> None:
    await _seed_logs(db_session, count=10, level="INFO", event_type="test_event")
    response = await client.get("/api/v2/logs?limit=5&offset=5", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 10
    assert len(body["items"]) == 5
    assert body["limit"] == 5
    assert body["offset"] == 5


async def test_query_logs_filter_by_player_id(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
    registered_user: dict[str, object],
    registered_user_a: dict[str, object],
) -> None:
    player_id = uuid.UUID(str(registered_user["id"]))
    other_id = uuid.UUID(str(registered_user_a["id"]))
    repo = LogRepository(db_session)
    await repo.bulk_insert(
        [
            LogEntry(
                level="INFO",
                event_type="user_registered",
                message="match",
                player_id=player_id,
                gameplay_id=None,
                metadata_={},
                timestamp=datetime.now(UTC),
            ),
            LogEntry(
                level="INFO",
                event_type="user_registered",
                message="other",
                player_id=other_id,
                gameplay_id=None,
                metadata_={},
                timestamp=datetime.now(UTC),
            ),
        ]
    )
    await db_session.commit()
    response = await client.get(f"/api/v2/logs?player_id={player_id}", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["playerId"] == str(player_id)


async def test_query_logs_filter_by_date_range(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
) -> None:
    now = datetime.now(UTC)
    repo = LogRepository(db_session)
    await repo.bulk_insert(
        [
            LogEntry(
                level="INFO",
                event_type="user_registered",
                message="old",
                player_id=None,
                gameplay_id=None,
                metadata_={},
                timestamp=now - timedelta(days=5),
            ),
            LogEntry(
                level="INFO",
                event_type="user_registered",
                message="new",
                player_id=None,
                gameplay_id=None,
                metadata_={},
                timestamp=now - timedelta(hours=1),
            ),
        ]
    )
    await db_session.commit()
    response = await client.get(
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


async def test_query_logs_invalid_limit_returns_400(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await client.get("/api/v2/logs?limit=0", headers=auth_headers)
    assert response.status_code == 400
