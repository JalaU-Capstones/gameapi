from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from gameapi.models.common import PyObjectId


class GameplayDocument(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )

    id: PyObjectId | None = Field(default=None, alias="_id")
    current_positions: str = ""
    host_player: str
    guest_player: str | None = None
    player_turn: str
    match_result: str | None = None
    created_date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_date: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_mongo(self) -> dict[str, Any]:
        data = self.model_dump(by_alias=True, mode="python")
        data.pop("_id", None)
        return data

    @classmethod
    def from_mongo(cls, document: dict[str, Any]) -> "GameplayDocument":
        return cls.model_validate(document)
