"""Guards against module-level singleton leakage between tests."""

import asyncio

import pytest

from gameapi.api.v2.ws import gameplays
from gameapi.api.v2.ws.manager import gameplays_manager, presence_manager


def test_presence_manager_is_empty_at_start_of_test_1() -> None:
    assert presence_manager.online_user_ids() == []
    assert gameplays_manager.online_user_ids() == []


def test_presence_manager_is_empty_at_start_of_test_2() -> None:
    assert presence_manager.online_user_ids() == []
    assert gameplays_manager.online_user_ids() == []


async def test_reset_pending_abandons_cancels_and_clears_tasks() -> None:
    task = asyncio.create_task(asyncio.sleep(60))
    gameplays._pending_abandons["user-id"] = task

    gameplays.reset_pending_abandons()

    assert gameplays._pending_abandons == {}
    with pytest.raises(asyncio.CancelledError):
        await task
