from __future__ import annotations

import threading
import time
from typing import Any


class InMemoryIdempotencyStore:
    """Small process-local TTL cache for replay protection.

    This is intentionally a single-process implementation. When the API is scaled to
    multiple workers, replace it with a shared Redis or key-value store.
    """

    def __init__(self, ttl_seconds: int = 86400) -> None:
        self._ttl_seconds = ttl_seconds
        self._values: dict[str, tuple[float, Any]] = {}
        self._lock = threading.RLock()

    def _prune(self) -> None:
        now = time.monotonic()
        expired = [key for key, (expires_at, _) in self._values.items() if expires_at <= now]
        for key in expired:
            self._values.pop(key, None)

    def get(self, key: str) -> Any | None:
        with self._lock:
            self._prune()
            value = self._values.get(key)
            if value is None:
                return None
            expires_at, payload = value
            if expires_at <= time.monotonic():
                self._values.pop(key, None)
                return None
            return payload

    def set(self, key: str, value: Any, *, ttl_seconds: int | None = None) -> Any:
        with self._lock:
            expires_at = time.monotonic() + (
                ttl_seconds if ttl_seconds is not None else self._ttl_seconds
            )
            self._values[key] = (expires_at, value)
            return value

    def remove(self, key: str) -> None:
        with self._lock:
            self._values.pop(key, None)

    def key_for(self, namespace: str, *parts: str) -> str:
        cleaned = []
        for value in parts:
            if value is None:
                continue
            normalized = str(value).strip()
            if normalized:
                cleaned.append(normalized)
        return f"{namespace}:{':'.join(cleaned)}"


def _normalize_key_part(value: str) -> str:
    cleaned = str(value).strip()
    if "@" in cleaned:
        return cleaned.lower()
    return cleaned


def _default_idempotency_store() -> InMemoryIdempotencyStore:
    return InMemoryIdempotencyStore(ttl_seconds=86400)


request_idempotency_store = _default_idempotency_store()


def normalize_registration_identity(email: str) -> str:
    return str(email).strip().lower()


def replay_response_for(
    *,
    store: InMemoryIdempotencyStore,
    namespace: str,
    key_parts: tuple[str, ...],
) -> Any | None:
    return store.get(store.key_for(namespace, *(_normalize_key_part(part) for part in key_parts)))


def remember_response(
    *,
    store: InMemoryIdempotencyStore,
    namespace: str,
    key_parts: tuple[str, ...],
    value: Any,
    ttl_seconds: int | None = None,
) -> Any:
    key = store.key_for(namespace, *(_normalize_key_part(part) for part in key_parts))
    return store.set(key, value, ttl_seconds=ttl_seconds)


def remember_ws_create_game(
    *,
    host_id: str,
    request_id: str,
    game_id: str,
    store: InMemoryIdempotencyStore | None = None,
) -> str:
    target = store or request_idempotency_store
    target.set(target.key_for("ws:create_game", host_id, request_id), game_id, ttl_seconds=86400)
    return game_id


def lookup_ws_create_game(
    *,
    host_id: str,
    request_id: str,
    store: InMemoryIdempotencyStore | None = None,
) -> str | None:
    target = store or request_idempotency_store
    cached = target.get(target.key_for("ws:create_game", host_id, request_id))
    return str(cached) if cached is not None else None
