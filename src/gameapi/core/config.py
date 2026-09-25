from functools import lru_cache
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class PostgresSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POSTGRES_", env_file=".env", extra="ignore")

    uri: str = Field(
        default="postgresql+asyncpg://gameapi:gameapi@localhost:5432/gameapi",
        min_length=1,
    )


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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    jwt: JWTSettings = Field(default_factory=JWTSettings)
    app: AppSettings = Field(default_factory=AppSettings)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
