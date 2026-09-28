import uuid
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from gameapi.db.models.log_entry import LogEntry


class LogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_insert(self, entries: list[LogEntry]) -> None:
        """Insert many log entries in a single transaction."""
        if not entries:
            return
        self._session.add_all(entries)
        await self._session.flush()

    async def query(
        self,
        *,
        level: str | None = None,
        event_type: str | None = None,
        player_id: uuid.UUID | None = None,
        gameplay_id: uuid.UUID | None = None,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[LogEntry], int]:
        """Return (entries, total_count) with filters applied."""
        stmt = select(LogEntry)
        count_stmt = select(func.count()).select_from(LogEntry)

        if level is not None:
            stmt = stmt.where(LogEntry.level == level)
            count_stmt = count_stmt.where(LogEntry.level == level)
        if event_type is not None:
            stmt = stmt.where(LogEntry.event_type == event_type)
            count_stmt = count_stmt.where(LogEntry.event_type == event_type)
        if player_id is not None:
            stmt = stmt.where(LogEntry.player_id == player_id)
            count_stmt = count_stmt.where(LogEntry.player_id == player_id)
        if gameplay_id is not None:
            stmt = stmt.where(LogEntry.gameplay_id == gameplay_id)
            count_stmt = count_stmt.where(LogEntry.gameplay_id == gameplay_id)
        if from_dt is not None:
            stmt = stmt.where(LogEntry.timestamp >= from_dt)
            count_stmt = count_stmt.where(LogEntry.timestamp >= from_dt)
        if to_dt is not None:
            stmt = stmt.where(LogEntry.timestamp <= to_dt)
            count_stmt = count_stmt.where(LogEntry.timestamp <= to_dt)

        stmt = stmt.order_by(LogEntry.timestamp.desc(), LogEntry.id)
        total_count = (await self._session.execute(count_stmt)).scalar_one()
        result = await self._session.execute(stmt.limit(limit).offset(offset))
        return list(result.scalars().all()), int(total_count)

    async def delete_older_than(self, cutoff: datetime) -> int:
        """Delete logs with timestamp < cutoff. Return the count of deleted rows."""
        result = await self._session.execute(delete(LogEntry).where(LogEntry.timestamp < cutoff))
        rowcount = getattr(result, "rowcount", None)
        return int(rowcount or 0)
