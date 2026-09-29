from httpx import AsyncClient


async def test_login_sets_httponly_access_cookie(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/users",
        json={"name": "Test User", "email": "test@example.com", "password": "password123"},
    )
    response = await client.post(
        "/api/v2/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert response.status_code == 200, response.text
    assert "gameapi_at" in response.cookies
    set_cookie = response.headers.get("set-cookie", "")
    assert "gameapi_at=" in set_cookie
    assert "HttpOnly" in set_cookie


async def test_login_sets_httponly_refresh_cookie(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/users",
        json={"name": "Test User", "email": "test@example.com", "password": "password123"},
    )
    response = await client.post(
        "/api/v2/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert response.status_code == 200, response.text
    assert "gameapi_rt" in response.cookies
    set_cookie = response.headers.get("set-cookie", "")
    assert "gameapi_rt=" in set_cookie
    assert "Path=/api/v2/auth" in set_cookie
    assert "HttpOnly" in set_cookie


async def test_login_returns_access_token_in_body_but_not_refresh(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/users",
        json={"name": "Test User", "email": "test@example.com", "password": "password123"},
    )
    response = await client.post(
        "/api/v2/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "access_token" in payload
    assert "user" in payload
    assert "refresh_token" not in payload


async def test_login_with_invalid_credentials_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v2/auth/login",
        json={"email": "test@example.com", "password": "wrong-pass"},
    )
    assert response.status_code == 401, response.text
    assert "gameapi_at" not in response.cookies
    assert "gameapi_rt" not in response.cookies


async def test_get_me_works_with_cookie(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/users",
        json={"name": "Test User", "email": "test@example.com", "password": "password123"},
    )
    login = await client.post(
        "/api/v2/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert login.status_code == 200, login.text

    response = await client.get("/api/v2/auth/me")
    assert response.status_code == 200, response.text
    assert response.json()["email"] == "test@example.com"


async def test_get_me_works_with_bearer_header(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/users",
        json={"name": "Test User", "email": "test@example.com", "password": "password123"},
    )
    login = await client.post(
        "/api/v2/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    response = await client.get("/api/v2/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    assert response.json()["email"] == "test@example.com"


async def test_get_me_without_any_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/api/v2/auth/me")
    assert response.status_code == 401, response.text
