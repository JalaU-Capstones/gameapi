"""In-process background loops that expire stale invitations."""

from __future__ import annotations

import asyncio
import logging

from gameapi.services.game_engine_service import GameEngineService

logger = logging.getLogger(__name__)


async def run_pending_expiry_loop(
    engine: GameEngineService,
    *,
    interval_seconds: float = 10.0,
    ttl_seconds: int = 60,
) -> None:
    while True:
        try:
            await engine.expire_pending_invitations(older_than_seconds=ttl_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("pending_expiry_failed")
        await asyncio.sleep(interval_seconds)


async def run_queued_expiry_loop(
    engine: GameEngineService,
    *,
    interval_seconds: float = 30.0,
    ttl_seconds: int = 5 * 60,
) -> None:
    while True:
        try:
            await engine.expire_queued_invitations(older_than_seconds=ttl_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("queued_expiry_failed")
        await asyncio.sleep(interval_seconds)
