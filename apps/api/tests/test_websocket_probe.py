from fastapi.testclient import TestClient

from app.main import create_app


def test_development_websocket_probe_sends_status_and_closes(
    valid_startup_environment: None,
) -> None:
    with TestClient(create_app()) as client, client.websocket_connect("/ws/health") as websocket:
        assert websocket.receive_json() == {"status": "ok"}
