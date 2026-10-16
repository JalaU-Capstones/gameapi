from __future__ import annotations

import importlib

import pytest

from gameapi.api.v2.ws.auth import parse_limit
from gameapi.core.config import settings
from gameapi.core.ws_rate_limit import UserWindowLimiter


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
def limiter(clock: FakeClock) -> UserWindowLimiter:
    return UserWindowLimiter("3/minute", monotonic_fn=clock)


def test_user_window_limiter_allows_calls_below_limit(limiter: UserWindowLimiter) -> None:
    assert limiter.check_and_record("user-a") == (True, 0)
    assert limiter.check_and_record("user-a") == (True, 0)


def test_user_window_limiter_rejects_calls_at_limit(
    limiter: UserWindowLimiter,
    clock: FakeClock,
) -> None:
    limiter.check_and_record("user-a")
    limiter.check_and_record("user-a")
    allowed, retry_after = limiter.check_and_record("user-a")

    assert allowed is True
    assert retry_after == 0

    clock.advance(0.1)
    allowed, retry_after = limiter.check_and_record("user-a")
    assert allowed is False
    assert retry_after >= 1


def test_user_window_limiter_slides_after_period_expiry(
    limiter: UserWindowLimiter,
    clock: FakeClock,
) -> None:
    for _ in range(3):
        assert limiter.check_and_record("user-a") == (True, 0)

    clock.advance(61.0)
    assert limiter.check_and_record("user-a") == (True, 0)


def test_user_window_limiter_keeps_keys_independent(limiter: UserWindowLimiter) -> None:
    for _ in range(3):
        assert limiter.check_and_record("user-a") == (True, 0)

    assert limiter.check_and_record("user-b") == (True, 0)
    assert limiter.check_and_record("user-b") == (True, 0)


def test_user_window_limiter_allow_wrapper(limiter: UserWindowLimiter) -> None:
    assert limiter.allow("user-a") is True
    assert limiter.allow("user-a") is True
    assert limiter.allow("user-a") is True
    assert limiter.allow("user-a") is False


def test_user_window_limiter_retry_after_uses_zero_and_positive_values(
    limiter: UserWindowLimiter,
    clock: FakeClock,
) -> None:
    assert limiter.retry_after("user-a") == 0
    limiter.check_and_record("user-a")
    limiter.check_and_record("user-a")
    limiter.check_and_record("user-a")
    assert limiter.retry_after("user-a") >= 1

    clock.advance(61.0)
    assert limiter.retry_after("user-a") == 0


def test_user_window_limiter_reset_clears_all_keys(limiter: UserWindowLimiter) -> None:
    limiter.check_and_record("user-a")
    limiter.check_and_record("user-a")
    limiter.check_and_record("user-a")

    limiter.reset()

    assert limiter.allow("user-a") is True


@pytest.mark.parametrize(
    ("limit", "expected_count", "expected_period"),
    [
        ("10/second", 10, 1.0),
        ("5/minute", 5, 60.0),
        ("3/hour", 3, 3600.0),
        ("2/day", 2, 86400.0),
    ],
)
def test_parse_limit_supports_each_supported_duration(
    limit: str,
    expected_count: int,
    expected_period: float,
) -> None:
    assert parse_limit(limit) == (expected_count, expected_period)
    limiter = UserWindowLimiter(limit)
    assert limiter._count == expected_count
    assert limiter._period == expected_period


def test_user_window_limiter_rejects_malformed_limits() -> None:
    with pytest.raises(ValueError):
        UserWindowLimiter("bad-limit")

    with pytest.raises(KeyError):
        UserWindowLimiter("2/week")


def test_create_game_limiter_uses_settings_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    original = settings.rate_limit.create_game
    import gameapi.core.ws_rate_limit as ws_rate_limit

    monkeypatch.setattr(settings.rate_limit, "create_game", "2/minute")
    try:
        importlib.reload(ws_rate_limit)
        assert ws_rate_limit.create_game_limiter._count == 2
        assert ws_rate_limit.create_game_limiter._period == 60.0
    finally:
        monkeypatch.setattr(settings.rate_limit, "create_game", original)
        importlib.reload(ws_rate_limit)
