from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

from gameapi.api.deps import get_session
from gameapi.main import app


@pytest.fixture(scope="session")
def postgres_container() -> PostgresContainer:
    with PostgresContainer("postgres:16-alpine") as container:
        yield container


@pytest.fixture(scope="session")
def postgres_uri(postgres_container: PostgresContainer) -> str:
    sync_uri = postgres_container.get_connection_url()
    return sync_uri.replace("postgresql+psycopg2://", "postgresql+asyncpg://")


@pytest.fixture(scope="session")
async def _run_migrations(postgres_uri: str) -> None:
    import os
    import subprocess

    env = os.environ.copy()
    env["POSTGRES_URI"] = postgres_uri
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], check=True, env=env)


@pytest.fixture
async def db_engine(postgres_uri: str, _run_migrations: None) -> AsyncIterator:
    engine = create_async_engine(postgres_uri, echo=False)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def db_session(db_engine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


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
def _override_dependencies(db_session: AsyncSession) -> AsyncIterator[None]:
    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _session
    yield
    app.dependency_overrides.clear()


@pytest.fixture
async def client(_override_dependencies: None) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def registered_user(client: AsyncClient) -> dict[str, object]:
    payload = {
        "name": "Test User",
        "email": "test@example.com",
        "password": "password123",
    }
    response = await client.post("/api/users", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def auth_token(client: AsyncClient, registered_user: dict[str, object]) -> str:
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
