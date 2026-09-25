import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gameapi.db.base import Base

if TYPE_CHECKING:
    from gameapi.db.models.gameplay import Gameplay


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    register_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    hosted_gameplays: Mapped[list["Gameplay"]] = relationship(
        "Gameplay",
        foreign_keys="Gameplay.host_player",
        back_populates="host",
    )
    joined_gameplays: Mapped[list["Gameplay"]] = relationship(
        "Gameplay",
        foreign_keys="Gameplay.guest_player",
        back_populates="guest",
    )

    @property
    def password(self) -> str:
        return self.password_hash

    @password.setter
    def password(self, value: str) -> None:
        self.password_hash = value
