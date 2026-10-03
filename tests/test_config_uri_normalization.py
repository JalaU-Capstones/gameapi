"""Tests for PostgreSQL URI normalization in the settings layer."""

from __future__ import annotations

import pytest

from gameapi.core.config import PostgresSettings, Settings


@pytest.mark.parametrize(
    ("raw_uri", "expected"),
    [
        (
            "postgresql://user:pass@host:5432/db",
            "postgresql+asyncpg://user:pass@host:5432/db",
        ),
        (
            "postgres://user:pass@host:5432/db",
            "postgresql+asyncpg://user:pass@host:5432/db",
        ),
        (
            "postgresql+asyncpg://user:pass@host:5432/db",
            "postgresql+asyncpg://user:pass@host:5432/db",
        ),
    ],
)
def test_postgres_settings_normalizes_uri(raw_uri: str, expected: str) -> None:
    """Direct instantiation uses the field validator."""
    assert PostgresSettings(uri=raw_uri).uri == expected


def test_settings_normalizes_uri_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Even when the URI comes from an environment variable (which bypasses
    nested field validators in pydantic-settings), the parent-level
    model_validator normalizes it.
    """
    monkeypatch.setenv(
        "POSTGRES_URI",
        "postgresql://user:pass@render-host:5432/gameapi",
    )
    settings = Settings()
    assert settings.postgres.uri.startswith("postgresql+asyncpg://")
    assert "psycopg" not in settings.postgres.uri


def test_settings_preserves_already_normalized_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    """A URI that already has +asyncpg must not be altered."""
    monkeypatch.setenv(
        "POSTGRES_URI",
        "postgresql+asyncpg://user:pass@render-host:5432/gameapi",
    )
    settings = Settings()
    assert settings.postgres.uri == ("postgresql+asyncpg://user:pass@render-host:5432/gameapi")
