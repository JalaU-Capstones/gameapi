from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase

from gameapi.core.config import settings

MongoDocument = dict[str, Any]


class MongoDatabase:
    client: AsyncIOMotorClient[MongoDocument] | None = None
    db: AsyncIOMotorDatabase[MongoDocument] | None = None

    @classmethod
    async def connect(cls) -> None:
        cls.client = AsyncIOMotorClient[MongoDocument](
            settings.mongo.connection_string,
            uuidRepresentation="standard",
            tz_aware=True,
        )
        cls.db = cls.client[settings.mongo.database_name]
        await cls.client.admin.command("ping")

    @classmethod
    async def disconnect(cls) -> None:
        if cls.client is not None:
            cls.client.close()
        cls.client = None
        cls.db = None

    @classmethod
    def get_db(cls) -> AsyncIOMotorDatabase[MongoDocument]:
        if cls.db is None:
            raise RuntimeError("MongoDB is not connected. Call connect() first.")
        return cls.db


@asynccontextmanager
async def lifespan_mongo() -> AsyncIterator[None]:
    await MongoDatabase.connect()
    try:
        yield
    finally:
        await MongoDatabase.disconnect()


def get_users_collection() -> AsyncIOMotorCollection[MongoDocument]:
    return MongoDatabase.get_db()["Users"]


def get_gameplays_collection() -> AsyncIOMotorCollection[MongoDocument]:
    return MongoDatabase.get_db()["Gameplays"]
