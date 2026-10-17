import uuid
from datetime import UTC, datetime, timedelta

from gameapi.core.config import settings
from gameapi.core.security import (
    create_access_token_short,
    generate_refresh_token,
    hash_refresh_token,
    verify_password,
)
from gameapi.db.models.refresh_token import RefreshToken
from gameapi.db.models.session import Session
from gameapi.db.models.user import User
from gameapi.repositories.refresh_token_repository import RefreshTokenRepository
from gameapi.repositories.session_repository import SessionRepository
from gameapi.schemas.user import UserCreate, UserResponse
from gameapi.services.exceptions import InvalidCredentialsError, InvalidRefreshTokenError
from gameapi.services.user_service import UserService


class AuthService:
    def __init__(
        self,
        user_service: UserService,
        refresh_repo: RefreshTokenRepository,
        session_repo: SessionRepository | None = None,
    ) -> None:
        self._user_service = user_service
        self._refresh_repo = refresh_repo
        self._session_repo = session_repo or SessionRepository(user_service._session)

    async def _create_session(self, user_id: uuid.UUID) -> Session:
        session = Session(user_id=user_id)
        return await self._session_repo.create(session)

    async def _issue_tokens_with_session(
        self,
        user: User | UserResponse,
        session: Session,
    ) -> tuple[str, str]:
        if user.id is None:
            raise RuntimeError("Persisted user has no id")

        subject_id = uuid.UUID(str(user.id))
        access_token = create_access_token_short(
            subject=str(user.id),
            email=user.email,
            name=user.name,
            sid=str(session.id),
        )
        raw_refresh_token, token_hash = generate_refresh_token()
        expires_at = datetime.now(UTC) + timedelta(days=settings.auth.refresh_token_expire_days)
        refresh_token = RefreshToken(
            user_id=subject_id,
            session_id=session.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        await self._refresh_repo.create(refresh_token)
        return access_token, raw_refresh_token

    async def login(self, email: str, password: str) -> tuple[str, str, User, Session, int]:
        """
        Validate credentials.
        Return (access_token, raw_refresh_token, user, session, other_active_sessions).
        """
        user = await self._user_service.get_by_email(email)
        if user is None or not verify_password(password, user.password):
            raise InvalidCredentialsError()

        session = await self._create_session(user.id)
        access_token, raw_refresh_token = await self._issue_tokens_with_session(user, session)
        other_active = await self._session_repo.count_active_for_user(
            user.id, exclude_session_id=session.id
        )
        return access_token, raw_refresh_token, user, session, other_active

    async def register(self, data: UserCreate) -> tuple[str, str, UserResponse, Session, int]:
        """Create the user and immediately issue auth tokens for the new session."""
        user = await self._user_service.create(data)
        session = await self._create_session(uuid.UUID(str(user.id)))
        access_token, raw_refresh_token = await self._issue_tokens_with_session(user, session)
        return access_token, raw_refresh_token, user, session, 0

    async def refresh(self, raw_refresh_token: str) -> tuple[str, str]:
        """
        Validate the refresh token.
        - Look up by hash.
        - Verify not revoked and not expired.
        - Rotate: revoke the old token, issue a new refresh token.
        - Issue a new access token.
        Return (new_access_token, new_raw_refresh_token).
        Raise InvalidRefreshTokenError if invalid.
        """
        token_hash = hash_refresh_token(raw_refresh_token)
        refresh_token = await self._refresh_repo.get_by_hash(token_hash)
        if refresh_token is None:
            raise InvalidRefreshTokenError()
        if refresh_token.revoked_at is not None:
            raise InvalidRefreshTokenError()
        if refresh_token.expires_at <= datetime.now(UTC):
            raise InvalidRefreshTokenError()

        if refresh_token.session_id is None:
            session = await self._create_session(refresh_token.user_id)
            refresh_token.session_id = session.id
            await self._refresh_repo.update(refresh_token)
        else:
            existing_session = await self._session_repo.get_by_id(refresh_token.session_id)
            if existing_session is None or existing_session.revoked_at is not None:
                raise InvalidRefreshTokenError()
            session = existing_session

        await self._refresh_repo.revoke(refresh_token)

        user = await self._user_service.get_by_id(str(refresh_token.user_id))
        if user is None:
            raise InvalidRefreshTokenError()

        new_access_token = create_access_token_short(
            subject=str(user.id),
            email=user.email,
            name=user.name,
            sid=str(session.id),
        )
        new_raw_refresh_token, new_token_hash = generate_refresh_token()
        new_refresh_token = RefreshToken(
            user_id=refresh_token.user_id,
            session_id=session.id,
            token_hash=new_token_hash,
            expires_at=datetime.now(UTC) + timedelta(days=settings.auth.refresh_token_expire_days),
        )
        await self._refresh_repo.create(new_refresh_token)
        return new_access_token, new_raw_refresh_token

    async def logout(self, raw_refresh_token: str) -> None:
        """Revoke the refresh token if it exists. Idempotent."""
        if not raw_refresh_token:
            return
        refresh_token = await self._refresh_repo.get_by_hash(hash_refresh_token(raw_refresh_token))
        if refresh_token is None:
            return
        if refresh_token.session_id is not None:
            session = await self._session_repo.get_by_id(refresh_token.session_id)
            if session is not None and session.revoked_at is None:
                await self._session_repo.revoke(session, reason="logout")
            return
        await self._refresh_repo.revoke(refresh_token)

    async def get_user_from_access(self, user_id: uuid.UUID) -> UserResponse | None:
        """Convenience for the /me endpoint."""
        return await self._user_service.get_by_id(str(user_id))
