from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from gameapi.core.config import settings
from gameapi.core.security import hash_refresh_token
from gameapi.db.models.refresh_token import RefreshToken
from gameapi.repositories.refresh_token_repository import RefreshTokenRepository
from gameapi.schemas.user import UserCreate
from gameapi.services.auth_service import AuthService
from gameapi.services.exceptions import InvalidCredentialsError, InvalidRefreshTokenError
from gameapi.services.user_service import UserService


async def test_refresh_returns_new_access_token(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/users",
        json={"name": "Test User", "email": "test@example.com", "password": "password123"},
    )
    login = await client.post(
        "/api/v2/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    old_access = login.json()["access_token"]

    refresh = await client.post("/api/v2/auth/refresh")
    assert refresh.status_code == 200, refresh.text
    payload = refresh.json()
    assert payload["access_token"]
    assert payload["access_token"] != old_access


async def test_refresh_rotates_refresh_token(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/users",
        json={"name": "Test User", "email": "test@example.com", "password": "password123"},
    )
    login = await client.post(
        "/api/v2/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    old_refresh = login.cookies["gameapi_rt"]

    refresh = await client.post("/api/v2/auth/refresh")
    assert refresh.status_code == 200, refresh.text
    assert refresh.cookies["gameapi_rt"] != old_refresh


async def test_refresh_without_cookie_returns_401(client: AsyncClient) -> None:
    response = await client.post("/api/v2/auth/refresh")
    assert response.status_code == 401, response.text


async def test_refresh_with_revoked_token_returns_401(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/users",
        json={"name": "Test User", "email": "test@example.com", "password": "password123"},
    )
    login = await client.post(
        "/api/v2/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    raw_refresh = login.cookies["gameapi_rt"]

    logout = await client.post("/api/v2/auth/logout")
    assert logout.status_code == 204, logout.text

    client.cookies.clear()
    client.cookies.set(
        settings.auth.refresh_cookie_name,
        raw_refresh,
        path=settings.auth.refresh_cookie_path,
    )
    response = await client.post("/api/v2/auth/refresh")
    assert response.status_code == 401, response.text


async def test_refresh_with_expired_token_returns_401(client: AsyncClient, db_session) -> None:
    await client.post(
        "/api/v1/users",
        json={"name": "Test User", "email": "test@example.com", "password": "password123"},
    )
    raw_refresh = "known-raw-refresh-token"
    created = await client.post(
        "/api/v1/users",
        json={"name": "Other User", "email": "other@example.com", "password": "password123"},
    )
    db_session.add(
        RefreshToken(
            user_id=created.json()["id"],
            token_hash=hash_refresh_token(raw_refresh),
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
    )
    await db_session.commit()

    client.cookies.clear()
    client.cookies.set(
        settings.auth.refresh_cookie_name,
        raw_refresh,
        path=settings.auth.refresh_cookie_path,
    )
    response = await client.post("/api/v2/auth/refresh")
    assert response.status_code == 401, response.text


async def test_refresh_token_repository_revoke_all_for_user_and_delete_expired(
    db_session,
    registered_user,
) -> None:
    user_id = registered_user["id"]
    repo = RefreshTokenRepository(db_session)
    now = datetime.now(UTC)

    db_session.add_all(
        [
            RefreshToken(
                user_id=user_id,
                token_hash="hash_active",
                expires_at=now + timedelta(days=1),
            ),
            RefreshToken(
                user_id=user_id,
                token_hash="hash_expired",
                expires_at=now - timedelta(days=1),
            ),
            RefreshToken(
                user_id=user_id,
                token_hash="hash_revoked",
                expires_at=now + timedelta(days=2),
                revoked_at=now,
            ),
        ]
    )
    await db_session.commit()

    assert await repo.revoke_all_for_user(user_id) == 1
    assert await repo.delete_expired() == 1

    remaining = (await db_session.execute(select(RefreshToken))).scalars().all()
    assert len(remaining) == 2
    assert {token.token_hash for token in remaining} == {"hash_active", "hash_revoked"}
    assert any(
        token.token_hash == "hash_active" and token.revoked_at is not None for token in remaining
    )


async def test_auth_service_rejects_invalid_credentials_and_refresh_tokens(db_session) -> None:
    user_service = UserService(db_session)
    auth_service = AuthService(user_service, RefreshTokenRepository(db_session))

    await user_service.create(
        UserCreate(name="Test User", email="valid@example.com", password="password123")
    )

    with pytest.raises(InvalidCredentialsError):
        await auth_service.login("valid@example.com", "wrong-password")

    with pytest.raises(InvalidRefreshTokenError):
        await auth_service.refresh("definitely-invalid-refresh-token")

    await auth_service.logout("")
