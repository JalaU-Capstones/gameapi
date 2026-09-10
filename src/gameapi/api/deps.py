from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase

from gameapi.core.database import (
    MongoDatabase,
    MongoDocument,
    get_gameplays_collection,
    get_users_collection,
)
from gameapi.core.security import TokenDecodeError, decode_access_token
from gameapi.models.user import UserDocument
from gameapi.services import GameplayService, UserService

bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> AsyncIOMotorDatabase[MongoDocument]:
    return MongoDatabase.get_db()


def get_user_service(
    collection: Annotated[AsyncIOMotorCollection[MongoDocument], Depends(get_users_collection)],
) -> UserService:
    return UserService(collection)


def get_gameplay_service(
    collection: Annotated[AsyncIOMotorCollection[MongoDocument], Depends(get_gameplays_collection)],
) -> GameplayService:
    return GameplayService(collection)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
GameplayServiceDep = Annotated[GameplayService, Depends(get_gameplay_service)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    user_service: UserServiceDep,
) -> UserDocument:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = decode_access_token(credentials.credentials)
    except TokenDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await user_service.get_by_id(claims.sub)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[UserDocument, Depends(get_current_user)]
