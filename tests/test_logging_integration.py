import logging

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from gameapi.db.models.log_entry import LogEntry
from gameapi.services.log_service import LogService


async def test_logging_integration_user_registered_event_is_persisted(
    client: AsyncClient,
    db_session,
) -> None:
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    service = LogService(factory, buffer_size=50, flush_interval=999)
    root_logger = logging.getLogger()
    previous_level = root_logger.level
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(service.get_handler())
    await service.start()
    try:
        response = await client.post(
            "/api/v1/users",
            json={
                "name": "Logger",
                "email": "logger@example.com",
                "password": "password123",
            },
        )
        assert response.status_code == 201
        await service.flush_now()
    finally:
        root_logger.removeHandler(service.get_handler())
        root_logger.setLevel(previous_level)
        await service.stop()

    rows = (await db_session.execute(select(LogEntry))).scalars().all()
    assert any(row.event_type == "user_registered" for row in rows)
