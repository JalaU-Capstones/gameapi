import uuid

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import select, update

from gameapi.api.v1.users import _require_self
from gameapi.api.v2.users import delete_user, get_user, update_user
from gameapi.db.models.user import User
from gameapi.schemas.user import UserResponse, UserUpdate
from gameapi.services.exceptions import (
    EmailAlreadyExistsError,
    UsernameAlreadyExistsError,
    UserNotFoundError,
)


def test_require_self_rejects_user_without_persisted_id() -> None:
    current_user = UserResponse.model_construct(id=None)

    with pytest.raises(RuntimeError, match="Authenticated user has no _id"):
        _require_self(current_user, "user-id")


async def test_register_user_returns_created(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/users",
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
        "/api/v1/users",
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
        "/api/v1/users",
        json={"name": "Valid", "email": "not-an-email", "password": "password123"},
    )
    assert response.status_code == 400
    assert "message" in response.json()


async def test_register_user_with_short_password_returns_400(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/users",
        json={"name": "Valid", "email": "x@example.com", "password": "123"},
    )
    assert response.status_code == 400
    assert "message" in response.json()


async def test_register_duplicate_email_returns_409(client: AsyncClient) -> None:
    payload = {
        "name": "Alice",
        "email": "alice@example.com",
        "password": "password123",
    }
    first = await client.post("/api/v1/users", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/v1/users", json=payload)
    assert second.status_code == 409
    assert second.json()["message"] == "Email is currently registered"


async def test_v1_create_duplicate_username_returns_409(
    client: AsyncClient,
    registered_user: dict[str, object],
) -> None:
    response = await client.post(
        "/api/v1/users",
        json={
            "name": registered_user["name"],
            "email": "duplicate-name-v1@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 409
    assert response.json()["message"] == "Username is already taken"


async def test_v2_register_duplicate_username_returns_409(
    client: AsyncClient,
    registered_user: dict[str, object],
) -> None:
    response = await client.post(
        "/api/v2/auth/register",
        json={
            "username": registered_user["username"],
            "email": "duplicate-name-v2@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 409
    assert response.json()["message"] == "Username is already taken"


async def test_list_users_v1_returns_410(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    await client.post(
        "/api/v1/users",
        json={"name": "Alice", "email": "alice@example.com", "password": "password123"},
    )
    response = await client.get("/api/v1/users", headers=auth_headers)
    assert response.status_code == 410
    assert response.json() == {"detail": "This endpoint has been removed for privacy reasons."}


async def test_list_users_v2_returns_410(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await client.get("/api/v2/users", headers=auth_headers)
    assert response.status_code == 410
    assert response.json() == {"detail": "This endpoint has been removed for privacy reasons."}


async def test_get_user_returns_only_id_and_name(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    created = await client.post(
        "/api/v1/users",
        json={"name": "Alice", "email": "alice@example.com", "password": "password123"},
    )
    user_id = created.json()["id"]

    response = await client.get(f"/api/v1/users/{user_id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"id": user_id, "name": "Alice"}


async def test_get_user_by_id_not_found(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await client.get(
        "/api/v1/users/00000000-0000-0000-0000-000000000000",
        headers=auth_headers,
    )
    assert response.status_code == 404
    assert response.json()["message"] == "User not found"


async def test_update_user_without_token_returns_401(client: AsyncClient) -> None:
    created = await client.post(
        "/api/v1/users",
        json={"name": "Alice", "email": "alice@example.com", "password": "password123"},
    )
    user_id = created.json()["id"]

    response = await client.put(
        f"/api/v1/users/{user_id}",
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
        f"/api/v1/users/{user_id}",
        json={"name": "Updated-Name"},
        headers=auth_headers,
    )
    assert response.status_code == 204

    fetched = await client.get(f"/api/v1/users/{user_id}", headers=auth_headers)
    assert fetched.json()["name"] == "Updated-Name"


async def test_v1_create_rejects_invalid_username(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/users",
        json={
            "name": "sandra dee",
            "email": "invalid-v1-username@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == 422, response.text


async def test_v2_update_rejects_invalid_username(
    client: AsyncClient,
    registered_user: dict[str, object],
    auth_headers: dict[str, str],
) -> None:
    response = await client.put(
        f"/api/v2/users/{registered_user['id']}",
        json={"username": "sandra dee"},
        headers=auth_headers,
    )

    assert response.status_code == 422, response.text


async def test_v1_update_duplicate_username_returns_409(
    client: AsyncClient,
    registered_user: dict[str, object],
    auth_headers: dict[str, str],
) -> None:
    await client.post(
        "/api/v1/users",
        json={"name": "TakenName", "email": "taken-v1@example.com", "password": "password123"},
    )

    response = await client.put(
        f"/api/v1/users/{registered_user['id']}",
        json={"name": "TakenName"},
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert response.json()["message"] == "Username is already taken"


async def test_user_update_resets_username_system_flag(
    client: AsyncClient,
    registered_user: dict[str, object],
    auth_headers: dict[str, str],
    db_session,
) -> None:
    await db_session.execute(
        update(User)
        .where(User.id == uuid.UUID(str(registered_user["id"])))
        .values(username_modified_by_system=True)
    )
    await db_session.commit()

    response = await client.put(
        f"/api/v2/users/{registered_user['id']}",
        json={"username": "UpdatedUsername"},
        headers=auth_headers,
    )
    assert response.status_code == 204

    db_session.expire_all()
    user = await db_session.scalar(
        select(User).where(User.id == uuid.UUID(str(registered_user["id"])))
    )
    assert user is not None
    assert user.username == "UpdatedUsername"
    assert user.username_modified_by_system is False


async def test_v2_update_duplicate_username_returns_409(
    client: AsyncClient,
    registered_user: dict[str, object],
    auth_headers: dict[str, str],
) -> None:
    await client.post(
        "/api/v1/users",
        json={"name": "TakenName", "email": "taken-v2@example.com", "password": "password123"},
    )

    response = await client.put(
        f"/api/v2/users/{registered_user['id']}",
        json={"username": "TakenName"},
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert response.json()["message"] == "Username is already taken"


async def test_update_user_with_email_only_updates_email(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    user_id = registered_user["id"]
    response = await client.put(
        f"/api/v1/users/{user_id}",
        json={"email": "new@example.com"},
        headers=auth_headers,
    )
    assert response.status_code == 204, response.text

    login = await client.post(
        "/api/v1/users/login",
        json={"email": "new@example.com", "password": "password123"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["user"]["email"] == "new@example.com"


async def test_update_user_with_password(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    user_id = registered_user["id"]
    response = await client.put(
        f"/api/v1/users/{user_id}",
        json={"password": "newPassword123"},
        headers=auth_headers,
    )
    assert response.status_code == 204, response.text

    login = await client.post(
        "/api/v1/users/login",
        json={"email": registered_user["email"], "password": "newPassword123"},
    )
    assert login.status_code == 200


async def test_update_user_with_empty_body_is_noop(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    user_id = registered_user["id"]
    response = await client.put(f"/api/v1/users/{user_id}", json={}, headers=auth_headers)
    assert response.status_code == 204, response.text

    fetched = await client.get(f"/api/v1/users/{user_id}", headers=auth_headers)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["name"] == registered_user["name"]


async def test_update_user_with_invalid_uuid_returns_404(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await client.put(
        "/api/v1/users/not-a-uuid",
        json={"name": "Updated"},
        headers=auth_headers,
    )
    assert response.status_code in {403, 404}


async def test_delete_user_with_invalid_uuid_returns_404(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await client.delete("/api/v1/users/not-a-uuid", headers=auth_headers)
    assert response.status_code in {403, 404}


async def test_update_another_user_returns_403(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    other = await client.post(
        "/api/v1/users",
        json={"name": "Other", "email": "other@example.com", "password": "password123"},
    )
    other_id = other.json()["id"]

    response = await client.put(
        f"/api/v1/users/{other_id}",
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
    response = await client.delete(f"/api/v1/users/{user_id}", headers=auth_headers)
    assert response.status_code == 204

    fetched = await client.get(f"/api/v1/users/{user_id}", headers=auth_headers)
    assert fetched.status_code == 401


async def test_delete_user_without_token_returns_401(
    client: AsyncClient,
    registered_user: dict,
) -> None:
    response = await client.delete(f"/api/v1/users/{registered_user['id']}")
    assert response.status_code == 401


async def test_v2_user_routes_cover_ownership_and_service_errors() -> None:
    current_user = UserResponse.model_validate(
        {
            "id": "11111111-1111-4111-8111-111111111111",
            "name": "Current User",
            "email": "current@example.com",
            "register_date": "2024-01-01T00:00:00Z",
        }
    )

    class Service:
        async def get_by_id(self, user_id: str):
            if user_id == str(current_user.id):
                return current_user
            return None

        async def update(self, user_id: str, payload: UserUpdate):
            raise UserNotFoundError(user_id)

        async def delete(self, user_id: str):
            raise UserNotFoundError(user_id)

    with pytest.raises(HTTPException) as exc:
        await get_user("00000000-0000-0000-0000-000000000000", Service())
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        await update_user(
            "22222222-2222-4222-8222-222222222222",
            UserUpdate(name="Nope"),
            current_user,
            Service(),
        )
    assert exc.value.status_code == 403

    class DuplicateEmailService:
        async def update(self, user_id: str, payload: UserUpdate):
            raise EmailAlreadyExistsError(payload.email or current_user.email)

    with pytest.raises(HTTPException) as exc:
        await update_user(
            str(current_user.id),
            UserUpdate(email="taken@example.com"),
            current_user,
            DuplicateEmailService(),
        )
    assert exc.value.status_code == 409

    class DuplicateUsernameService:
        async def update(self, user_id: str, payload: UserUpdate):
            raise UsernameAlreadyExistsError()

    with pytest.raises(HTTPException) as exc:
        await update_user(
            str(current_user.id),
            UserUpdate(username="taken"),
            current_user,
            DuplicateUsernameService(),
        )
    assert exc.value.status_code == 409

    with pytest.raises(HTTPException) as exc:
        await delete_user(
            "22222222-2222-4222-8222-222222222222",
            current_user,
            Service(),
        )
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        await update_user(
            str(current_user.id),
            UserUpdate(name="Changed"),
            current_user,
            Service(),
        )
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        await delete_user(str(current_user.id), current_user, Service())
    assert exc.value.status_code == 404


async def test_login_with_valid_credentials(client: AsyncClient, registered_user: dict) -> None:
    response = await client.post(
        "/api/v1/users/login",
        json={"email": registered_user["email"], "password": "password123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "token" in body
    assert body["user"]["email"] == registered_user["email"]


async def test_login_with_invalid_credentials(client: AsyncClient, registered_user: dict) -> None:
    response = await client.post(
        "/api/v1/users/login",
        json={"email": registered_user["email"], "password": "wrong"},
    )
    assert response.status_code == 401
    assert response.json()["message"] == "Invalid credentials"
