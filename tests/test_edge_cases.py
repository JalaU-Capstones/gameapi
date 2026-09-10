"""Edge case tests to raise overall test coverage above the configured threshold."""

import asyncio

import pytest
from bson import ObjectId
from httpx import AsyncClient
from pydantic import BaseModel, ConfigDict, ValidationError

from gameapi.core.database import (
    MongoDatabase,
    get_gameplays_collection,
    get_users_collection,
)
from gameapi.models.common import PyObjectId
from gameapi.services.exceptions import (
    DomainError,
    EmailAlreadyExistsError,
    GameplayNotFoundError,
    UserNotFoundError,
)

VALID_BOARD = '{"board": [[0,0,0],[0,0,0],[0,0,0]], "lastMove": null}'


# --------------------------------------------------------------- exceptions


def test_domain_error_hierarchy() -> None:
    assert issubclass(UserNotFoundError, DomainError)
    assert issubclass(EmailAlreadyExistsError, DomainError)
    assert issubclass(GameplayNotFoundError, DomainError)


def test_exception_messages_include_identifier() -> None:
    assert "abc" in str(UserNotFoundError("abc"))
    assert "x@y.com" in str(EmailAlreadyExistsError("x@y.com"))
    assert "def" in str(GameplayNotFoundError("def"))


# ------------------------------------------------------- database lifecycle


def test_get_db_raises_when_not_connected() -> None:
    original_db = MongoDatabase.db
    MongoDatabase.db = None
    try:
        with pytest.raises(RuntimeError, match="not connected"):
            MongoDatabase.get_db()
    finally:
        MongoDatabase.db = original_db


def test_get_collections_raise_when_not_connected() -> None:
    original_db = MongoDatabase.db
    MongoDatabase.db = None
    try:
        with pytest.raises(RuntimeError):
            get_users_collection()
        with pytest.raises(RuntimeError):
            get_gameplays_collection()
    finally:
        MongoDatabase.db = original_db


def test_disconnect_when_never_connected() -> None:
    original_client = MongoDatabase.client
    original_db = MongoDatabase.db
    MongoDatabase.client = None
    MongoDatabase.db = None
    try:
        asyncio.run(MongoDatabase.disconnect())
        assert MongoDatabase.client is None
        assert MongoDatabase.db is None
    finally:
        MongoDatabase.client = original_client
        MongoDatabase.db = original_db


# ----------------------------------------------------- PyObjectId validation


