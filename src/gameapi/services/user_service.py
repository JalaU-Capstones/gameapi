import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from gameapi.core.security import hash_password
from gameapi.db.models.user import User
from gameapi.repositories.user_repository import UserRepository
from gameapi.schemas.user import UserCreate, UserResponse, UserUpdate
from gameapi.services.exceptions import EmailAlreadyExistsError, UserNotFoundError


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = UserRepository(session)

    async def ensure_indexes(self) -> None:
        return None

    async def list_all(self) -> list[UserResponse]:
        users = await self._repo.list_all()
        return [UserResponse.model_validate(user) for user in users]

    async def get_by_id(self, user_id: str) -> UserResponse | None:
        try:
            parsed_id = uuid.UUID(user_id)
        except ValueError:
            return None
        user = await self._repo.get_by_id(parsed_id)
        if user is None:
            return None
        return UserResponse.model_validate(user)

    async def get_by_email(self, email: str) -> User | None:
        return await self._repo.get_by_email(email.lower())

    async def create(self, data: UserCreate) -> UserResponse:
        user = User(
            name=data.name,
            email=data.email.lower(),
            password_hash=hash_password(data.password),
        )
        try:
            created = await self._repo.create(user)
        except IntegrityError as exc:
            await self._session.rollback()
            if exc.orig is not None and getattr(exc.orig, "pgcode", None) == "23505":
                raise EmailAlreadyExistsError(data.email) from exc
            raise
        return UserResponse.model_validate(created)

    async def update(self, user_id: str, data: UserUpdate) -> UserResponse:
        try:
            parsed_id = uuid.UUID(user_id)
        except ValueError as exc:
            raise UserNotFoundError(user_id) from exc

        user = await self._repo.get_by_id(parsed_id)
        if user is None:
            raise UserNotFoundError(user_id)

        update_fields: dict[str, object] = {}
        if data.name is not None:
            update_fields["name"] = data.name
        if data.email is not None:
            update_fields["email"] = data.email.lower()
        if data.password is not None:
            update_fields["password_hash"] = hash_password(data.password)

        if not update_fields:
            return UserResponse.model_validate(user)

        for key, value in update_fields.items():
            setattr(user, key, value)

        try:
            await self._repo.update(user)
        except IntegrityError as exc:
            await self._session.rollback()
            if exc.orig is not None and getattr(exc.orig, "pgcode", None) == "23505":
                raise EmailAlreadyExistsError(data.email or user.email) from exc
            raise

        return UserResponse.model_validate(user)

    async def delete(self, user_id: str) -> None:
        try:
            parsed_id = uuid.UUID(user_id)
        except ValueError as exc:
            raise UserNotFoundError(user_id) from exc

        user = await self._repo.get_by_id(parsed_id)
        if user is None:
            raise UserNotFoundError(user_id)
        await self._repo.delete(user)
