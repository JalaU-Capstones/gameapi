import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from gameapi.api.deps import CurrentUser, LogAdmin, SessionDep
from gameapi.core.config import settings
from gameapi.core.rate_limit import rate_limit
from gameapi.repositories.log_repository import LogRepository
from gameapi.schemas.log import LogEntryResponse, LogsQueryResponse

router = APIRouter(prefix="/logs", tags=["Logs"])


async def _query_logs(
    session: AsyncSession,
    *,
    level: str | None,
    event_type: str | None,
    player_id: uuid.UUID | None,
    gameplay_id: uuid.UUID | None,
    from_dt: datetime | None,
    to_dt: datetime | None,
    limit: int,
    offset: int,
) -> LogsQueryResponse:
    entries, total = await LogRepository(session).query(
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


@router.get(
    "/me",
    response_model=LogsQueryResponse,
    summary="Query logs belonging to the current user",
    responses={429: {"description": "Rate limit exceeded"}},
)
@rate_limit(settings.rate_limit.logs_me)
async def query_my_logs(
    request: Request,
    response: Response,
    current_user: CurrentUser,
    session: SessionDep,
    level: Annotated[str | None, Query()] = None,
    event_type: Annotated[str | None, Query()] = None,
    gameplay_id: Annotated[uuid.UUID | None, Query()] = None,
    from_dt: Annotated[datetime | None, Query(alias="from")] = None,
    to_dt: Annotated[datetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LogsQueryResponse:
    """Query only the current user's logs; unknown query parameters are ignored."""
    del request
    return await _query_logs(
        session,
        level=level,
        event_type=event_type,
        player_id=uuid.UUID(str(current_user.id)),
        gameplay_id=gameplay_id,
        from_dt=from_dt,
        to_dt=to_dt,
        limit=limit,
        offset=offset,
    )


@router.get(
    "",
    response_model=LogsQueryResponse,
    summary="Query all logs (admin only)",
    responses={
        403: {"description": "Admin access required"},
        429: {"description": "Rate limit exceeded"},
    },
)
@rate_limit(settings.rate_limit.logs_admin)
async def query_all_logs(
    request: Request,
    response: Response,
    _: LogAdmin,
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
    del request
    return await _query_logs(
        session,
        level=level,
        event_type=event_type,
        player_id=player_id,
        gameplay_id=gameplay_id,
        from_dt=from_dt,
        to_dt=to_dt,
        limit=limit,
        offset=offset,
    )
