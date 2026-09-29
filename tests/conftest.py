import os
from collections.abc import AsyncIterator, Callable, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.community.postgres import PostgresContainer


def _to_asyncpg_uri(uri: str) -> str:
    """Convert a sync SQLAlchemy URI (psycopg2) to an asyncpg URI."""
    return uri.replace("postgresql+psycopg2://", "postgresql+asyncpg://").replace(
        "postgresql://", "postgresql+asyncpg://"
    )


@pytest.fixture(scope="session")
def postgres_uri() -> Iterator[str]:
    """
    Yield the PostgreSQL URI to use.

    - If TEST_POSTGRES_URI is set (CI), use it directly.
    - Otherwise, spin up a testcontainers PostgreSQL (local).
    """
    env_uri = os.environ.get("TEST_POSTGRES_URI")
    if env_uri:
        yield _to_asyncpg_uri(env_uri)
        return

    with PostgresContainer("postgres:16-alpine") as container:
        yield _to_asyncpg_uri(container.get_connection_url())


@pytest.fixture(scope="session")
async def _run_migrations(postgres_uri: str) -> None:
    import os
    import subprocess

    env = os.environ.copy()
    env["POSTGRES_URI"] = postgres_uri
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True, env=env)


@pytest.fixture
async def db_engine(postgres_uri: str, _run_migrations: None) -> AsyncIterator:
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(postgres_uri, echo=False, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def db_session(db_engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)

    from gameapi.db.session import PostgresDatabase

    PostgresDatabase.engine = db_engine
    PostgresDatabase._session_factory = factory

    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()

    PostgresDatabase.engine = None
    PostgresDatabase._session_factory = None


@pytest.fixture(autouse=True)
async def _clean_tables(db_session: AsyncSession) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await db_session.rollback()
        await db_session.execute(
            text("TRUNCATE TABLE logs, gameplays, users RESTART IDENTITY CASCADE")
        )
        await db_session.commit()


@pytest.fixture(autouse=True)
def _override_dependencies(db_session: AsyncSession) -> Iterator[None]:
    from gameapi.api.deps import get_session
    from gameapi.main import app

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session
        await db_session.commit()

    app.dependency_overrides[get_session] = _session
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def client(_override_dependencies: None) -> AsyncIterator[AsyncClient]:
    from gameapi.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def ws_client_factory(
    _override_dependencies: None,
) -> AsyncIterator[Callable[[], AsyncClient]]:
    from httpx_ws.transport import ASGIWebSocketTransport

    from gameapi.main import app

    clients: list[AsyncClient] = []

    def factory() -> AsyncClient:
        client = AsyncClient(
            transport=ASGIWebSocketTransport(app=app),
            base_url="http://test",
        )
        clients.append(client)
        return client

    yield factory

    for client in clients:
        await client.aclose()


@pytest.fixture(autouse=True)
def _clear_ws_managers() -> Iterator[None]:
    from gameapi.api.v2.ws.manager import gameplays_manager, presence_manager

    yield
    gameplays_manager._connections.clear()
    presence_manager._connections.clear()


@pytest.fixture(autouse=True)
async def _reset_event_bus() -> AsyncIterator[None]:
    from gameapi.services.event_bus import event_bus

    yield
    await event_bus.shutdown()


@pytest.fixture
async def registered_user(client: AsyncClient) -> dict[str, object]:
    payload = {
        "name": "Test User",
        "email": "test@example.com",
        "password": "password123",
    }
    response = await client.post("/api/v1/users", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def auth_token(client: AsyncClient, registered_user: dict[str, object]) -> str:
    response = await client.post(
        "/api/v1/users/login",
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


@pytest.fixture
async def authed_client(client: AsyncClient, registered_user: dict[str, object]) -> AsyncClient:
    response = await client.post(
        "/api/v2/auth/login",
        json={
            "email": registered_user["email"],
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    return client


@pytest.fixture
async def authed_client_bearer(
    client: AsyncClient,
    registered_user: dict[str, object],
) -> dict[str, str]:
    response = await client.post(
        "/api/v1/users/login",
        json={
            "email": registered_user["email"],
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
async def registered_user_a(client: AsyncClient) -> dict[str, object]:
    payload = {
        "name": "User A",
        "email": "a@example.com",
        "password": "password123",
    }
    response = await client.post("/api/v1/users", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def auth_token_a(client: AsyncClient, registered_user_a: dict[str, object]) -> str:
    response = await client.post(
        "/api/v1/users/login",
        json={
            "email": registered_user_a["email"],
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["token"])


@pytest.fixture
async def registered_user_b(client: AsyncClient) -> dict[str, object]:
    payload = {
        "name": "User B",
        "email": "b@example.com",
        "password": "password123",
    }
    response = await client.post("/api/v1/users", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def auth_token_b(client: AsyncClient, registered_user_b: dict[str, object]) -> str:
    response = await client.post(
        "/api/v1/users/login",
        json={
            "email": registered_user_b["email"],
            "password": "password123",
        },
    )
    assert response.status_code == 200, response.text
    return str(response.json()["token"])
