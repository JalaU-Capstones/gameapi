import asyncio
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from gameapi.services.chat_service import ChatMessage, ChatService, chat_service
from gameapi.services.exceptions import (
    ChatEmptyMessageError,
    ChatMessageTooLongError,
    ChatRateLimitedError,
)


class FakeClock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def service(clock: FakeClock) -> ChatService:
    return ChatService(monotonic_fn=clock)


@pytest.mark.asyncio
async def test_ring_buffer_cap(service: ChatService) -> None:
    for idx in range(201):
        await service.publish(f"user-{idx}", "tester", f"message-{idx}")

    history = service.history()
    assert len(history) == 50
    assert history[0].content == "message-151"
    assert history[-1].content == "message-200"


def test_ttl_prune_on_read(service: ChatService) -> None:
    now = datetime.now(UTC)
    old_one = ChatMessage(
        id="old-1",
        user_id="u1",
        user_name="Old",
        content="expired-one",
        timestamp=now - timedelta(hours=3),
    )
    old_two = ChatMessage(
        id="old-2",
        user_id="u2",
        user_name="Old2",
        content="expired-two",
        timestamp=now - timedelta(hours=4),
    )
    recent = ChatMessage(
        id="recent",
        user_id="u1",
        user_name="Recent",
        content="fresh",
        timestamp=now - timedelta(minutes=5),
    )
    service._messages.extend([old_one, old_two, recent])

    removed = service.prune_expired()

    assert removed == 2
    assert [item.content for item in service.history()] == ["fresh"]


@pytest.mark.asyncio
async def test_ttl_prune_on_publish(service: ChatService) -> None:
    first = await service.publish("u1", "name", "first")
    old_timestamp = datetime.now(UTC) - timedelta(hours=3)
    object.__setattr__(first, "timestamp", old_timestamp)
    service._messages.clear()
    service._messages.append(first)

    second = await service.publish("u1", "name", "second")

    assert len(service._messages) == 1
    assert service._messages[0].content == "second"
    assert service._messages[0].id == second.id


def test_history_min_rule(service: ChatService) -> None:
    now = datetime.now(UTC)
    for idx in range(60):
        service._messages.append(
            ChatMessage(
                id=f"m-{idx}",
                user_id="u",
                user_name="Tester",
                content=f"msg-{idx}",
                timestamp=now - timedelta(minutes=5 + (idx % 25)),
            )
        )

    history = service.history()
    assert len(history) == 50

    service._messages.clear()
    for idx in range(60):
        minutes_ago = 15 if idx < 30 else 45
        service._messages.append(
            ChatMessage(
                id=f"m-{idx}",
                user_id="u",
                user_name="Tester",
                content=f"msg-{idx}",
                timestamp=now - timedelta(minutes=minutes_ago),
            )
        )

    history = service.history()
    assert len(history) == 30
    assert all((now - message.timestamp).total_seconds() <= 1800 for message in history)


def test_history_returns_copies(service: ChatService) -> None:
    now = datetime.now(UTC)
    service._messages.append(
        ChatMessage(
            id="m1",
            user_id="u1",
            user_name="Tester",
            content="one",
            timestamp=now,
        )
    )

    history = service.history()
    history.append(
        ChatMessage(
            id="m2",
            user_id="u2",
            user_name="Tester",
            content="two",
            timestamp=now,
        )
    )

    assert len(service._messages) == 1
    assert [item.content for item in service._messages] == ["one"]


@pytest.mark.asyncio
async def test_rate_limit_blocks_after_ten(service: ChatService, clock: FakeClock) -> None:
    for idx in range(10):
        await service.publish("user", "tester", f"message-{idx}")

    with pytest.raises(ChatRateLimitedError) as exc:
        await service.publish("user", "tester", "too-fast")

    assert exc.value.retry_after_seconds == 30


@pytest.mark.asyncio
async def test_block_duration_and_window_reset(service: ChatService, clock: FakeClock) -> None:
    for idx in range(10):
        await service.publish("user", "tester", f"message-{idx}")

    with pytest.raises(ChatRateLimitedError):
        await service.publish("user", "tester", "blocked")

    clock.advance(29)
    with pytest.raises(ChatRateLimitedError):
        await service.publish("user", "tester", "still-blocked")

    clock.advance(1.1)
    message = await service.publish("user", "tester", "allowed")
    assert message.content == "allowed"

    clock.advance(11)
    message = await service.publish("user", "tester", "after-window-reset")
    assert message.content == "after-window-reset"


@pytest.mark.asyncio
async def test_sanitization_and_whitespace_and_nfc(service: ChatService) -> None:
    message = await service.publish("user", "name", "\u202exterm\u2066")
    assert "\u202e" not in message.content
    assert "\u2066" not in message.content
    assert message.content == "xterm"

    spaced = await service.publish("user", "name", "hello\u00a0\u2003world")
    assert spaced.content == "hello world"

    normalized = await service.publish("user", "name", "cafe\u0301")
    assert normalized.content == "café"


@pytest.mark.asyncio
async def test_empty_after_sanitization(service: ChatService) -> None:
    with pytest.raises(ChatEmptyMessageError):
        await service.publish("u1", "name", "   \u200b  ")


@pytest.mark.asyncio
async def test_too_long_and_exact_limit(service: ChatService) -> None:
    message = "a" * 500
    stored = await service.publish("u1", "name", message)
    assert stored.content == message

    with pytest.raises(ChatMessageTooLongError):
        await service.publish("u1", "name", "a" * 501)


@pytest.mark.asyncio
async def test_name_fallback_and_name_sanitization(service: ChatService) -> None:
    empty_name = await service.publish("u1", "   \u200b  ", "hello")
    assert empty_name.user_name == "Unknown"

    sanitized = await service.publish("u1", "\u202ebad\u2066", "hello")
    assert sanitized.user_name == "bad"

    fallback = await service.publish("u1", "\u200b \u00ad", "hello")
    assert fallback.user_name == "Unknown"


@pytest.mark.asyncio
async def test_rate_limit_applies_before_validation(service: ChatService) -> None:
    for _ in range(10):
        with pytest.raises(ChatEmptyMessageError):
            await service.publish("user", "name", "   \u200b  ")

    with pytest.raises(ChatRateLimitedError):
        await service.publish("user", "name", "   \u200b  ")


@pytest.mark.asyncio
async def test_chat_message_is_immutable() -> None:
    message = ChatMessage("id", "user", "name", "content", datetime.now(UTC))
    with pytest.raises(FrozenInstanceError):
        message.user_id = "other"  # type: ignore[misc]


@pytest.mark.asyncio
async def test_concurrent_publishes(service: ChatService) -> None:
    tasks = [service.publish(f"user-{idx}", "name", f"message-{idx}") for idx in range(20)]
    messages = await asyncio.gather(*tasks)

    assert len(messages) == 20
    assert len(service._messages) == 20
    assert {message.user_id for message in messages} == {f"user-{idx}" for idx in range(20)}


@pytest.mark.asyncio
async def test_reset_clears_state(service: ChatService) -> None:
    for idx in range(10):
        await service.publish("user", "name", f"message-{idx}")
    with pytest.raises(ChatRateLimitedError):
        await service.publish("user", "name", "blocked")

    service.reset()

    assert len(service._messages) == 0
    assert service._rate_windows == {}
    assert service._blocked_until == {}


def test_singleton_exists() -> None:
    assert isinstance(chat_service, ChatService)
