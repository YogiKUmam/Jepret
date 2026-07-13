from fastapi.testclient import TestClient

from app.main import create_app


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
