from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from time import monotonic

from gameapi.api.v2.ws.auth import parse_limit
from gameapi.core.config import settings


class UserWindowLimiter:
    """Simple per-user sliding-window limiter keyed by a user id."""

    def __init__(
        self,
        limit: str,
        *,
        monotonic_fn: Callable[[], float] = monotonic,
    ) -> None:
        self.limit = limit
        self._now = monotonic_fn
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._count, self._period = parse_limit(limit)

    def reset(self) -> None:
        self._attempts.clear()

    def check_and_record(self, user_id: str) -> tuple[bool, int]:
        now = self._now()
        window = self._attempts.setdefault(user_id, deque())
        while window and now - window[0] > self._period:
            window.popleft()

        if len(window) >= self._count:
            retry_after = max(1, int(window[0] + self._period - now))
            return False, retry_after

        window.append(now)
        return True, 0

    def allow(self, user_id: str) -> bool:
        allowed, _ = self.check_and_record(user_id)
        return allowed

    def retry_after(self, user_id: str) -> int:
        now = self._now()
        window = self._attempts.setdefault(user_id, deque())
        while window and now - window[0] > self._period:
            window.popleft()
        if not window or len(window) < self._count:
            return 0
        return max(1, int(window[0] + self._period - now))


create_game_limiter = UserWindowLimiter(settings.rate_limit.create_game)
