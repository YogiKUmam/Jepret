from fastapi.testclient import TestClient

from app.db.session import database_ready
from app.main import create_app


async def _database_unavailable() -> bool:
    return False


def test_readiness_returns_503_when_database_is_unavailable() -> None:
    app = create_app()
    app.dependency_overrides[database_ready] = _database_unavailable

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
