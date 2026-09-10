from datetime import UTC, datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from gameapi.core.database import MongoDocument
from gameapi.models.gameplay import GameplayDocument
from gameapi.schemas.gameplay import GameplayCreate, GameplayUpdate
from gameapi.services.exceptions import GameplayNotFoundError


class GameplayService:
    def __init__(self, collection: AsyncIOMotorCollection[MongoDocument]) -> None:
        self._collection = collection

    async def list_all(self) -> list[GameplayDocument]:
        cursor = self._collection.find({}).sort("created_date", -1)
        return [GameplayDocument.from_mongo(doc) async for doc in cursor]

    async def get_by_id(self, gameplay_id: str) -> GameplayDocument | None:
        if not ObjectId.is_valid(gameplay_id):
            return None
        doc = await self._collection.find_one({"_id": ObjectId(gameplay_id)})
        return GameplayDocument.from_mongo(doc) if doc else None

    async def list_by_player(self, player_id: str) -> list[GameplayDocument]:
        query = {"$or": [{"host_player": player_id}, {"guest_player": player_id}]}
        cursor = self._collection.find(query).sort("created_date", -1)
        return [GameplayDocument.from_mongo(doc) async for doc in cursor]

    async def create(self, data: GameplayCreate) -> GameplayDocument:
        now = datetime.now(UTC)
        gameplay = GameplayDocument(
            current_positions=data.current_positions,
            host_player=data.host_player,
            guest_player=data.guest_player,
            player_turn=data.player_turn,
            match_result=data.match_result,
            created_date=now,
            updated_date=now,
        )
        result = await self._collection.insert_one(gameplay.to_mongo())
        gameplay.id = result.inserted_id
        return gameplay

    async def update(self, gameplay_id: str, data: GameplayUpdate) -> GameplayDocument:
        gameplay = await self.get_by_id(gameplay_id)
        if gameplay is None:
            raise GameplayNotFoundError(gameplay_id)

        updates: dict[str, object] = {
            field: getattr(data, field) for field in data.model_fields_set
        }
        updates["updated_date"] = datetime.now(UTC)

        await self._collection.update_one({"_id": gameplay.id}, {"$set": updates})

        return gameplay.model_copy(update=updates)

    async def delete(self, gameplay_id: str) -> None:
        if not ObjectId.is_valid(gameplay_id):
            raise GameplayNotFoundError(gameplay_id)
        result = await self._collection.delete_one({"_id": ObjectId(gameplay_id)})
        if result.deleted_count == 0:
            raise GameplayNotFoundError(gameplay_id)
