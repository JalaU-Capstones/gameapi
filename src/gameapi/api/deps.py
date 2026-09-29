from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from gameapi.core.config import settings
from gameapi.core.security import TokenDecodeError, decode_access_token
from gameapi.db.session import session_scope
from gameapi.repositories.refresh_token_repository import RefreshTokenRepository
from gameapi.schemas.user import UserResponse
from gameapi.services import AuthService, GameplayService, UserService

bearer_scheme = HTTPBearer(auto_error=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_scope() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_user_service(session: SessionDep) -> UserService:
    return UserService(session)


def get_gameplay_service(session: SessionDep) -> GameplayService:
    return GameplayService(session)


def get_refresh_token_repository(session: SessionDep) -> RefreshTokenRepository:
    return RefreshTokenRepository(session)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
GameplayServiceDep = Annotated[GameplayService, Depends(get_gameplay_service)]


def get_auth_service(
    user_service: UserServiceDep,
    refresh_repo: Annotated[RefreshTokenRepository, Depends(get_refresh_token_repository)],
) -> AuthService:
    return AuthService(user_service, refresh_repo)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    user_service: UserServiceDep,
    access_token_cookie: Annotated[
        str | None,
        Cookie(alias=settings.auth.access_cookie_name),
    ] = None,
) -> UserResponse:
    token: str | None = None
    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    elif access_token_cookie:
        token = access_token_cookie

    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = decode_access_token(token)
    except TokenDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await user_service.get_by_id(claims.sub)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[UserResponse, Depends(get_current_user)]


async def require_log_admin(current_user: CurrentUser) -> UserResponse:
    """Ensure the authenticated user is configured for global log access."""
    admin_emails = {email.lower() for email in settings.log.admin_emails}
    if current_user.email.lower() not in admin_emails:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


LogAdmin = Annotated[UserResponse, Depends(require_log_admin)]
