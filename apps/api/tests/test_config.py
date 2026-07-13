from pydantic import ValidationError
import pytest

from app.core.config import Environment, Settings


def test_settings_accept_complete_development_environment() -> None:
    settings = Settings(
        environment=Environment.DEVELOPMENT,
        database_url="postgresql+asyncpg://jepret:jepret@db:5432/jepret",
        public_origin="http://localhost:8080",
        minio_endpoint="http://minio:9000",
        minio_access_key="minioadmin",
        minio_secret_key="minioadmin",
    )
    assert settings.environment is Environment.DEVELOPMENT
    assert settings.redis_url is None


def test_settings_reject_wildcard_public_origin() -> None:
    with pytest.raises(ValidationError, match="public_origin"):
        Settings(
            database_url="postgresql+asyncpg://jepret:jepret@db:5432/jepret",
            public_origin="*",
            minio_endpoint="http://minio:9000",
            minio_access_key="minioadmin",
            minio_secret_key="minioadmin",
        )
