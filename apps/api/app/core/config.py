from enum import StrEnum
from functools import lru_cache

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JEPRET_", env_file=".env", extra="ignore")

    environment: Environment
    database_url: str
    public_origin: AnyHttpUrl
    minio_endpoint: AnyHttpUrl
    minio_public_endpoint: AnyHttpUrl
    minio_access_key: str = Field(min_length=1)
    minio_secret_key: str = Field(min_length=1)
    minio_private_bucket: str = Field(default="jepret-private", min_length=1)
    storage_signed_url_ttl_seconds: int = Field(default=600, ge=60, le=3600)
    redis_url: str | None = None

    @field_validator("public_origin", mode="before")
    @classmethod
    def reject_wildcard_origin(cls, value: object) -> object:
        if value == "*":
            raise ValueError("public_origin cannot be a wildcard")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
