from datetime import datetime

from pydantic import AliasChoices, EmailStr, Field, field_validator

from gameapi.schemas.base import ApiModel, ObjectIdStr


class UserCreate(ApiModel):
    username: str = Field(
        min_length=3,
        max_length=30,
        validation_alias=AliasChoices("username", "name"),
    )
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @property
    def name(self) -> str:
        return self.username

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.lower()


class UserUpdate(ApiModel):
    username: str | None = Field(
        default=None,
        min_length=3,
        max_length=30,
        validation_alias=AliasChoices("username", "name"),
    )
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)

    @property
    def name(self) -> str | None:
        return self.username

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str | None) -> str | None:
        return value.lower() if value is not None else None


class PublicUserResponse(ApiModel):
    """Minimal user information exposed to other authenticated users."""

    id: ObjectIdStr
    name: str


class UserResponse(PublicUserResponse):
    """Full user information exposed only to the authenticated user."""

    username: str = Field(validation_alias=AliasChoices("username", "name"))
    username_modified_by_system: bool = False
    email: EmailStr
    register_date: datetime
