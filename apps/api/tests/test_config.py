import pytest
from pydantic import ValidationError

from app.core.config import Environment, Settings


def complete_settings_input() -> dict[str, str]:
    return {
        "database_url": "postgresql+asyncpg://jepret:jepret@db:5432/jepret",
        "public_origin": "http://localhost:8080",
        "minio_endpoint": "http://minio:9000",
        "minio_public_endpoint": "http://localhost:9000",
        "minio_access_key": "minioadmin",
        "minio_secret_key": "minioadmin",
    }


def test_settings_require_explicit_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JEPRET_ENVIRONMENT", raising=False)

    with pytest.raises(ValidationError, match="environment"):
        Settings(_env_file=None, **complete_settings_input())  # type: ignore[arg-type]


def test_settings_require_minio_public_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JEPRET_MINIO_PUBLIC_ENDPOINT", raising=False)
    settings_input = complete_settings_input()
    del settings_input["minio_public_endpoint"]

    with pytest.raises(ValidationError, match="minio_public_endpoint"):
        Settings(  # type: ignore[arg-type]
            _env_file=None,
            environment=Environment.DEVELOPMENT,
            **settings_input,
        )


def test_settings_accept_complete_development_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JEPRET_REDIS_URL", raising=False)

    settings = Settings(
        _env_file=None,
        environment=Environment.DEVELOPMENT,
        **complete_settings_input(),  # type: ignore[arg-type]
    )
    assert settings.environment is Environment.DEVELOPMENT
    assert settings.minio_private_bucket == "jepret-private"
    assert settings.storage_signed_url_ttl_seconds == 600
    assert settings.redis_url is None


def test_settings_reject_wildcard_public_origin() -> None:
    with pytest.raises(ValidationError, match="public_origin"):
        Settings(
            _env_file=None,
            environment=Environment.DEVELOPMENT,
            **(complete_settings_input() | {"public_origin": "*"}),  # type: ignore[arg-type]
        )
