from __future__ import annotations

from datetime import datetime
from typing import Any

from gameapi.db.models.log_entry import LogEntry
from gameapi.schemas.base import ApiModel


class LogEntryResponse(ApiModel):
    id: str
    level: str
    event_type: str
    message: str
    player_id: str | None
    gameplay_id: str | None
    metadata: dict[str, Any] | None
    timestamp: datetime

    @classmethod
    def from_model(cls, entry: LogEntry) -> LogEntryResponse:
        return cls(
            id=str(entry.id),
            level=entry.level,
            event_type=entry.event_type,
            message=entry.message,
            player_id=str(entry.player_id) if entry.player_id is not None else None,
            gameplay_id=str(entry.gameplay_id) if entry.gameplay_id is not None else None,
            metadata=entry.metadata_ if entry.metadata_ is not None else None,
            timestamp=entry.timestamp,
        )


class LogsQueryResponse(ApiModel):
    total: int
    limit: int
    offset: int
    items: list[LogEntryResponse]
