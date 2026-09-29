from httpx import AsyncClient


async def test_v1_login_still_returns_token_in_body(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/users",
        json={"name": "Test User", "email": "test@example.com", "password": "password123"},
    )
    response = await client.post(
        "/api/v1/users/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "token" in body
    assert "user" in body
    assert "access_token" not in body
    assert "gameapi_at" not in response.cookies


async def test_v1_endpoints_work_with_bearer_header(client: AsyncClient) -> None:
    created = await client.post(
        "/api/v1/users",
        json={"name": "Test User", "email": "test@example.com", "password": "password123"},
    )
    login = await client.post(
        "/api/v1/users/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert created.status_code == 201, created.text
    assert login.status_code == 200, login.text

    response = await client.get(
        f"/api/v1/users/{created.json()['id']}",
        headers={"Authorization": f"Bearer {login.json()['token']}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["email"] == "test@example.com"
