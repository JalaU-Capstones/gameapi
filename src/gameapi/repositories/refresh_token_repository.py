import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from gameapi.db.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, token: RefreshToken) -> RefreshToken:
        self._session.add(token)
        await self._session.flush()
        await self._session.refresh(token)
        return token

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def revoke(self, token: RefreshToken) -> None:
        """Set revoked_at to now() if not already revoked."""
        if token.revoked_at is None:
            token.revoked_at = datetime.now(UTC)
        await self._session.flush()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        """Revoke all active tokens for a user. Return count."""
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
        )
        tokens = result.scalars().all()
        for token in tokens:
            token.revoked_at = now
        await self._session.flush()
        return len(tokens)

    async def delete_expired(self) -> int:
        """Delete tokens whose expires_at < now(). Return count."""
        now = datetime.now(UTC)
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.expires_at < now)
        )
        expired_tokens = result.scalars().all()
        for token in expired_tokens:
            await self._session.delete(token)
        await self._session.flush()
        return len(expired_tokens)
