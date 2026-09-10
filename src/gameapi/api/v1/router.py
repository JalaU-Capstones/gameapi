from fastapi import APIRouter

from gameapi.api.v1 import gameplays, users

api_router = APIRouter(prefix="/api")
api_router.include_router(users.router)
api_router.include_router(gameplays.router)
