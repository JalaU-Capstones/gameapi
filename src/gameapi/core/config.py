from functools import lru_cache
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _normalize_asyncpg_uri(value: str | None) -> str | None:
    if value is None:
        return None
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+asyncpg://", 1)
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+asyncpg://", 1)
    return value


class PostgresSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POSTGRES_", env_file=".env", extra="ignore")

    uri: str = Field(
        default="******localhost:5432/gameapi",
        min_length=1,
    )

    @field_validator("uri")
    @classmethod
    def _normalize_asyncpg_driver(cls, value: str) -> str:
        """
        Render's `fromDatabase.connectionString` returns a URI without the
        async driver suffix. SQLAlchemy async requires it explicitly.
        Normalize on load so the rest of the codebase never has to care.
        """
        return _normalize_asyncpg_uri(value) or value


class JWTSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JWT_", env_file=".env", extra="ignore")

    secret_key: str = Field(
        default="Una_Clave_Secreta_Super_Segura_con_Minimo_32_Caracteres_123456789",
        min_length=32,
    )
    algorithm: str = "HS256"
    issuer: str = "GameAPI"
    audience: str = "GameAPI"
    expire_minutes: int = Field(default=60, gt=0)

    @model_validator(mode="after")
    def _require_explicit_secret_in_production(self) -> "JWTSettings":
        import os

        if (
            os.getenv("APP_ENV", "development") == "production"
            and self.secret_key
            == "Una_Clave_Secreta_Super_Segura_con_Minimo_32_Caracteres_123456789"
        ):
            raise ValueError(
                "JWT_SECRET_KEY must be overridden in production. "
                "Generate one with: openssl rand -base64 48"
            )
        return self


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")

    env: Literal["development", "staging", "production"] = Field(
        default="development",
        validation_alias=AliasChoices("APP_ENV", "env"),
    )
    host: str = Field(
        default="0.0.0.0",
        validation_alias=AliasChoices("APP_HOST", "host"),
    )
    port: int = Field(
        default=8080,
        validation_alias=AliasChoices("APP_PORT", "port"),
    )
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["*"],
        validation_alias=AliasChoices("CORS_ORIGINS", "APP_CORS_ORIGINS", "cors_origins"),
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("cors_origins")
    @classmethod
    def _require_explicit_origins_in_production(cls, value: list[str]) -> list[str]:
        import os

        if os.getenv("APP_ENV") == "production" and value == ["*"]:
            raise ValueError(
                "CORS_ORIGINS must be an explicit list in production. "
                "Wildcard '*' is not allowed with credentials."
            )
        return value


class LogSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOG_", env_file=".env", extra="ignore")

    buffer_size: int = Field(default=100, gt=0)
    flush_interval_seconds: float = Field(default=5.0, gt=0)
    retention_days: int = Field(default=30, gt=0)
    queue_maxsize: int = Field(default=1000, gt=0)
    admin_emails: Annotated[list[str], NoDecode] = Field(default_factory=list)

    @field_validator("admin_emails", mode="before")
    @classmethod
    def _split_emails(cls, value: object) -> object:
        if isinstance(value, str):
            return [email.strip().lower() for email in value.split(",") if email.strip()]
        if isinstance(value, list):
            return [str(email).strip().lower() for email in value]
        return value


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_", env_file=".env", extra="ignore")

    access_cookie_name: str = "gameapi_at"
    refresh_cookie_name: str = "gameapi_rt"
    access_token_expire_minutes: int = Field(default=15, gt=0)
    refresh_token_expire_days: int = Field(default=7, gt=0)
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_domain: str | None = None
    refresh_cookie_path: str = "/api/v2/auth"
    access_cookie_path: str = "/"

    @model_validator(mode="after")
    def _validate_samesite(self) -> "AuthSettings":
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("cookie_samesite='none' requires cookie_secure=True")
        return self

    @model_validator(mode="after")
    def _require_secure_cookies_in_production(self) -> "AuthSettings":
        import os

        if os.getenv("APP_ENV", "development") == "production" and not self.cookie_secure:
            raise ValueError("AUTH_COOKIE_SECURE must be True in production (HTTPS-only cookies)")
        return self


class RateLimitSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RATE_LIMIT_", env_file=".env", extra="ignore")

    enabled: bool = True
    storage_uri: str = "memory://"

    anonymous_default: str = "60/minute"
    login: str = "5/minute"
    register_limit: str = Field(
        default="3/minute",
        validation_alias=AliasChoices("RATE_LIMIT_REGISTER", "register_limit"),
    )
    refresh: str = "10/minute"

    authenticated_default: str = "60/minute"
    auth_me: str = "60/minute"
    logs_me: str = "30/minute"
    logs_admin: str = "300/minute"

    ws_handshake: str = "10/minute"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    postgres_migrator_uri: str | None = Field(
        default=None,
        validation_alias=AliasChoices("POSTGRES_MIGRATOR_URI", "postgres_migrator_uri"),
    )
    jwt: JWTSettings = Field(default_factory=JWTSettings)
    app: AppSettings = Field(default_factory=AppSettings)
    log: LogSettings = Field(default_factory=LogSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)

    @property
    def postgres_uri(self) -> str:
        return self.postgres.uri

    @field_validator("postgres_migrator_uri")
    @classmethod
    def _normalize_migrator_uri(cls, value: str | None) -> str | None:
        return _normalize_asyncpg_uri(value)

    @model_validator(mode="after")
    def _normalize_nested_uris(self) -> "Settings":
        """
        Normalize nested URIs that may not have been processed by their
        own validators.

        pydantic-settings does not always run field_validator on nested
        BaseSettings models when the value comes from an environment
        variable. Normalizing here guarantees the correction runs
        regardless of the source.
        """
        self.postgres.uri = _normalize_asyncpg_uri(self.postgres.uri) or self.postgres.uri
        if self.postgres_migrator_uri is not None:
            self.postgres_migrator_uri = _normalize_asyncpg_uri(self.postgres_migrator_uri)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
