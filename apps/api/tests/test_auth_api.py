import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import unique_email

pytestmark = pytest.mark.integration

PASSWORD = "sandi-aman-123"


def _register(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Uji Auth"},
    )
    assert response.status_code == 201, response.text


def test_register_sets_session_cookie_and_returns_user(email_cleanup: list[str]) -> None:
    email = unique_email("register")
    email_cleanup.append(email)
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/auth/register",
            json={"email": email.upper(), "password": PASSWORD, "full_name": "Uji Auth"},
        )
    assert response.status_code == 201
    assert response.json()["data"]["email"] == email
    assert "jepret_session" in response.cookies


def test_register_rejects_duplicate_email(email_cleanup: list[str]) -> None:
    email = unique_email("duplicate")
    email_cleanup.append(email)
    with TestClient(create_app()) as client:
        _register(client, email)
        response = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": PASSWORD, "full_name": "Uji Auth"},
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_TAKEN"


def test_login_with_wrong_password_is_generic_401(email_cleanup: list[str]) -> None:
    email = unique_email("login-salah")
    email_cleanup.append(email)
    with TestClient(create_app()) as client:
        _register(client, email)
        response = client.post(
            "/api/v1/auth/login", json={"email": email, "password": "password-salah"}
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_me_requires_session_cookie() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_login_then_me_then_logout_flow(email_cleanup: list[str]) -> None:
    email = unique_email("alur")
    email_cleanup.append(email)
    with TestClient(create_app()) as client:
        _register(client, email)
        client.cookies.clear()

        login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert login.status_code == 200

        me = client.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json()["data"]["email"] == email
        assert me.json()["data"]["is_admin"] is False

        logout = client.post("/api/v1/auth/logout")
        assert logout.status_code == 200

        after = client.get("/api/v1/auth/me")
        assert after.status_code == 401


def test_mutating_request_with_foreign_origin_is_rejected() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "a@b.c", "password": "x"},
            headers={"Origin": "https://jahat.example"},
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN_ORIGIN"


def test_mutating_request_with_public_origin_is_allowed(email_cleanup: list[str]) -> None:
    email = unique_email("origin-ok")
    email_cleanup.append(email)
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": PASSWORD, "full_name": "Uji Auth"},
            headers={"Origin": "http://localhost:8080"},
        )
    assert response.status_code == 201
