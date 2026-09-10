from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from gameapi.schemas.base import ApiModel, ObjectIdStr


class UserCreate(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.lower()


class UserUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str | None) -> str | None:
        return value.lower() if value is not None else None


class UserResponse(ApiModel):
    id: ObjectIdStr
    name: str
    email: EmailStr
    register_date: datetime
