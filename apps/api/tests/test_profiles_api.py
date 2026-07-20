import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import unique_email

pytestmark = pytest.mark.integration

PASSWORD = "sandi-aman-123"

DRAFT = {
    "display_name": "Studio Uji",
    "city": "Bandung",
    "bio": "Fotografer pernikahan.",
    "specialty": "wedding",
    "starting_price_idr": 1_500_000,
}


def register(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Uji Profil"},
    )
    assert response.status_code == 201, response.text


def test_profiles_require_authentication() -> None:
    with TestClient(create_app()) as client:
        assert client.patch("/api/v1/profiles/me", json={"full_name": "X Y"}).status_code == 401
        assert client.put("/api/v1/profiles/me/creator", json=DRAFT).status_code == 401
        assert client.post("/api/v1/profiles/me/creator/submit").status_code == 401


def test_update_full_name(email_cleanup: list[str]) -> None:
    email = unique_email("nama")
    email_cleanup.append(email)
    with TestClient(create_app()) as client:
        register(client, email)
        response = client.patch("/api/v1/profiles/me", json={"full_name": "Nama Baru"})
    assert response.status_code == 200
    assert response.json()["data"]["full_name"] == "Nama Baru"


def test_creator_draft_submit_flow_and_lock(email_cleanup: list[str]) -> None:
    email = unique_email("kreator")
    email_cleanup.append(email)
    with TestClient(create_app()) as client:
        register(client, email)

        draft = client.put("/api/v1/profiles/me/creator", json=DRAFT)
        assert draft.status_code == 200
        assert draft.json()["data"]["status"] == "draft"

        submitted = client.post("/api/v1/profiles/me/creator/submit")
        assert submitted.status_code == 200
        assert submitted.json()["data"]["status"] == "pending"
        assert submitted.json()["data"]["submitted_at"] is not None

        locked = client.put("/api/v1/profiles/me/creator", json=DRAFT)
        assert locked.status_code == 409
        assert locked.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"

        resubmit = client.post("/api/v1/profiles/me/creator/submit")
        assert resubmit.status_code == 409

        me = client.get("/api/v1/auth/me")
        assert me.json()["data"]["creator_profile"]["status"] == "pending"


def test_submit_without_draft_is_incomplete(email_cleanup: list[str]) -> None:
    email = unique_email("tanpa-draft")
    email_cleanup.append(email)
    with TestClient(create_app()) as client:
        register(client, email)
        response = client.post("/api/v1/profiles/me/creator/submit")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CREATOR_PROFILE_INCOMPLETE"