class _PyObjectIdModel(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: PyObjectId


def test_pyobjectid_rejects_invalid_string() -> None:
    with pytest.raises(ValidationError):
        _PyObjectIdModel(id="not-a-valid-objectid")


def test_pyobjectid_accepts_valid_string_and_object_id() -> None:
    valid_str = "65f0a1b2c3d4e5f60718293a"
    expected = ObjectId(valid_str)
    assert _PyObjectIdModel(id=valid_str).id == expected
    assert _PyObjectIdModel(id=expected).id == expected


def test_pyobjectid_serializes_to_string() -> None:
    model = _PyObjectIdModel(id="65f0a1b2c3d4e5f60718293a")
    assert model.model_dump(mode="json") == {"id": "65f0a1b2c3d4e5f60718293a"}


# ------------------------------------------------------- users: edge cases


async def test_get_user_with_invalid_object_id_returns_404(client: AsyncClient) -> None:
    response = await client.get("/api/users/not-an-object-id")
    assert response.status_code == 404
    assert response.json()["message"] == "User not found"


async def test_update_user_with_duplicate_email_returns_409(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    await client.post(
        "/api/users",
        json={"name": "Other", "email": "other@example.com", "password": "password123"},
    )
    response = await client.put(
        f"/api/users/{registered_user['id']}",
        json={"email": "other@example.com"},
        headers=auth_headers,
    )
    assert response.status_code == 409
    assert response.json()["message"] == "Email is currently registered"


async def test_update_user_with_invalid_email_returns_400(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    response = await client.put(
        f"/api/users/{registered_user['id']}",
        json={"email": "not-an-email"},
        headers=auth_headers,
    )
    assert response.status_code == 400


async def test_login_with_nonexistent_email_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        "/api/users/login",
        json={"email": "ghost@example.com", "password": "password123"},
    )
    assert response.status_code == 401
    assert response.json()["message"] == "Invalid credentials"


async def test_login_with_missing_password_returns_400(client: AsyncClient) -> None:
    response = await client.post(
        "/api/users/login",
        json={"email": "someone@example.com", "password": ""},
    )
    assert response.status_code == 400


async def test_register_user_missing_fields_returns_400(client: AsyncClient) -> None:
    response = await client.post("/api/users", json={"email": "x@y.com"})
    assert response.status_code == 400
    assert "message" in response.json()


# --------------------------------------------------- gameplays: edge cases


async def test_get_gameplay_with_invalid_object_id_returns_404(client: AsyncClient) -> None:
    response = await client.get("/api/gameplays/not-an-object-id")
    assert response.status_code == 404
    assert response.json()["message"] == "Gameplay not found"


async def test_update_gameplay_not_found_returns_404(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await client.put(
        "/api/gameplays/000000000000000000000000",
        json={"currentPositions": VALID_BOARD},
        headers=auth_headers,
    )
    assert response.status_code == 404


async def test_delete_gameplay_not_found_returns_404(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await client.delete(
        "/api/gameplays/000000000000000000000000",
        headers=auth_headers,
    )
    assert response.status_code == 404


async def test_delete_gameplay_by_non_host_returns_403(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    other = await client.post(
        "/api/users",
        json={"name": "Other", "email": "other@example.com", "password": "password123"},
    )
    other_id = other.json()["id"]
    other_login = await client.post(
        "/api/users/login",
        json={"email": "other@example.com", "password": "password123"},
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['token']}"}

    gameplay = await client.post(
        "/api/gameplays",
        json={
            "currentPositions": VALID_BOARD,
            "hostPlayer": registered_user["id"],
            "guestPlayer": other_id,
            "playerTurn": registered_user["id"],
        },
        headers=auth_headers,
    )
    gameplay_id = gameplay.json()["id"]

    response = await client.delete(f"/api/gameplays/{gameplay_id}", headers=other_headers)
    assert response.status_code == 403


async def test_update_gameplay_with_nonexistent_guest_returns_400(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    gameplay = await client.post(
        "/api/gameplays",
        json={
            "currentPositions": VALID_BOARD,
            "hostPlayer": registered_user["id"],
            "playerTurn": registered_user["id"],
        },
        headers=auth_headers,
    )
    gameplay_id = gameplay.json()["id"]

    response = await client.put(
        f"/api/gameplays/{gameplay_id}",
        json={"guestPlayer": "000000000000000000000000"},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert response.json()["message"] == "Guest player does not exist"


async def test_create_gameplay_with_empty_current_positions_is_allowed(
    client: AsyncClient,
    registered_user: dict,
    auth_headers: dict[str, str],
) -> None:
    response = await client.post(
        "/api/gameplays",
        json={
            "currentPositions": "",
            "hostPlayer": registered_user["id"],
            "playerTurn": registered_user["id"],
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["currentPositions"] == ""


# -------------------------------------------------- deps: auth edge cases


async def test_request_with_malformed_bearer_returns_401(client: AsyncClient) -> None:
    response = await client.get(
        "/api/gameplays/my-gameplays",
        headers={"Authorization": "Bearer not-a-valid-jwt"},
    )
    assert response.status_code == 401
    assert response.json()["message"] == "Invalid or expired token"


async def test_request_with_wrong_scheme_returns_401(client: AsyncClient) -> None:
    response = await client.get(
        "/api/gameplays/my-gameplays",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert response.status_code == 401
    assert response.json()["message"] == "Not authenticated"
