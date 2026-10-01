"""v2 REST API."""

from fastapi import APIRouter

from gameapi.api.v2 import auth, gameplays, logs, users
from gameapi.api.v2.ws.router import router as ws_router

api_router = APIRouter(prefix="/api/v2")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(gameplays.router)
api_router.include_router(logs.router)
api_router.include_router(ws_router)
