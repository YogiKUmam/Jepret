import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_admin, unique_email
from tests.test_profiles_api import DRAFT, PASSWORD, register

pytestmark = pytest.mark.integration


async def _admin_client_email(email_cleanup: list[str]) -> str:
    email = unique_email("admin")
    email_cleanup.append(email)
    return email


def test_admin_routes_forbidden_for_regular_user(email_cleanup: list[str]) -> None:
    email = unique_email("bukan-admin")
    email_cleanup.append(email)
    with TestClient(create_app()) as client:
        register(client, email)
        response = client.get("/api/v1/admin/creator-applications")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_admin_routes_require_authentication() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/admin/creator-applications").status_code == 401


async def test_admin_can_approve_pending_application(email_cleanup: list[str]) -> None:
    creator_email = unique_email("calon")
    admin_email = unique_email("admin")
    email_cleanup.extend([creator_email, admin_email])

    with TestClient(create_app()) as creator:
        register(creator, creator_email)
        assert creator.put("/api/v1/profiles/me/creator", json=DRAFT).status_code == 200
        assert creator.post("/api/v1/profiles/me/creator/submit").status_code == 200

    with TestClient(create_app()) as admin:
        register(admin, admin_email)
        await make_admin(admin_email)

        listing = admin.get("/api/v1/admin/creator-applications")
        assert listing.status_code == 200
        entries = [item for item in listing.json()["data"] if item["user_email"] == creator_email]
        assert len(entries) == 1
        profile_id = entries[0]["profile"]["id"]

        approved = admin.post(f"/api/v1/admin/creator-applications/{profile_id}/approve")
        assert approved.status_code == 200
        assert approved.json()["data"]["status"] == "approved"
        assert approved.json()["data"]["reviewed_at"] is not None

        again = admin.post(f"/api/v1/admin/creator-applications/{profile_id}/approve")
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"

    with TestClient(create_app()) as creator:
        login = creator.post(
            "/api/v1/auth/login", json={"email": creator_email, "password": PASSWORD}
        )
        assert login.json()["data"]["creator_profile"]["status"] == "approved"


async def test_admin_can_reject_pending_application(email_cleanup: list[str]) -> None:
    creator_email = unique_email("ditolak")
    admin_email = unique_email("admin2")
    email_cleanup.extend([creator_email, admin_email])

    with TestClient(create_app()) as creator_client:
        register(creator_client, creator_email)
        creator_client.put("/api/v1/profiles/me/creator", json=DRAFT)
        creator_client.post("/api/v1/profiles/me/creator/submit")

    with TestClient(create_app()) as admin:
        register(admin, admin_email)
        await make_admin(admin_email)
        listing = admin.get("/api/v1/admin/creator-applications").json()["data"]
        profile_id = next(
            item["profile"]["id"] for item in listing if item["user_email"] == creator_email
        )
        rejected = admin.post(f"/api/v1/admin/creator-applications/{profile_id}/reject")
        assert rejected.status_code == 200
        assert rejected.json()["data"]["status"] == "rejected"

    with TestClient(create_app()) as creator_client:
        creator_client.post(
            "/api/v1/auth/login", json={"email": creator_email, "password": PASSWORD}
        )
        redraft = creator_client.put("/api/v1/profiles/me/creator", json=DRAFT)
        assert redraft.status_code == 200
        assert redraft.json()["data"]["status"] == "draft"
