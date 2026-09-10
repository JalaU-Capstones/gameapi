from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from gameapi.api.deps import get_db, get_gameplay_service, get_user_service
from gameapi.core.database import get_gameplays_collection, get_users_collection
from gameapi.main import app
from gameapi.services import GameplayService, UserService


@pytest.fixture
def mock_db() -> Any:
    return AsyncMongoMockClient()["GameDB"]


@pytest.fixture
async def mock_users_collection(mock_db: Any) -> Any:
    collection = mock_db["Users"]
    await collection.create_index("email", unique=True)
    return collection


@pytest.fixture
def mock_gameplays_collection(mock_db: Any) -> Any:
    return mock_db["Gameplays"]


@pytest.fixture(autouse=True)
def _override_dependencies(
    mock_db: Any,
    mock_users_collection: Any,
    mock_gameplays_collection: Any,
) -> AsyncIterator[None]:
    def _db() -> Any:
        return mock_db

    def _users_collection() -> Any:
        return mock_users_collection

    def _gameplays_collection() -> Any:
        return mock_gameplays_collection

    def _user_service() -> UserService:
        return UserService(mock_users_collection)

    def _gameplay_service() -> GameplayService:
        return GameplayService(mock_gameplays_collection)

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_users_collection] = _users_collection
    app.dependency_overrides[get_gameplays_collection] = _gameplays_collection
    app.dependency_overrides[get_user_service] = _user_service
    app.dependency_overrides[get_gameplay_service] = _gameplay_service

    yield

    app.dependency_overrides.clear()


@pytest.fixture
async def client(_override_dependencies: None) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def user_service(
    mock_users_collection: Any,
    _override_dependencies: None,
) -> UserService:
    return UserService(mock_users_collection)


@pytest.fixture
async def gameplay_service(
    mock_gameplays_collection: Any,
    _override_dependencies: None,
) -> GameplayService:
    return GameplayService(mock_gameplays_collection)


@pytest.fixture
async def registered_user(client: AsyncClient) -> dict[str, Any]:
    payload = {
        "name": "Test User",
        "email": "test@example.com",
        "password": "password123",
    }
    response = await client.post("/api/users", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def auth_token(client: AsyncClient, registered_user: dict[str, Any]) -> str:
    response = await client.post(
        "/api/users/login",
        json={
            "email": registered_user["email"],
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["token"])


@pytest.fixture
def auth_headers(auth_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_token}"}
