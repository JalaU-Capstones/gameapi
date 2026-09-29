from httpx import AsyncClient

from gameapi.core.config import settings


async def test_logout_clears_cookies(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/users",
        json={"name": "Test User", "email": "test@example.com", "password": "password123"},
    )
    login = await client.post(
        "/api/v2/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert login.status_code == 200, login.text

    logout = await client.post("/api/v2/auth/logout")
    assert logout.status_code == 204, logout.text
    set_cookie = logout.headers.get("set-cookie", "")
    assert "gameapi_at=" in set_cookie
    assert "gameapi_rt=" in set_cookie
    assert "Max-Age=0" in set_cookie


async def test_logout_revokes_refresh_token(client: AsyncClient) -> None:
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


async def test_logout_is_idempotent(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/users",
        json={"name": "Test User", "email": "test@example.com", "password": "password123"},
    )
    await client.post(
        "/api/v2/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )

    first = await client.post("/api/v2/auth/logout")
    second = await client.post("/api/v2/auth/logout")
    assert first.status_code == 204, first.text
    assert second.status_code == 204, second.text
