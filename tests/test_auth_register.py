from httpx import AsyncClient


async def test_register_creates_user_and_returns_201(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v2/auth/register",
        json={"name": "Alice", "email": "alice@example.com", "password": "password123"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["email"] == "alice@example.com"
    assert body["user"]["name"] == "Alice"
    assert body["access_token"]
    assert body["token_type"] == "bearer"


async def test_register_sets_httponly_cookies(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v2/auth/register",
        json={"name": "Cookie User", "email": "cookie@example.com", "password": "password123"},
    )
    assert response.status_code == 201, response.text
    assert "gameapi_at" in response.cookies
    assert "gameapi_rt" in response.cookies
    set_cookie = response.headers.get("set-cookie", "")
    assert "gameapi_at=" in set_cookie
    assert "gameapi_rt=" in set_cookie
    assert "HttpOnly" in set_cookie


async def test_register_response_shape_matches_login(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v2/auth/register",
        json={"name": "Login Shape", "email": "shape@example.com", "password": "password123"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body.keys()) == {"access_token", "token_type", "user"}
    assert body["token_type"] == "bearer"


async def test_register_returns_same_user_as_me(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v2/auth/register",
        json={"name": "Me User", "email": "me@example.com", "password": "password123"},
    )
    assert response.status_code == 201, response.text

    me_response = await client.get("/api/v2/auth/me")
    assert me_response.status_code == 200, me_response.text
    assert me_response.json()["email"] == "me@example.com"
    assert me_response.json()["name"] == "Me User"


async def test_register_duplicate_email_returns_409(client: AsyncClient) -> None:
    payload = {"name": "Dup", "email": "dup@example.com", "password": "password123"}
    first = await client.post("/api/v2/auth/register", json=payload)
    assert first.status_code == 201, first.text

    second = await client.post("/api/v2/auth/register", json=payload)
    assert second.status_code == 409, second.text
    assert second.json()["message"] == "Email is currently registered"


async def test_register_invalid_email_returns_400(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v2/auth/register",
        json={"name": "Bad", "email": "not-an-email", "password": "password123"},
    )
    assert response.status_code == 400, response.text


async def test_register_short_password_returns_400(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v2/auth/register",
        json={"name": "Short", "email": "short@example.com", "password": "123"},
    )
    assert response.status_code == 400, response.text


async def test_register_does_not_expose_refresh_token_in_body(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v2/auth/register",
        json={"name": "Secure", "email": "secure@example.com", "password": "password123"},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert "access_token" in payload
    assert "token_type" in payload
    assert "user" in payload
    assert "refresh_token" not in payload


async def test_register_user_can_immediately_call_authenticated_endpoints(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v2/auth/register",
        json={"name": "Authed", "email": "authed@example.com", "password": "password123"},
    )
    assert response.status_code == 201, response.text
    user_id = response.json()["user"]["id"]

    user_response = await client.get(f"/api/v2/users/{user_id}")
    assert user_response.status_code == 200, user_response.text
    assert user_response.json()["email"] == "authed@example.com"
