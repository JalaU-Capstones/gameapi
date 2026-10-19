from httpx import AsyncClient


async def test_other_user_lookup_returns_only_public_fields(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    created = await client.post(
        "/api/v1/users",
        json={"name": "Other-User", "email": "other@example.com", "password": "password123"},
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    response = await client.get(f"/api/v2/users/{user_id}", headers=auth_headers)

    assert response.status_code == 200, response.text
    assert response.json() == {"id": user_id, "name": "Other-User"}


async def test_current_user_endpoint_still_returns_private_fields(
    client: AsyncClient,
    registered_user: dict[str, object],
    auth_headers: dict[str, str],
) -> None:
    response = await client.get("/api/v2/auth/me", headers=auth_headers)

    assert response.status_code == 200, response.text
    assert response.json()["email"] == registered_user["email"]
    assert "registerDate" in response.json()


async def test_v2_user_list_returns_gone_without_user_data(
    client: AsyncClient,
    registered_user: dict[str, object],
    auth_headers: dict[str, str],
) -> None:
    response = await client.get("/api/v2/users", headers=auth_headers)

    assert response.status_code == 410
    assert response.json() == {"detail": "This endpoint has been removed for privacy reasons."}
    assert "test@example.com" not in response.text


async def test_v2_login_still_returns_authenticated_user_email(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/users",
        json={"name": "Login-User", "email": "login@example.com", "password": "password123"},
    )

    response = await client.post(
        "/api/v2/auth/login",
        json={"email": "login@example.com", "password": "password123"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["user"]["email"] == "login@example.com"
    assert "register_date" in response.json()["user"]
