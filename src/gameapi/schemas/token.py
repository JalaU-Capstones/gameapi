from pydantic import EmailStr, Field

from gameapi.schemas.base import ApiModel
from gameapi.schemas.user import UserResponse


class LoginRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1)


class LoginResponse(ApiModel):
    token: str
    user: UserResponse
