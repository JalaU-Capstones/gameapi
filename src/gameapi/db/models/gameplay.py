import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gameapi.db.base import Base

if TYPE_CHECKING:
    from gameapi.db.models.user import User


class Gameplay(Base):
    __tablename__ = "gameplays"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    current_positions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    host_player: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    guest_player: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    player_turn: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    match_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    host: Mapped["User"] = relationship(
        "User",
        foreign_keys=[host_player],
        back_populates="hosted_gameplays",
    )
    guest: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[guest_player],
        back_populates="joined_gameplays",
    )
