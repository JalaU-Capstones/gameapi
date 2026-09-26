"""v1 API — Frozen. Mirrors the C# legacy migration 1:1. Do not modify."""

from fastapi import APIRouter

from gameapi.api.v1 import gameplays, users

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(users.router)
api_router.include_router(gameplays.router)
