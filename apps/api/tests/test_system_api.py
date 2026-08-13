from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import get_settings
from app.main import create_app

VALID_STARTUP_ENVIRONMENT = {
    "JEPRET_ENVIRONMENT": "test",
    "JEPRET_DATABASE_URL": "postgresql+asyncpg://jepret:jepret@db:5432/jepret",
    "JEPRET_PUBLIC_ORIGIN": "http://localhost:8080",
    "JEPRET_MINIO_ENDPOINT": "http://minio:9000",
    "JEPRET_MINIO_ACCESS_KEY": "minioadmin",
    "JEPRET_MINIO_SECRET_KEY": "minioadmin",
}


@pytest.fixture
def valid_startup_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[None]:
    for name, value in VALID_STARTUP_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    try:
        yield
    finally:
        get_settings.cache_clear()


def test_app_startup_requires_explicit_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    for name, value in VALID_STARTUP_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("JEPRET_ENVIRONMENT", raising=False)
    monkeypatch.chdir(tmp_path)
    get_settings.cache_clear()

    try:
        with pytest.raises(ValidationError, match="environment"), TestClient(create_app()):
            pass
    finally:
        get_settings.cache_clear()


def test_health_returns_consistent_envelope_and_request_id(
    valid_startup_environment: None,
) -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health", headers={"X-Request-ID": "req-test-123"})

    assert response.status_code == 200
    assert response.json() == {"data": {"status": "ok"}}
    assert response.headers["X-Request-ID"] == "req-test-123"


def test_unknown_route_uses_error_envelope(valid_startup_environment: None) -> None:
    with TestClient(create_app()) as client:
        response = client.get("/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ROUTE_NOT_FOUND"
