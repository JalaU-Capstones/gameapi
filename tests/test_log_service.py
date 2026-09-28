import asyncio
import io
import uuid
from contextlib import redirect_stderr
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from gameapi.db.models.log_entry import LogEntry
from gameapi.repositories.log_repository import LogRepository
from gameapi.services.log_service import LogService


@pytest.fixture
async def log_service_factory(db_session):
    async def _factory(
        *,
        buffer_size: int = 2,
        flush_interval: float = 0.1,
        queue_maxsize: int = 10,
    ) -> LogService:
        factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
        service = LogService(
            factory,
            buffer_size=buffer_size,
            flush_interval=flush_interval,
            queue_maxsize=queue_maxsize,
        )
        await service.start()
        return service

    return _factory


async def _seed_log_entries(
    session,
    count: int,
    *,
    level: str = "INFO",
    event_type: str = "test_event",
) -> list[LogEntry]:
    repo = LogRepository(session)
    entries: list[LogEntry] = []
    for index in range(count):
        entry = LogEntry(
            level=level,
            event_type=event_type,
            message=f"Entry {index}",
            player_id=None,
            gameplay_id=None,
            metadata_={"index": index},
            timestamp=datetime.now(UTC) - timedelta(minutes=index),
        )
        entries.append(entry)
    await repo.bulk_insert(entries)
    await session.commit()
    return entries


async def test_log_service_enqueues_record(log_service_factory) -> None:
    service = await log_service_factory(buffer_size=5)
    try:
        await service.log(
            level="INFO",
            event_type="user_registered",
            message="User registered",
            player_id=str(uuid.uuid4()),
            metadata={"email": "alice@example.com"},
        )
        assert service._queue.qsize() >= 1
    finally:
        await service.stop()


async def test_log_service_flushes_when_buffer_full(log_service_factory, db_session) -> None:
    service = await log_service_factory(buffer_size=2, flush_interval=1)
    try:
        await service.log(level="INFO", event_type="user_registered", message="one")
        await service.log(level="INFO", event_type="user_registered", message="two")
        for _ in range(50):
            rows = (await db_session.execute(select(LogEntry))).scalars().all()
            if len(rows) >= 2:
                break
            await asyncio.sleep(0.05)
        assert len((await db_session.execute(select(LogEntry))).scalars().all()) >= 2
    finally:
        await service.stop()


async def test_log_service_flushes_on_interval(log_service_factory, db_session) -> None:
    service = await log_service_factory(buffer_size=50, flush_interval=0.2)
    try:
        await service.log(level="WARNING", event_type="login_failed", message="bad pass")
        await asyncio.sleep(0.5)
        rows = (await db_session.execute(select(LogEntry))).scalars().all()
        assert len(rows) >= 1
    finally:
        await service.stop()


async def test_log_service_flushes_on_stop(log_service_factory, db_session) -> None:
    service = await log_service_factory(buffer_size=100, flush_interval=999)
    try:
        await service.log(level="ERROR", event_type="user_deleted", message="deleted")
        await service.stop()
        rows = (await db_session.execute(select(LogEntry))).scalars().all()
        assert len(rows) >= 1
    finally:
        await service.stop()


async def test_log_service_falls_back_to_stderr_on_db_error(
    log_service_factory,
    monkeypatch,
) -> None:
    service = await log_service_factory(buffer_size=1, flush_interval=999)
    try:

        async def _boom(*args, **kwargs):
            raise RuntimeError("db down")

        monkeypatch.setattr("gameapi.repositories.log_repository.LogRepository.bulk_insert", _boom)
        captured = io.StringIO()
        with redirect_stderr(captured):
            await service.log(level="ERROR", event_type="db_error", message="oops")
            await asyncio.sleep(0.2)
        assert "db down" in captured.getvalue()
    finally:
        await service.stop()


async def test_log_service_retention_deletes_old_logs(db_session, log_service_factory) -> None:
    service = await log_service_factory(buffer_size=10, flush_interval=999)
    try:
        old_time = datetime.now(UTC) - timedelta(days=45)
        new_time = datetime.now(UTC) - timedelta(days=2)
        await LogRepository(db_session).bulk_insert(
            [
                LogEntry(
                    level="INFO",
                    event_type="old_event",
                    message="old",
                    metadata_={"source": "old"},
                    timestamp=old_time,
                ),
                LogEntry(
                    level="INFO",
                    event_type="new_event",
                    message="new",
                    metadata_={"source": "new"},
                    timestamp=new_time,
                ),
            ]
        )
        await db_session.commit()

        deleted = await service._run_retention_once()
        assert deleted == 1
        remaining = (await db_session.execute(select(LogEntry))).scalars().all()
        assert len(remaining) == 1
    finally:
        await service.stop()


async def test_log_service_queue_full_drops_silently(log_service_factory) -> None:
    service = await log_service_factory(buffer_size=10, flush_interval=999, queue_maxsize=1)
    try:
        await service.log(level="INFO", event_type="one", message="one")
        await service.log(level="INFO", event_type="two", message="two")
        await service.log(level="INFO", event_type="three", message="three")
        assert service._queue.qsize() <= 1
    finally:
        await service.stop()
