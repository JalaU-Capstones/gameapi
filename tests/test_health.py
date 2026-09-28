import asyncio
import logging
from unittest.mock import AsyncMock

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from gameapi.db import PostgresDatabase
from gameapi.main import app, lifespan
from gameapi.services.event_bus import event_bus


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_lifespan_manages_logging_and_database_lifecycle(
    db_session,
    monkeypatch,
) -> None:
    connect = AsyncMock()
    disconnect = AsyncMock()
    shutdown = AsyncMock()
    monkeypatch.setattr(PostgresDatabase, "connect", connect)
    monkeypatch.setattr(PostgresDatabase, "disconnect", disconnect)
    monkeypatch.setattr(
        PostgresDatabase,
        "session_factory",
        lambda: async_sessionmaker(db_session.bind, expire_on_commit=False),
    )
    monkeypatch.setattr(event_bus, "shutdown", shutdown)

    root_logger = logging.getLogger()
    previous_level = root_logger.level
    try:
        async with lifespan(app):
            handler = app.state.log_service.get_handler()
            assert handler in root_logger.handlers
            assert handler._loop is asyncio.get_running_loop()

        assert handler not in root_logger.handlers
    finally:
        root_logger.setLevel(previous_level)

    connect.assert_awaited_once()
    disconnect.assert_awaited_once()
    shutdown.assert_awaited_once()
