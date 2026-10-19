from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select, update

from gameapi.core.security import hash_refresh_token
from gameapi.db.models.refresh_token import RefreshToken
from gameapi.db.models.session import Session
from gameapi.db.models.user import User
from gameapi.repositories.refresh_token_repository import RefreshTokenRepository
from gameapi.repositories.session_repository import SessionRepository
from gameapi.schemas.auth import LoginResponse
from gameapi.schemas.user import UserCreate
from gameapi.services.auth_service import AuthService
from gameapi.services.exceptions import InvalidRefreshTokenError
from gameapi.services.user_service import UserService


async def test_auth_service_refresh_rejects_revoked_token(db_session) -> None:
    user_service = UserService(db_session)
    repo = RefreshTokenRepository(db_session)
    auth_service = AuthService(user_service, repo)
    user = await user_service.create(
        UserCreate(name="Revoked", email="revoked@example.com", password="password123")
    )
    session = await SessionRepository(db_session).create(Session(user_id=user.id))
    raw_token = "revoked-refresh-token"
    await repo.create(
        RefreshToken(
            user_id=user.id,
            session_id=session.id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(days=1),
            revoked_at=datetime.now(UTC),
        )
    )

    with pytest.raises(InvalidRefreshTokenError):
        await auth_service.refresh(raw_token)


async def test_auth_service_refresh_rejects_expired_token(db_session) -> None:
    user_service = UserService(db_session)
    repo = RefreshTokenRepository(db_session)
    auth_service = AuthService(user_service, repo)
    user = await user_service.create(
        UserCreate(name="Expired", email="expired@example.com", password="password123")
    )
    raw_token = "expired-refresh-token"
    await repo.create(
        RefreshToken(
            user_id=user.id,
            session_id=None,
            token_hash=hash_refresh_token(raw_token),
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
    )

    with pytest.raises(InvalidRefreshTokenError):
        await auth_service.refresh(raw_token)


async def test_auth_service_refresh_rejects_deleted_user(db_session) -> None:
    user_service = UserService(db_session)
    repo = RefreshTokenRepository(db_session)
    auth_service = AuthService(user_service, repo)
    user = await user_service.create(
        UserCreate(name="Ghost", email="ghost@example.com", password="password123")
    )
    raw_token = "ghost-refresh-token"
    await repo.create(
        RefreshToken(
            user_id=user.id,
            session_id=None,
            token_hash=hash_refresh_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    await user_service.delete(str(user.id))

    with pytest.raises(InvalidRefreshTokenError):
        await auth_service.refresh(raw_token)


async def test_auth_service_refresh_creates_session_for_legacy_token(db_session) -> None:
    user_service = UserService(db_session)
    repo = RefreshTokenRepository(db_session)
    auth_service = AuthService(user_service, repo)
    user = await user_service.create(
        UserCreate(name="Legacy", email="legacy@example.com", password="password123")
    )
    raw_token = "legacy-refresh-token"
    legacy_token = RefreshToken(
        user_id=user.id,
        session_id=None,
        token_hash=hash_refresh_token(raw_token),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    await repo.create(legacy_token)

    access_token, new_refresh_token = await auth_service.refresh(raw_token)

    assert access_token
    assert new_refresh_token
    sessions = (await db_session.execute(select(Session))).scalars().all()
    assert len(sessions) == 1
    assert legacy_token.session_id is not None
    assert legacy_token.revoked_at is not None
    assert sessions[0].id == legacy_token.session_id


async def test_auth_service_logout_noops_for_empty_or_missing_token(db_session) -> None:
    user_service = UserService(db_session)
    repo = RefreshTokenRepository(db_session)
    auth_service = AuthService(user_service, repo)

    before = await db_session.execute(select(RefreshToken))
    assert before.scalars().all() == []

    await auth_service.logout("")
    await auth_service.logout("does-not-exist")

    after = await db_session.execute(select(RefreshToken))
    assert after.scalars().all() == []


async def test_auth_service_get_user_from_access_returns_user_and_none(db_session) -> None:
    user_service = UserService(db_session)
    auth_service = AuthService(user_service, RefreshTokenRepository(db_session))
    user = await user_service.create(
        UserCreate(name="Lookup", email="lookup@example.com", password="password123")
    )

    assert await auth_service.get_user_from_access(user.id) == user
    assert await auth_service.get_user_from_access("00000000-0000-0000-0000-000000000000") is None


async def test_auth_service_issue_tokens_requires_persisted_user_id(db_session) -> None:
    user_service = UserService(db_session)
    auth_service = AuthService(user_service, RefreshTokenRepository(db_session))
    ghost_user = SimpleNamespace(id=None, email="ghost@example.com", name="Ghost")

    with pytest.raises(RuntimeError, match="Persisted user has no id"):
        await auth_service._issue_tokens_with_session(ghost_user, Session(user_id=uuid.uuid4()))


async def test_auth_service_refresh_returns_new_tokens_for_valid_token(db_session) -> None:
    user_service = UserService(db_session)
    repo = RefreshTokenRepository(db_session)
    auth_service = AuthService(user_service, repo)
    user = await user_service.create(
        UserCreate(name="Rotate", email="rotate@example.com", password="password123")
    )
    session = await SessionRepository(db_session).create(Session(user_id=user.id))
    token = RefreshToken(
        user_id=user.id,
        session_id=session.id,
        token_hash=hash_refresh_token("rotate-token"),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    await repo.create(token)

    access_token, new_refresh = await auth_service.refresh("rotate-token")

    assert access_token
    assert new_refresh
    assert token.revoked_at is not None
    stored = await repo.get_by_hash(hash_refresh_token(new_refresh))
    assert stored is not None
    assert stored.session_id == session.id


async def test_login_response_includes_auto_generated_username_flag(
    client,
    db_session,
) -> None:
    user_service = UserService(db_session)
    user = await user_service.create(
        UserCreate(name="Generated", email="generated@example.com", password="password123")
    )
    await db_session.execute(
        update(User).where(User.id == user.id).values(username_modified_by_system=True)
    )
    await db_session.commit()

    response = await client.post(
        "/api/v2/auth/login",
        json={"email": "generated@example.com", "password": "password123"},
    )

    assert response.status_code == 200
    login_response = LoginResponse.model_validate(response.json())
    assert login_response.username_was_auto_generated is True


async def test_register_response_includes_auto_generated_username_flag(
    client,
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_create = UserService.create

    async def create_auto_generated_username(self, data):
        user_response = await original_create(self, data)
        user_response.username_modified_by_system = True
        await db_session.execute(
            update(User).where(User.id == user_response.id).values(username_modified_by_system=True)
        )
        return user_response

    monkeypatch.setattr(UserService, "create", create_auto_generated_username)

    response = await client.post(
        "/api/v2/auth/register",
        json={
            "name": "Generated-Register",
            "email": "generated-register@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 201
    assert response.json()["username_was_auto_generated"] is True
