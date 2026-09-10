from datetime import UTC, datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo.errors import DuplicateKeyError

from gameapi.core.database import MongoDocument
from gameapi.core.security import hash_password
from gameapi.models.user import UserDocument
from gameapi.schemas.user import UserCreate, UserUpdate
from gameapi.services.exceptions import EmailAlreadyExistsError, UserNotFoundError


class UserService:
    def __init__(self, collection: AsyncIOMotorCollection[MongoDocument]) -> None:
        self._collection = collection

    async def ensure_indexes(self) -> None:
        await self._collection.create_index("email", unique=True)

    async def list_all(self) -> list[UserDocument]:
        cursor = self._collection.find({})
        return [UserDocument.from_mongo(doc) async for doc in cursor]

    async def get_by_id(self, user_id: str) -> UserDocument | None:
        if not ObjectId.is_valid(user_id):
            return None
        doc = await self._collection.find_one({"_id": ObjectId(user_id)})
        return UserDocument.from_mongo(doc) if doc else None

    async def get_by_email(self, email: str) -> UserDocument | None:
        doc = await self._collection.find_one({"email": email.lower()})
        return UserDocument.from_mongo(doc) if doc else None

    async def create(self, data: UserCreate) -> UserDocument:
        user = UserDocument(
            name=data.name,
            email=data.email.lower(),
            password=hash_password(data.password),
            register_date=datetime.now(UTC),
        )
        try:
            result = await self._collection.insert_one(user.to_mongo())
        except DuplicateKeyError as exc:
            raise EmailAlreadyExistsError(data.email) from exc
        user.id = result.inserted_id
        return user

    async def update(self, user_id: str, data: UserUpdate) -> UserDocument:
        user = await self.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError(user_id)

        updates: dict[str, object] = {}
        if data.name is not None:
            updates["name"] = data.name
        if data.email is not None:
            updates["email"] = data.email.lower()
        if data.password is not None:
            updates["password"] = hash_password(data.password)

        if not updates:
            return user

        try:
            await self._collection.update_one({"_id": user.id}, {"$set": updates})
        except DuplicateKeyError as exc:
            raise EmailAlreadyExistsError(data.email or user.email) from exc

        return user.model_copy(update=updates)

    async def delete(self, user_id: str) -> None:
        if not ObjectId.is_valid(user_id):
            raise UserNotFoundError(user_id)
        result = await self._collection.delete_one({"_id": ObjectId(user_id)})
        if result.deleted_count == 0:
            raise UserNotFoundError(user_id)
