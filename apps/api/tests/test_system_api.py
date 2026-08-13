import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import get_settings
from app.main import create_app


def test_app_startup_requires_explicit_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    required_environment = {
        "JEPRET_DATABASE_URL": "postgresql+asyncpg://jepret:jepret@db:5432/jepret",
        "JEPRET_PUBLIC_ORIGIN": "http://localhost:8080",
        "JEPRET_MINIO_ENDPOINT": "http://minio:9000",
        "JEPRET_MINIO_ACCESS_KEY": "minioadmin",
        "JEPRET_MINIO_SECRET_KEY": "minioadmin",
    }
    for name, value in required_environment.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("JEPRET_ENVIRONMENT", raising=False)
    get_settings.cache_clear()

    try:
        with pytest.raises(ValidationError, match="environment"), TestClient(create_app()):
            pass
    finally:
        get_settings.cache_clear()


def test_health_returns_consistent_envelope_and_request_id() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health", headers={"X-Request-ID": "req-test-123"})

    assert response.status_code == 200
    assert response.json() == {"data": {"status": "ok"}}
    assert response.headers["X-Request-ID"] == "req-test-123"


def test_unknown_route_uses_error_envelope() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/missing")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ROUTE_NOT_FOUND"
