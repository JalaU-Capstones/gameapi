"""v2 REST API.

For now, v2 REST mirrors v1 exactly. WebSocket endpoints are added under
`/api/v2/ws/*`. When a REST contract needs to diverge from v1, that endpoint
should be reimplemented here instead of re-exporting from v1.
"""

from fastapi import APIRouter

from gameapi.api.v2 import auth as v2_auth
from gameapi.api.v2 import gameplays as v2_gameplays
from gameapi.api.v2 import logs as v2_logs
from gameapi.api.v2 import users as v2_users
from gameapi.api.v2.ws.router import router as ws_router

api_router = APIRouter(prefix="/api/v2")
api_router.include_router(v2_auth.router)
api_router.include_router(v2_users.router)
api_router.include_router(v2_gameplays.router)
api_router.include_router(v2_logs.router)
api_router.include_router(ws_router)
