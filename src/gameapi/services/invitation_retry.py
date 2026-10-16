from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from time import monotonic

from gameapi.core.config import settings
from gameapi.services.exceptions import InvitationRetryLimitExceededError


class InvitationRetryTracker:
    """Sliding-window retry counter keyed by (host_id, guest_id)."""

    def __init__(
        self,
        *,
        max_attempts: int | None = None,
        window_seconds: int | None = None,
        monotonic_fn: Callable[[], float] = monotonic,
    ) -> None:
        self._max_attempts = (
            settings.invitation.pair_max_attempts if max_attempts is None else max_attempts
        )
        self._window_seconds = (
            settings.invitation.pair_window_seconds if window_seconds is None else window_seconds
        )
        self._now = monotonic_fn
        self._attempts: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def reset(self) -> None:
        self._attempts.clear()

    def check_and_record(self, host_id: str, guest_id: str) -> tuple[int, int]:
        now = self._now()
        key = (host_id, guest_id)
        window = self._attempts.setdefault(key, deque())

        while window and now - window[0] > self._window_seconds:
            window.popleft()

        if self._max_attempts == 0:
            raise InvitationRetryLimitExceededError(host_id, guest_id, 0)

        if len(window) >= self._max_attempts:
            retry_after = max(1, int(window[0] + self._window_seconds - now))
            raise InvitationRetryLimitExceededError(host_id, guest_id, retry_after)

        window.append(now)
        attempt = len(window)
        remaining = max(0, self._max_attempts - attempt)
        return attempt, remaining


invitation_retry_tracker = InvitationRetryTracker()
