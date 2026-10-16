from __future__ import annotations

import pytest

from gameapi.services.exceptions import InvitationRetryLimitExceededError
from gameapi.services.invitation_retry import InvitationRetryTracker


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def tracker(clock: FakeClock) -> InvitationRetryTracker:
    return InvitationRetryTracker(max_attempts=3, window_seconds=180, monotonic_fn=clock)


def test_first_retry_returns_attempt_and_remaining(tracker: InvitationRetryTracker) -> None:
    assert tracker.check_and_record("host", "guest") == (1, 2)


def test_retry_limit_reached_returns_progressive_remaining_attempts(
    tracker: InvitationRetryTracker,
) -> None:
    assert tracker.check_and_record("host", "guest") == (1, 2)
    assert tracker.check_and_record("host", "guest") == (2, 1)
    assert tracker.check_and_record("host", "guest") == (3, 0)


def test_fourth_retry_raises_with_remaining_window_and_pair_details(
    tracker: InvitationRetryTracker,
    clock: FakeClock,
) -> None:
    tracker.check_and_record("host", "guest")
    tracker.check_and_record("host", "guest")
    tracker.check_and_record("host", "guest")
    clock.advance(1.0)

    with pytest.raises(InvitationRetryLimitExceededError) as exc_info:
        tracker.check_and_record("host", "guest")

    exc = exc_info.value
    assert exc.host_id == "host"
    assert exc.guest_id == "guest"
    assert exc.retry_after_seconds == 179


def test_retry_window_slides_and_prunes_expired_entries(
    tracker: InvitationRetryTracker,
    clock: FakeClock,
) -> None:
    for _ in range(3):
        tracker.check_and_record("host", "guest")

    with pytest.raises(InvitationRetryLimitExceededError):
        tracker.check_and_record("host", "guest")

    clock.advance(181.0)
    assert tracker.check_and_record("host", "guest") == (1, 2)


def test_partial_slide_still_raises_until_window_expires(
    tracker: InvitationRetryTracker,
    clock: FakeClock,
) -> None:
    tracker.check_and_record("host", "guest")
    clock.advance(40.0)
    tracker.check_and_record("host", "guest")
    clock.advance(40.0)
    tracker.check_and_record("host", "guest")

    clock.advance(20.0)
    with pytest.raises(InvitationRetryLimitExceededError):
        tracker.check_and_record("host", "guest")

    clock.advance(81.0)
    assert tracker.check_and_record("host", "guest") == (3, 0)


def test_retry_entries_for_different_pairs_are_independent() -> None:
    tracker_a = InvitationRetryTracker(max_attempts=3, window_seconds=180)
    tracker_b = InvitationRetryTracker(max_attempts=3, window_seconds=180)

    assert tracker_a.check_and_record("host-1", "guest-1") == (1, 2)
    assert tracker_a.check_and_record("host-1", "guest-1") == (2, 1)
    assert tracker_a.check_and_record("host-1", "guest-1") == (3, 0)

    with pytest.raises(InvitationRetryLimitExceededError):
        tracker_a.check_and_record("host-1", "guest-1")

    assert tracker_a.check_and_record("host-1", "guest-2") == (1, 2)
    assert tracker_b.check_and_record("host-2", "guest-1") == (1, 2)


def test_retry_limit_zero_disables_retries() -> None:
    tracker = InvitationRetryTracker(max_attempts=0, window_seconds=180)

    with pytest.raises(InvitationRetryLimitExceededError) as exc_info:
        tracker.check_and_record("host", "guest")

    exc = exc_info.value
    assert exc.retry_after_seconds == 0
    assert exc.host_id == "host"
    assert exc.guest_id == "guest"


def test_reset_clears_every_pair(tracker: InvitationRetryTracker) -> None:
    tracker.check_and_record("host", "guest")
    tracker.check_and_record("host", "guest")
    tracker.check_and_record("host", "guest")

    tracker.reset()

    assert tracker.check_and_record("host", "guest") == (1, 2)


def test_retry_after_seconds_is_positive_integer_across_window_boundary(
    clock: FakeClock,
) -> None:
    tracker = InvitationRetryTracker(max_attempts=3, window_seconds=180, monotonic_fn=clock)
    tracker.check_and_record("host", "guest")
    tracker.check_and_record("host", "guest")
    tracker.check_and_record("host", "guest")

    clock.advance(179.0)
    with pytest.raises(InvitationRetryLimitExceededError) as exc_info:
        tracker.check_and_record("host", "guest")
    assert isinstance(exc_info.value.retry_after_seconds, int)
    assert exc_info.value.retry_after_seconds >= 1

    clock.advance(1.0)
    with pytest.raises(InvitationRetryLimitExceededError) as exc_info:
        tracker.check_and_record("host", "guest")
    assert isinstance(exc_info.value.retry_after_seconds, int)
    assert exc_info.value.retry_after_seconds >= 1


def test_identical_retry_key_does_not_duplicate_without_clock_advance() -> None:
    tracker = InvitationRetryTracker(max_attempts=3, window_seconds=180)

    assert tracker.check_and_record("host", "guest") == (1, 2)
    assert tracker.check_and_record("host", "guest") == (2, 1)
