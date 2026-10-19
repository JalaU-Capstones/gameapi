from datetime import datetime

from pydantic import AliasChoices, EmailStr, Field, field_validator

from gameapi.core.username import USERNAME_MAX_LENGTH, USERNAME_MIN_LENGTH, USERNAME_PATTERN
from gameapi.schemas.base import ApiModel, ObjectIdStr

_USERNAME_DESCRIPTION = (
    "Unique username: 3-30 chars, alphanumeric, hyphens, and underscores. "
    "Must begin and end with a letter or digit."
)


class UserCreate(ApiModel):
    username: str = Field(
        min_length=USERNAME_MIN_LENGTH,
        max_length=USERNAME_MAX_LENGTH,
        pattern=USERNAME_PATTERN,
        description=_USERNAME_DESCRIPTION,
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
        min_length=USERNAME_MIN_LENGTH,
        max_length=USERNAME_MAX_LENGTH,
        pattern=USERNAME_PATTERN,
        description=_USERNAME_DESCRIPTION,
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
