import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from gameapi.api.deps import CurrentUser, SessionDep
from gameapi.repositories.log_repository import LogRepository
from gameapi.schemas.log import LogEntryResponse, LogsQueryResponse

router = APIRouter(tags=["Logs"])


@router.get(
    "/logs",
    response_model=LogsQueryResponse,
    summary="Query persistent logs",
)
async def query_logs(
    current_user: CurrentUser,
    session: SessionDep,
    level: Annotated[str | None, Query()] = None,
    event_type: Annotated[str | None, Query()] = None,
    player_id: Annotated[uuid.UUID | None, Query()] = None,
    gameplay_id: Annotated[uuid.UUID | None, Query()] = None,
    from_dt: Annotated[datetime | None, Query(alias="from")] = None,
    to_dt: Annotated[datetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LogsQueryResponse:
    del current_user
    repo = LogRepository(session)
    entries, total = await repo.query(
        level=level,
        event_type=event_type,
        player_id=player_id,
        gameplay_id=gameplay_id,
        from_dt=from_dt,
        to_dt=to_dt,
        limit=limit,
        offset=offset,
    )
    return LogsQueryResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[LogEntryResponse.from_model(entry) for entry in entries],
    )
