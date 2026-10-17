import asyncio
import io
import logging
import threading
from contextlib import redirect_stderr
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from gameapi.db.models.log_entry import LogEntry
from gameapi.repositories.log_repository import LogRepository
from gameapi.services.log_service import AsyncQueueHandler, LogService


@pytest_asyncio.fixture
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


async def test_log_service_flush_now_is_deterministic(
    log_service_factory,
    db_session,
) -> None:
    service = await log_service_factory(buffer_size=100, flush_interval=999)
    try:
        await service.log(level="INFO", event_type="user_registered", message="event")
        await service.flush_now()
        rows = (await db_session.execute(select(LogEntry))).scalars().all()
        assert len(rows) >= 1
    finally:
        await service.stop()


async def test_log_service_stop_is_idempotent(log_service_factory) -> None:
    service = await log_service_factory()

    await service.stop()
    await service.stop()


async def test_log_service_handler_is_thread_safe(
    log_service_factory,
    db_session,
) -> None:
    service = await log_service_factory(buffer_size=10, flush_interval=999)
    root_logger = logging.getLogger()
    previous_level = root_logger.level
    root_logger.setLevel(logging.INFO)
    handler = service.get_handler()
    assert handler is service.get_handler()
    root_logger.addHandler(handler)
    try:

        def _emit_from_thread() -> None:
            logging.getLogger("test_threaded").info(
                "from other thread",
                extra={"event_type": "threaded_log"},
            )

        thread = threading.Thread(target=_emit_from_thread)
        thread.start()
        thread.join(timeout=2)
        assert not thread.is_alive()

        await service.flush_now()
        rows = (await db_session.execute(select(LogEntry))).scalars().all()
        assert any(row.event_type == "threaded_log" for row in rows)
    finally:
        root_logger.removeHandler(handler)
        root_logger.setLevel(previous_level)
        await service.stop()


async def test_log_service_queue_handler_is_safe_when_loop_is_missing_or_queue_is_full() -> None:
    handler = AsyncQueueHandler(asyncio.Queue(maxsize=1))
    record = logging.LogRecord("demo", logging.INFO, __file__, 1, "hello world", (), None)

    handler.emit(record)

    loop = asyncio.get_running_loop()
    handler.attach_loop(loop)
    handler._queue.put_nowait({"payload": "occupied"})
    handler._safe_put({"payload": "next"})

    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    original = handler._queue.put_nowait
    handler._queue.put_nowait = _raise  # type: ignore[assignment]
    try:
        handler._safe_put({"payload": "fallback"})
    finally:
        handler._queue.put_nowait = original  # type: ignore[assignment]

    assert handler._queue.qsize() == 1


async def test_log_service_retention_failure_returns_zero_and_logs(monkeypatch) -> None:
    async def _boom(*args, **kwargs):
        raise RuntimeError("retention boom")

    class _FakeSessionFactory:
        def __call__(self):
            return _FakeSession()

    class _FakeSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    service = LogService(_FakeSessionFactory(), buffer_size=10, flush_interval=999)
    monkeypatch.setattr("gameapi.services.log_service.LogRepository.delete_older_than", _boom)
    logged = []
    monkeypatch.setattr(
        "gameapi.services.log_service.logger.exception", lambda *args, **kwargs: logged.append(args)
    )

    result = await service._run_retention_once()

    assert result == 0
    assert logged


async def test_log_service_format_record_roundtrips_values() -> None:
    service = LogService(session_factory=object(), buffer_size=10, flush_interval=999)

    formatted = service._format_record(
        {
            "timestamp": "2024-01-01T00:00:00Z",
            "level": "WARNING",
            "event_type": "user_login_failed",
            "message": "bad credentials",
        }
    )

    assert "WARNING" in formatted
    assert "user_login_failed" in formatted
    assert "bad credentials" in formatted
