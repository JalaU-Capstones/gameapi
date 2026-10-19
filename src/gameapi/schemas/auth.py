from pydantic import EmailStr, Field

from gameapi.schemas.base import ApiModel
from gameapi.schemas.user import UserResponse


class LoginRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1)


class LoginResponse(ApiModel):
    access_token: str = Field(serialization_alias="access_token", validation_alias="access_token")
    token_type: str = Field(
        default="bearer", serialization_alias="token_type", validation_alias="token_type"
    )
    user: UserResponse
    other_active_sessions: int = Field(
        default=0,
        serialization_alias="other_active_sessions",
        validation_alias="other_active_sessions",
    )
    username_was_auto_generated: bool = Field(
        default=False,
        serialization_alias="username_was_auto_generated",
        validation_alias="username_was_auto_generated",
    )


class RegisterResponse(LoginResponse):
    pass


class RefreshResponse(ApiModel):
    access_token: str = Field(serialization_alias="access_token", validation_alias="access_token")
    token_type: str = Field(
        default="bearer", serialization_alias="token_type", validation_alias="token_type"
    )
