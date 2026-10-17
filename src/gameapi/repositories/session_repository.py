import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gameapi.db.models.refresh_token import RefreshToken
from gameapi.db.models.session import Session


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, session: Session) -> Session:
        self._session.add(session)
        await self._session.flush()
        await self._session.refresh(session)
        return session

    async def get_by_id(self, session_id: uuid.UUID) -> Session | None:
        result = await self._session.execute(select(Session).where(Session.id == session_id))
        return result.scalar_one_or_none()

    async def count_active_for_user(
        self,
        user_id: uuid.UUID,
        exclude_session_id: uuid.UUID | None = None,
    ) -> int:
        stmt = select(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None))
        if exclude_session_id is not None:
            stmt = stmt.where(Session.id != exclude_session_id)
        result = await self._session.execute(stmt)
        return len(result.scalars().all())

    async def revoke(self, session: Session, reason: str) -> None:
        now = datetime.now(UTC)
        if session.revoked_at is None:
            session.revoked_at = now
            session.revoked_reason = reason
        result = await self._session.execute(
            select(RefreshToken).where(
                RefreshToken.session_id == session.id,
                RefreshToken.revoked_at.is_(None),
            )
        )
        for token in result.scalars().all():
            token.revoked_at = now
        await self._session.flush()

    async def revoke_all_for_user(
        self,
        user_id: uuid.UUID,
        reason: str,
        *,
        exclude_session_id: uuid.UUID | None = None,
    ) -> int:
        now = datetime.now(UTC)
        stmt = select(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None))
        if exclude_session_id is not None:
            stmt = stmt.where(Session.id != exclude_session_id)
        result = await self._session.execute(stmt)
        sessions = result.scalars().all()
        for session in sessions:
            session.revoked_at = now
            session.revoked_reason = reason
            tokens = await self._session.execute(
                select(RefreshToken).where(
                    RefreshToken.session_id == session.id,
                    RefreshToken.revoked_at.is_(None),
                )
            )
            for token in tokens.scalars().all():
                token.revoked_at = now
        await self._session.flush()
        return len(sessions)
