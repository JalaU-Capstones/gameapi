import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, or_, select, update
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

    async def get_by_id_for_update(self, gameplay_id: uuid.UUID) -> Gameplay | None:
        result = await self._session.execute(
            select(Gameplay)
            .where(Gameplay.id == gameplay_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def touch_updated_date(self, gameplay_id: uuid.UUID) -> datetime | None:
        result = await self._session.execute(
            update(Gameplay)
            .where(Gameplay.id == gameplay_id)
            .values(updated_date=func.now())
            .returning(Gameplay.updated_date)
            .execution_options(synchronize_session="fetch")
        )
        return result.scalar_one_or_none()

    async def expire_if_stale(
        self, gameplay_id: uuid.UUID, state: str, cutoff: datetime
    ) -> datetime | None:
        result = await self._session.execute(
            update(Gameplay)
            .where(
                Gameplay.id == gameplay_id,
                Gameplay.invitation_state == state,
                Gameplay.updated_date < cutoff,
                _NO_RESULT,
            )
            .values(
                invitation_state="expired",
                match_result={"winner": None, "reason": "expired"},
                updated_date=func.now(),
            )
            .returning(Gameplay.updated_date)
            .execution_options(synchronize_session="fetch")
        )
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

    async def has_pending_or_queued_invitation(self, user_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            select(Gameplay.id)
            .where(
                or_(Gameplay.host_player == user_id, Gameplay.guest_player == user_id),
                or_(Gameplay.invitation_state == "pending", Gameplay.invitation_state == "queued"),
            )
            .limit(1)
        )
        return result.scalar() is not None

    async def list_active_game_user_ids(self) -> Sequence[uuid.UUID]:
        host_ids = select(Gameplay.host_player).where(
            Gameplay.invitation_state == "accepted",
            _NO_RESULT,
        )
        guest_ids = select(Gameplay.guest_player).where(
            Gameplay.invitation_state == "accepted",
            Gameplay.guest_player.is_not(None),
            _NO_RESULT,
        )
        result = await self._session.execute(host_ids.union(guest_ids))
        return [row for row in result.scalars().all() if row is not None]

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
