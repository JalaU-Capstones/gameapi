from __future__ import annotations

import asyncio
from typing import Any

import pytest

import gameapi.services.invitation_expiry as invitation_expiry


async def test_run_pending_expiry_loop_logs_exception_and_stops_on_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    sleep_calls: list[float] = []
    logged: list[str] = []

    class DummyEngine:
        async def expire_pending_invitations(self, older_than_seconds: int) -> None:
            calls.append(older_than_seconds)
            if len(calls) == 1:
                raise RuntimeError("boom")
            raise asyncio.CancelledError

    def fake_exception(message: str, *args: Any, **kwargs: Any) -> None:
        logged.append(message)

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(invitation_expiry.logger, "exception", fake_exception)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await invitation_expiry.run_pending_expiry_loop(
            DummyEngine(),
            interval_seconds=5.0,
            ttl_seconds=42,
        )

    assert calls == [42, 42]
    assert sleep_calls == [5.0]
    assert logged == ["pending_expiry_failed"]


async def test_run_queued_expiry_loop_logs_exception_and_stops_on_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    sleep_calls: list[float] = []
    logged: list[str] = []

    class DummyEngine:
        async def expire_queued_invitations(self, older_than_seconds: int) -> None:
            calls.append(older_than_seconds)
            if len(calls) == 1:
                raise RuntimeError("queue boom")
            raise asyncio.CancelledError

    def fake_exception(message: str, *args: Any, **kwargs: Any) -> None:
        logged.append(message)

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        if len(sleep_calls) >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr(invitation_expiry.logger, "exception", fake_exception)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await invitation_expiry.run_queued_expiry_loop(
            DummyEngine(),
            interval_seconds=10.0,
            ttl_seconds=120,
        )

    assert calls == [120, 120]
    assert sleep_calls == [10.0]
    assert logged == ["queued_expiry_failed"]
