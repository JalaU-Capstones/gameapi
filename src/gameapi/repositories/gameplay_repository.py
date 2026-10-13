import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from gameapi.db.models.gameplay import Gameplay

# match_result may be SQL NULL or a JSONB 'null' literal (Python None is persisted as JSON null).
_NO_RESULT = or_(
    Gameplay.match_result.is_(None),
    func.jsonb_typeof(Gameplay.match_result) == "null",
)


class GameplayRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> Sequence[Gameplay]:
        result = await self._session.execute(
            select(Gameplay).order_by(Gameplay.created_date.desc())
        )
        return result.scalars().all()

    async def get_by_id(self, gameplay_id: uuid.UUID) -> Gameplay | None:
        result = await self._session.execute(select(Gameplay).where(Gameplay.id == gameplay_id))
        return result.scalar_one_or_none()

    async def list_by_player(self, player_id: uuid.UUID) -> Sequence[Gameplay]:
        result = await self._session.execute(
            select(Gameplay)
            .where(or_(Gameplay.host_player == player_id, Gameplay.guest_player == player_id))
            .order_by(Gameplay.created_date.desc())
        )
        return result.scalars().all()

    async def list_expired_pending(self, cutoff: datetime) -> Sequence[Gameplay]:
        result = await self._session.execute(
            select(Gameplay)
            .where(Gameplay.invitation_state == "pending", Gameplay.updated_date < cutoff)
            .order_by(Gameplay.updated_date.asc())
        )
        return result.scalars().all()

    async def list_expired_queued(self, cutoff: datetime) -> Sequence[Gameplay]:
        result = await self._session.execute(
            select(Gameplay)
            .where(Gameplay.invitation_state == "queued", Gameplay.updated_date < cutoff)
            .order_by(Gameplay.updated_date.asc())
        )
        return result.scalars().all()

    async def find_active_game_for_user(self, user_id: uuid.UUID) -> Gameplay | None:
        result = await self._session.execute(
            select(Gameplay)
            .where(
                or_(Gameplay.host_player == user_id, Gameplay.guest_player == user_id),
                Gameplay.invitation_state == "accepted",
                _NO_RESULT,
            )
            .order_by(Gameplay.created_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_active_game_for_user(self, user_id: uuid.UUID) -> Gameplay | None:
        return await self.find_active_game_for_user(user_id)

    async def find_next_queued_for_guest(self, guest_id: uuid.UUID) -> Gameplay | None:
        result = await self._session.execute(
            select(Gameplay)
            .where(Gameplay.guest_player == guest_id, Gameplay.invitation_state == "queued")
            .order_by(Gameplay.created_date.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_next_queued_for_guest(self, guest_id: uuid.UUID) -> Gameplay | None:
        return await self.find_next_queued_for_guest(guest_id)

    async def create(self, gameplay: Gameplay) -> Gameplay:
        self._session.add(gameplay)
        await self._session.flush()
        await self._session.refresh(gameplay)
        return gameplay

    async def update(self, gameplay: Gameplay) -> Gameplay:
        await self._session.flush()
        await self._session.refresh(gameplay)
        return gameplay

    async def delete(self, gameplay: Gameplay) -> None:
        await self._session.delete(gameplay)
        await self._session.flush()
