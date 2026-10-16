from fastapi import APIRouter

from gameapi.api.v2.ws import chat, gameplays, presence

router = APIRouter(prefix="/ws", tags=["WebSocket"])
router.include_router(gameplays.router)
router.include_router(presence.router)
router.include_router(chat.router)
