import uuid
from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from gameapi.db.models.gameplay import Gameplay


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
