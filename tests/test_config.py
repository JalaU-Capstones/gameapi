from __future__ import annotations

import pytest
from pydantic import ValidationError

from gameapi.core.config import (
    AppSettings,
    AuthSettings,
    LogSettings,
    PostgresSettings,
    RateLimitSettings,
    Settings,
)


@pytest.mark.parametrize(
    ("raw_uri", "expected"),
    [
        ("postgresql://host:5432/db", "postgresql+asyncpg://host:5432/db"),
        ("postgres://host:5432/db", "postgresql+asyncpg://host:5432/db"),
        ("postgresql+asyncpg://host:5432/db", "postgresql+asyncpg://host:5432/db"),
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
    monkeypatch.setenv("POSTGRES_URI", "postgresql://render-host:5432/gameapi")
    settings = Settings()
    assert settings.postgres.uri.startswith("postgresql+asyncpg://")
    assert "psycopg" not in settings.postgres.uri


def test_settings_preserves_already_normalized_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    """A URI that already has +asyncpg must not be altered."""
    monkeypatch.setenv("POSTGRES_URI", "postgresql+asyncpg://render-host:5432/gameapi")
    settings = Settings()
    assert settings.postgres.uri == "postgresql+asyncpg://render-host:5432/gameapi"


def test_production_settings_valid_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 64)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("POSTGRES_URI", "postgresql://db.example:5432/gameapi")

    settings = Settings()

    assert settings.app.env == "production"
    assert settings.auth.cookie_secure is True
    assert settings.app.cors_origins == ["https://app.example.com"]


def test_production_rejects_default_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "JWT_SECRET_KEY",
        "Una_Clave_Secreta_Super_Segura_con_Minimo_32_Caracteres_123456789",
    )
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")

    with pytest.raises(ValidationError, match="JWT_SECRET_KEY must be overridden"):
        Settings()


def test_production_rejects_insecure_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 64)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")

    with pytest.raises(ValidationError, match="AUTH_COOKIE_SECURE must be True"):
        Settings()


def test_production_rejects_wildcard_cors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 64)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")
    monkeypatch.setenv("CORS_ORIGINS", "*")

    with pytest.raises(ValidationError, match="CORS_ORIGINS must be an explicit list"):
        Settings()


def test_settings_normalizes_postgresql_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_URI", "postgresql://db.example:5432/gameapi")
    assert Settings().postgres.uri.startswith("postgresql+asyncpg://")


def test_settings_normalizes_postgres_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_URI", "postgres://db.example:5432/gameapi")
    assert Settings().postgres.uri.startswith("postgresql+asyncpg://")


def test_settings_preserves_asyncpg_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_URI", "postgresql+asyncpg://db.example:5432/gameapi")
    assert Settings().postgres.uri == "postgresql+asyncpg://db.example:5432/gameapi"


def test_samesite_none_requires_secure() -> None:
    with pytest.raises(ValidationError, match="requires cookie_secure=True"):
        AuthSettings(cookie_samesite="none", cookie_secure=False)


def test_samesite_none_with_secure_is_valid() -> None:
    settings = AuthSettings(cookie_samesite="none", cookie_secure=True)
    assert settings.cookie_samesite == "none"


def test_cors_origins_string_is_split() -> None:
    settings = AppSettings(cors_origins="https://a.com, https://b.com")
    assert settings.cors_origins == ["https://a.com", "https://b.com"]


def test_cors_origins_list_passthrough() -> None:
    settings = AppSettings(cors_origins=["https://a.com"])
    assert settings.cors_origins == ["https://a.com"]


def test_admin_emails_string_is_split_and_lowercased() -> None:
    settings = LogSettings(admin_emails=" Admin@X.com , Other@Y.com ")
    assert settings.admin_emails == ["admin@x.com", "other@y.com"]


def test_admin_emails_list_is_normalized() -> None:
    settings = LogSettings(admin_emails=["A@B.COM"])
    assert settings.admin_emails == ["a@b.com"]


def test_rate_limit_register_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_REGISTER", "5/minute")
    settings = RateLimitSettings()
    assert settings.register_limit == "5/minute"
