from httpx import AsyncClient


async def test_register_user_returns_created(client: AsyncClient) -> None:
    response = await client.post(
        "/api/users",
        json={
            "name": "Alice",
            "email": "alice@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Alice"
    assert body["email"] == "alice@example.com"
    assert "id" in body
    assert "registerDate" in body
    assert "password" not in body


async def test_register_user_normalizes_email_to_lowercase(client: AsyncClient) -> None:
    response = await client.post(
        "/api/users",
        json={
            "name": "Bob",
            "email": "BOB@Example.COM",
            "password": "password123",
        },
    )
    assert response.status_code == 201
    assert response.json()["email"] == "bob@example.com"


async def test_register_user_with_invalid_email_returns_400(client: AsyncClient) -> None:
    response = await client.post(
        "/api/users",
        json={"name": "X", "email": "not-an-email", "password": "password123"},
    )
    assert response.status_code == 400
    assert "message" in response.json()


async def test_register_user_with_short_password_returns_400(client: AsyncClient) -> None:
    response = await client.post(
        "/api/users",
        json={"name": "X", "email": "x@example.com", "password": "123"},
    )
    assert response.status_code == 400
    assert "message" in response.json()


async def test_register_duplicate_email_returns_409(client: AsyncClient) -> None:
    payload = {
        "name": "Alice",
        "email": "alice@example.com",
        "password": "password123",
    }
    first = await client.post("/api/users", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/users", json=payload)
    assert second.status_code == 409
    assert second.json()["message"] == "Email is currently registered"


async def test_list_users_returns_registered_users(client: AsyncClient) -> None:
    await client.post(
        "/api/users",
        json={"name": "Alice", "email": "alice@example.com", "password": "password123"},
    )
    response = await client.get("/api/users")
    assert response.status_code == 200
    users = response.json()
    assert len(users) == 1
    assert users[0]["email"] == "alice@example.com"


async def test_get_user_by_id(client: AsyncClient) -> None:
    created = await client.post(
        "/api/users",
        json={"name": "Alice", "email": "alice@example.com", "password": "password123"},
    )
    user_id = created.json()["id"]

    response = await client.get(f"/api/users/{user_id}")
    assert response.status_code == 200
    assert response.json()["id"] == user_id


async def test_get_user_by_id_not_found(client: AsyncClient) -> None:
    response = await client.get("/api/users/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["message"] == "User not found"


async def test_update_user_without_token_returns_401(client: AsyncClient) -> None:
    created = await client.post(
        "/api/users",
        json={"name": "Alice", "email": "alice@example.com", "password": "password123"},
    )
    user_id = created.json()["id"]

    response = await client.put(
        f"/api/users/{user_id}",
        json={"name": "Updated"},
    )
    assert response.status_code == 401


async def test_update_user_with_token(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    user_id = registered_user["id"]
    response = await client.put(
        f"/api/users/{user_id}",
        json={"name": "Updated Name"},
        headers=auth_headers,
    )
    assert response.status_code == 204

    fetched = await client.get(f"/api/users/{user_id}")
    assert fetched.json()["name"] == "Updated Name"


async def test_update_another_user_returns_403(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    other = await client.post(
        "/api/users",
        json={"name": "Other", "email": "other@example.com", "password": "password123"},
    )
    other_id = other.json()["id"]

    response = await client.put(
        f"/api/users/{other_id}",
        json={"name": "Hacked"},
        headers=auth_headers,
    )
    assert response.status_code == 403


async def test_delete_user_with_token(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    user_id = registered_user["id"]
    response = await client.delete(f"/api/users/{user_id}", headers=auth_headers)
    assert response.status_code == 204

    fetched = await client.get(f"/api/users/{user_id}")
    assert fetched.status_code == 404


async def test_delete_user_without_token_returns_401(
    client: AsyncClient,
    registered_user: dict,
) -> None:
    response = await client.delete(f"/api/users/{registered_user['id']}")
    assert response.status_code == 401


async def test_login_with_valid_credentials(client: AsyncClient, registered_user: dict) -> None:
    response = await client.post(
        "/api/users/login",
        json={"email": registered_user["email"], "password": "password123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "token" in body
    assert body["user"]["email"] == registered_user["email"]


async def test_login_with_invalid_credentials(client: AsyncClient, registered_user: dict) -> None:
    response = await client.post(
        "/api/users/login",
        json={"email": registered_user["email"], "password": "wrong"},
    )
    assert response.status_code == 401
    assert response.json()["message"] == "Invalid credentials"
