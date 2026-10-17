import logging
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from gameapi.core.config import settings
from gameapi.core.security import TokenDecodeError, decode_access_token
from gameapi.db.session import session_scope
from gameapi.repositories.refresh_token_repository import RefreshTokenRepository
from gameapi.repositories.session_repository import SessionRepository
from gameapi.schemas.user import UserResponse
from gameapi.services import AuthService, GameplayService, UserService

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


class AuthHTTPException(HTTPException):
    def __init__(self, status_code: int, detail: str, code: str) -> None:
        super().__init__(
            status_code=status_code,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )
        self.code = code


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


def get_session_repository(session: SessionDep) -> SessionRepository:
    return SessionRepository(session)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
GameplayServiceDep = Annotated[GameplayService, Depends(get_gameplay_service)]
SessionRepositoryDep = Annotated[SessionRepository, Depends(get_session_repository)]


def get_auth_service(
    user_service: UserServiceDep,
    refresh_repo: Annotated[RefreshTokenRepository, Depends(get_refresh_token_repository)],
    session_repo: SessionRepositoryDep,
) -> AuthService:
    return AuthService(user_service, refresh_repo, session_repo)


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
    except (TokenDecodeError, ValidationError) as exc:
        if isinstance(exc, ValidationError):
            try:
                payload = jwt.decode(
                    token,
                    settings.jwt.secret_key,
                    algorithms=[settings.jwt.algorithm],
                    audience=settings.jwt.audience,
                    issuer=settings.jwt.issuer,
                )
            except JWTError as legacy_exc:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token",
                    headers={"WWW-Authenticate": "Bearer"},
                ) from legacy_exc
            user_id = str(payload.get("sub")) if payload.get("sub") is not None else None
            if user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token",
                    headers={"WWW-Authenticate": "Bearer"},
                ) from None
            logger.info(
                "Legacy token used",
                extra={"event_type": "legacy_token_used", "player_id": user_id},
            )
            user = await user_service.get_by_id(user_id)
            if user is None:
                raise AuthHTTPException(
                    401,
                    "User no longer exists",
                    "USER_NOT_FOUND",
                ) from exc
            return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    session_repo = None
    if hasattr(user_service, "_session"):
        session_repo = SessionRepository(user_service._session)

    sid = getattr(claims, "sid", None)
    if session_repo is not None and sid is not None:
        # `last_seen_at` is intentionally left alone here; the refresh flow and
        # future takeover logic update it when a session is actively used.
        session = await session_repo.get_by_id(UUID(str(sid)))
        if session is None or session.revoked_at is not None:
            code = (
                "SESSION_REPLACED"
                if session is not None and session.revoked_reason == "session_replaced"
                else "SESSION_REVOKED"
            )
            raise AuthHTTPException(401, "Session ended", code)
    elif session_repo is not None:
        logger.info(
            "Legacy token used",
            extra={"event_type": "legacy_token_used", "player_id": claims.sub},
        )

    user = await user_service.get_by_id(claims.sub)
    if user is None:
        raise AuthHTTPException(401, "User no longer exists", "USER_NOT_FOUND")
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
