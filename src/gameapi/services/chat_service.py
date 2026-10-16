"""In-memory global chat service.

Best-effort, single-process. The buffer is intentionally lost on cold
start; there is no persistence layer. See `README.md` for the rationale.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import unicodedata
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil

from gameapi.services.exceptions import (
    ChatEmptyMessageError,
    ChatMessageTooLongError,
    ChatRateLimitedError,
)

logger = logging.getLogger(__name__)

# Patterns mirror the frontend `sanitizeDisplayName` helper.
_BIDI_AND_INVISIBLE = re.compile(
    r"[\u00AD\u061C\u180E\u200B-\u200F\u202A-\u202E\u2060-\u2064\u2066-\u2069\uFEFF]"
)
_CONTROL_CHARS = re.compile(r"[\u0000-\u001F\u007F-\u009F]")
_WHITESPACE_COLLAPSE = re.compile(r"\s+")


def _sanitize(value: str) -> str:
    """Strip dangerous or invisible characters, collapse whitespace, NFC-normalize."""
    sanitized = unicodedata.normalize("NFC", value)
    sanitized = _BIDI_AND_INVISIBLE.sub("", sanitized)
    sanitized = _CONTROL_CHARS.sub("", sanitized)
    sanitized = _WHITESPACE_COLLAPSE.sub(" ", sanitized)
    return sanitized.strip()


@dataclass(frozen=True, slots=True)
class ChatMessage:
    id: str
    user_id: str
    user_name: str
    content: str
    timestamp: datetime


class ChatService:
    def __init__(
        self,
        *,
        max_messages: int = 200,
        ttl_seconds: int = 7200,
        history_max_messages: int = 50,
        history_max_age_seconds: int = 1800,
        rate_max_messages: int = 10,
        rate_window_seconds: float = 10.0,
        rate_block_seconds: float = 30.0,
        max_content_length: int = 500,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_messages = max_messages
        self.ttl_seconds = ttl_seconds
        self.history_max_messages = history_max_messages
        self.history_max_age_seconds = history_max_age_seconds
        self.rate_max_messages = rate_max_messages
        self.rate_window_seconds = rate_window_seconds
        self.rate_block_seconds = rate_block_seconds
        self.max_content_length = max_content_length
        self._monotonic_fn = monotonic_fn
        self._messages: deque[ChatMessage] = deque(maxlen=max_messages)
        self._rate_windows: dict[str, deque[float]] = {}
        self._blocked_until: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def publish(self, user_id: str, user_name: str, content: str) -> ChatMessage:
        async with self._lock:
            now = self._monotonic_fn()
            # Rate limiting is enforced before content validation so malformed messages
            # still count against the user's quota.
            self._check_rate_limit(user_id, now)

            clean_content = _sanitize(content)
            if clean_content == "":
                raise ChatEmptyMessageError()
            if len(clean_content) > self.max_content_length:
                raise ChatMessageTooLongError(self.max_content_length)

            clean_name = _sanitize(user_name) or "Unknown"
            self._prune_locked()

            message = ChatMessage(
                id=uuid.uuid4().hex,
                user_id=user_id,
                user_name=clean_name,
                content=clean_content,
                timestamp=datetime.now(UTC),
            )
            self._messages.append(message)
            logger.info(
                "Chat message published",
                extra={
                    "event_type": "chat_message_published",
                    "player_id": user_id,
                    "metadata": {"length": len(clean_content)},
                },
            )
            return message

    def history(self) -> list[ChatMessage]:
        self.prune_expired()
        cutoff = datetime.now(UTC) - timedelta(seconds=self.history_max_age_seconds)
        recent = [message for message in self._messages if message.timestamp >= cutoff]
        return recent[-self.history_max_messages :]

    def prune_expired(self) -> int:
        return self._prune_locked()

    def reset(self) -> None:
        """Clear all state. TEST-ONLY. Production code must not call this."""
        self._messages.clear()
        self._rate_windows.clear()
        self._blocked_until.clear()

    def _check_rate_limit(self, user_id: str, now: float) -> None:
        blocked_until = self._blocked_until.get(user_id)
        if blocked_until is not None:
            if blocked_until > now:
                remaining = blocked_until - now
                raise ChatRateLimitedError(int(ceil(remaining)))
            del self._blocked_until[user_id]

        window = self._rate_windows.setdefault(user_id, deque())
        while window and now - window[0] > self.rate_window_seconds:
            window.popleft()

        if len(window) >= self.rate_max_messages:
            self._blocked_until[user_id] = now + self.rate_block_seconds
            window.clear()
            raise ChatRateLimitedError(int(self.rate_block_seconds))

        window.append(now)

    def _prune_locked(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(seconds=self.ttl_seconds)
        removed = 0
        while self._messages and self._messages[0].timestamp < cutoff:
            self._messages.popleft()
            removed += 1
        return removed


chat_service = ChatService()
