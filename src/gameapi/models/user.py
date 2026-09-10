from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from gameapi.models.common import PyObjectId


class UserDocument(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )

    id: PyObjectId | None = Field(default=None, alias="_id")
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str
    register_date: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_mongo(self) -> dict[str, Any]:
        data = self.model_dump(by_alias=True, mode="python")
        data.pop("_id", None)
        return data

    @classmethod
    def from_mongo(cls, document: dict[str, Any]) -> "UserDocument":
        return cls.model_validate(document)
