from __future__ import annotations

import asyncio

from gameapi.services.event_bus import EventBus


async def test_event_bus_subscribe_registers_and_counts() -> None:
    bus = EventBus()

    async def callback(_event: dict[str, object]) -> None:
        return None

    bus.subscribe("game-1", "user-1", callback)

    assert bus.channel_subscriber_count("game-1") == 1
    assert bus.active_channels() == ["game-1"]

    await bus.shutdown()


async def test_event_bus_publish_delivers_to_one_subscriber() -> None:
    bus = EventBus()
    received: list[dict[str, object]] = []

    async def callback(event: dict[str, object]) -> None:
        received.append(event)

    bus.subscribe("game-1", "user-1", callback)
    await bus.publish("game-1", {"event": "ping", "payload": {}})
    await asyncio.sleep(0.05)

    assert received == [{"event": "ping", "payload": {}}]
    await bus.shutdown()


async def test_event_bus_publish_delivers_to_multiple_subscribers() -> None:
    bus = EventBus()
    received: list[str] = []

    async def callback_1(event: dict[str, object]) -> None:
        received.append(str(event["payload"]))

    async def callback_2(event: dict[str, object]) -> None:
        received.append(str(event["payload"]))

    bus.subscribe("game-1", "user-1", callback_1)
    bus.subscribe("game-1", "user-2", callback_2)

    await bus.publish("game-1", {"event": "message", "payload": {"value": 10}})
    await asyncio.sleep(0.05)

    assert len(received) == 2
    assert received == ["{'value': 10}", "{'value': 10}"]
    await bus.shutdown()


async def test_event_bus_publish_to_empty_channel_is_noop() -> None:
    bus = EventBus()

    await bus.publish("empty-channel", {"event": "message", "payload": {}})

    assert bus.channel_subscriber_count("empty-channel") == 0
    assert bus.active_channels() == []
    await bus.shutdown()


async def test_event_bus_unsubscribe_removes_subscriber_and_channel() -> None:
    bus = EventBus()

    async def callback(_event: dict[str, object]) -> None:
        return None

    bus.subscribe("game-1", "user-1", callback)
    bus.unsubscribe("game-1", "user-1")

    assert bus.channel_subscriber_count("game-1") == 0
    assert bus.active_channels() == []
    assert "game-1" not in bus._queues
    await bus.shutdown()


async def test_event_bus_unsubscribe_twice_is_safe() -> None:
    bus = EventBus()

    async def callback(_event: dict[str, object]) -> None:
        return None

    bus.subscribe("game-1", "user-1", callback)
    bus.unsubscribe("game-1", "user-1")
    bus.unsubscribe("game-1", "user-1")

    assert bus.channel_subscriber_count("game-1") == 0
    await bus.shutdown()


async def test_event_bus_failing_subscriber_does_not_block_others() -> None:
    bus = EventBus()
    received: list[str] = []

    async def failing_callback(_event: dict[str, object]) -> None:
        raise RuntimeError("boom")

    async def working_callback(event: dict[str, object]) -> None:
        received.append(str(event["payload"]))

    bus.subscribe("game-1", "user-1", failing_callback)
    bus.subscribe("game-1", "user-2", working_callback)

    await bus.publish("game-1", {"event": "message", "payload": {"value": "ok"}})
    await asyncio.sleep(0.05)

    assert received == ["{'value': 'ok'}"]
    await bus.shutdown()


async def test_subscribe_idempotent_same_subscriber_id() -> None:
    bus = EventBus()

    async def first_callback(_event: dict[str, object]) -> None:
        return None

    async def second_callback(_event: dict[str, object]) -> None:
        return None

    bus.subscribe("game-1", "user-1", first_callback)
    bus.subscribe("game-1", "user-1", second_callback)

    assert bus.channel_subscriber_count("game-1") == 1
    assert "user-1" in bus._subscribers["game-1"]
    await bus.shutdown()


async def test_unsubscribe_last_subscriber_cleans_worker() -> None:
    bus = EventBus()

    async def callback(_event: dict[str, object]) -> None:
        return None

    bus.subscribe("game-1", "user-1", callback)
    bus.unsubscribe("game-1", "user-1")

    assert "game-1" not in bus._subscribers
    assert "game-1" not in bus._queues
    assert "game-1" not in bus._workers
    await bus.shutdown()


async def test_shutdown_cancels_all_workers() -> None:
    bus = EventBus()

    async def callback(_event: dict[str, object]) -> None:
        await asyncio.sleep(10)

    bus.subscribe("game-1", "user-1", callback)
    bus.subscribe("game-2", "user-2", callback)
    await bus.shutdown()

    assert bus._subscribers == {}
    assert bus._queues == {}
    assert bus._workers == {}


async def test_event_bus_shutdown_cancels_workers_and_clears_state() -> None:
    bus = EventBus()

    async def callback(_event: dict[str, object]) -> None:
        await asyncio.sleep(1)

    bus.subscribe("game-1", "user-1", callback)
    await bus.shutdown()

    assert bus.channel_subscriber_count("game-1") == 0
    assert bus.active_channels() == []
    assert bus._queues == {}
    assert bus._subscribers == {}
    assert bus._workers == {}


async def test_event_bus_active_channels_returns_only_channels_with_subscribers() -> None:
    bus = EventBus()

    async def callback(_event: dict[str, object]) -> None:
        return None

    bus.subscribe("game-1", "user-1", callback)
    bus.subscribe("game-2", "user-2", callback)
    bus.unsubscribe("game-1", "user-1")

    assert bus.active_channels() == ["game-2"]
    await bus.shutdown()
