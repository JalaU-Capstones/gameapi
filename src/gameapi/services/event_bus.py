"""In-process event bus for real-time message dispatch.

Uses asyncio.Queue per channel to decouple publishers from subscribers.
A channel is created on first subscribe and torn down when the last
subscriber unsubscribes.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

Event = dict[str, Any]
Subscriber = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        # channel_id -> list of (subscriber_id, callback)
        self._subscribers: dict[str, dict[str, Subscriber]] = {}
        # channel_id -> asyncio.Queue
        self._queues: dict[str, asyncio.Queue[Event]] = {}
        # channel_id -> worker task
        self._workers: dict[str, asyncio.Task[None]] = {}

    def _ensure_channel(self, channel_id: str) -> None:
        if channel_id not in self._subscribers:
            self._subscribers[channel_id] = {}
        if channel_id not in self._queues:
            self._queues[channel_id] = asyncio.Queue(maxsize=1000)
        if channel_id not in self._workers:
            self._workers[channel_id] = asyncio.create_task(self._dispatch_loop(channel_id))

    async def _dispatch_loop(self, channel_id: str) -> None:
        queue = self._queues.get(channel_id)
        if queue is None:
            return

        try:
            while True:
                event = await queue.get()
                subscribers = list(self._subscribers.get(channel_id, {}).values())
                if subscribers:
                    await asyncio.gather(
                        *(self._deliver_event(subscriber, event) for subscriber in subscribers),
                        return_exceptions=True,
                    )
                queue.task_done()
        except asyncio.CancelledError:
            logger.debug("Event bus worker cancelled for channel '%s'", channel_id)
            raise
        finally:
            self._subscribers.pop(channel_id, None)
            self._queues.pop(channel_id, None)
            self._workers.pop(channel_id, None)

    async def _deliver_event(self, callback: Subscriber, event: Event) -> None:
        try:
            await callback(event)
        except (asyncio.CancelledError, RuntimeError):
            logger.warning("Subscriber callback was interrupted for event %s", event)
        except Exception:
            logger.exception("Subscriber callback raised an exception for event %s", event)

    def subscribe(self, channel_id: str, subscriber_id: str, callback: Subscriber) -> None:
        """
        Register a subscriber for a channel.

        subscriber_id must be unique within the channel (e.g. the user_id).
        Idempotent: subscribing twice with the same subscriber_id replaces the
        previous callback.
        """
        self._ensure_channel(channel_id)
        self._subscribers[channel_id][subscriber_id] = callback

    def unsubscribe(self, channel_id: str, subscriber_id: str) -> None:
        """
        Remove a subscriber. If it was the last one, tear down the channel:
        cancel the worker task and clear the queue.
        """
        channel_subscribers = self._subscribers.get(channel_id)
        if channel_subscribers is None:
            return

        channel_subscribers.pop(subscriber_id, None)
        if not channel_subscribers:
            self._subscribers.pop(channel_id, None)
            task = self._workers.pop(channel_id, None)
            if task is not None:
                task.cancel()
            self._queues.pop(channel_id, None)

    async def publish(self, channel_id: str, event: Event) -> None:
        """
        Enqueue an event for a channel. Non-blocking.
        If no subscribers exist for the channel, the event is dropped
        (with a debug log).
        """
        subscribers = self._subscribers.get(channel_id)
        if not subscribers:
            logger.debug("Dropping event for channel '%s': no subscribers", channel_id)
            return

        queue = self._queues.get(channel_id)
        if queue is None:
            logger.debug("Dropping event for channel '%s': queue missing", channel_id)
            return

        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Event queue for channel '%s' is full; dropping event", channel_id)

    def channel_subscriber_count(self, channel_id: str) -> int:
        """Return the number of subscribers for a channel (for tests/metrics)."""
        return len(self._subscribers.get(channel_id, {}))

    def active_channels(self) -> list[str]:
        """Return channel IDs with at least one subscriber (for tests/metrics)."""
        return [channel_id for channel_id, subscribers in self._subscribers.items() if subscribers]

    async def shutdown(self) -> None:
        """Cancel all workers and clear state. Called on app shutdown."""
        for task in list(self._workers.values()):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        self._subscribers.clear()
        self._queues.clear()
        self._workers.clear()


event_bus = EventBus()
