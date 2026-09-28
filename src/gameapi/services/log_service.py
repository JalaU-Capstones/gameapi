from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from gameapi.db.models.log_entry import LogEntry
from gameapi.repositories.log_repository import LogRepository

logger = logging.getLogger(__name__)


class AsyncQueueHandler(logging.Handler):
    """Thread-safe handler that pushes log records onto an asyncio queue."""

    def __init__(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        super().__init__()
        self._queue = queue
        self._loop: asyncio.AbstractEventLoop | None = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def emit(self, record: logging.LogRecord) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return

        try:
            entry = {
                "level": record.levelname,
                "event_type": getattr(record, "event_type", record.name),
                "message": record.getMessage(),
                "player_id": getattr(record, "player_id", None),
                "gameplay_id": getattr(record, "gameplay_id", None),
                "metadata": getattr(record, "metadata", None),
                "timestamp": datetime.fromtimestamp(record.created, tz=UTC),
            }
        except Exception:
            self.handleError(record)
            return

        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(self._safe_put, entry)

    def _safe_put(self, entry: dict[str, Any]) -> None:
        try:
            self._queue.put_nowait(entry)
        except asyncio.QueueFull:
            pass
        except Exception:
            pass


class LogService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        buffer_size: int = 100,
        flush_interval: float = 5.0,
        retention_days: int = 30,
        retention_interval_seconds: float = 86400.0,
        queue_maxsize: int = 1000,
    ) -> None:
        self._session_factory = session_factory
        self._buffer_size = buffer_size
        self._flush_interval = flush_interval
        self._retention_days = retention_days
        self._retention_interval_seconds = retention_interval_seconds
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=queue_maxsize)
        self._buffer: list[dict[str, Any]] = []
        self._flush_lock = asyncio.Lock()
        self._writer_task: asyncio.Task[None] | None = None
        self._retention_task: asyncio.Task[None] | None = None
        self._started = False
        self._handler: AsyncQueueHandler | None = None

    async def start(self) -> None:
        """Start the writer task and the retention task. Idempotent."""
        if self._started:
            return
        self.get_handler().attach_loop(asyncio.get_running_loop())
        self._writer_task = asyncio.create_task(self._writer_loop())
        self._retention_task = asyncio.create_task(self._retention_loop())
        self._started = True

    async def stop(self) -> None:
        """Cancel background tasks and perform a bounded final flush."""
        self._started = False

        if self._retention_task is not None:
            self._retention_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._retention_task
            self._retention_task = None

        if self._writer_task is not None:
            self._writer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._writer_task
            self._writer_task = None

        with contextlib.suppress(Exception):
            await asyncio.wait_for(self.flush_now(), timeout=5.0)

    def get_handler(self) -> AsyncQueueHandler:
        """Return the AsyncQueueHandler for integration with stdlib logging."""
        if self._handler is None:
            self._handler = AsyncQueueHandler(self._queue)
        return self._handler

    async def log(
        self,
        *,
        level: str,
        event_type: str,
        message: str,
        player_id: str | None = None,
        gameplay_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Programmatic API. Enqueues a log entry directly without going through stdlib logging."""
        entry = {
            "level": level.upper(),
            "event_type": event_type,
            "message": message,
            "player_id": player_id,
            "gameplay_id": gameplay_id,
            "metadata": metadata,
            "timestamp": datetime.now(UTC),
        }
        with contextlib.suppress(asyncio.QueueFull):
            self._queue.put_nowait(entry)

    async def _writer_loop(self) -> None:
        while True:
            try:
                async with asyncio.timeout(self._flush_interval):
                    record = await self._queue.get()
            except TimeoutError:
                async with self._flush_lock:
                    await self._flush_buffer_locked()
                continue

            self._buffer.append(record)
            if len(self._buffer) >= self._buffer_size:
                async with self._flush_lock:
                    await self._flush_buffer_locked()

    async def _flush_buffer_locked(self) -> None:
        if not self._buffer:
            return
        records = self._buffer.copy()
        await self._flush(records)
        del self._buffer[: len(records)]

    async def flush_now(self) -> None:
        """Drain queued and buffered records and persist them deterministically."""
        await asyncio.sleep(0)
        async with self._flush_lock:
            while not self._queue.empty():
                try:
                    self._buffer.append(self._queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            await self._flush_buffer_locked()

    async def _flush(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        entries = [
            LogEntry(
                level=str(record.get("level", "INFO")),
                event_type=str(record.get("event_type", "unknown")),
                message=str(record.get("message", "")),
                player_id=record.get("player_id"),
                gameplay_id=record.get("gameplay_id"),
                metadata_=record.get("metadata"),
                timestamp=record.get("timestamp") or datetime.now(UTC),
            )
            for record in records
        ]
        try:
            async with self._session_factory() as session:
                await LogRepository(session).bulk_insert(entries)
                await session.commit()
        except Exception as exc:  # pragma: no cover - guarded path
            print(f"Log persistence failed: {exc}", file=sys.stderr)

    async def _run_retention_once(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=self._retention_days)
        try:
            async with self._session_factory() as session:
                deleted = await LogRepository(session).delete_older_than(cutoff)
                await session.commit()
            if deleted:
                logger.info("log_retention_removed count=%d", deleted)
            return deleted
        except Exception:
            logger.exception("log_retention_failed")
            return 0

    async def _retention_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._retention_interval_seconds)
                await self._run_retention_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("log_retention_failed")

    def _format_record(self, record: dict[str, Any]) -> str:
        return (
            f"{record.get('timestamp')} | {record.get('level')} | "
            f"{record.get('event_type')} | {record.get('message')}"
        )
