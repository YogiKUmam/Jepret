import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from tests.conftest import fresh_connection, unique_email

pytestmark = pytest.mark.integration

PASSWORD = "sandi-aman-123"


def future_date(days: int = 30) -> str:
    return (datetime.now(UTC).date() + timedelta(days=days)).isoformat()


def register(client: TestClient, email_cleanup: list[str], name: str) -> str:
    email = unique_email("bk")
    email_cleanup.append(email)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": name},
    )
    assert response.status_code == 201, response.text
    return email


def login(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text


async def approve_profile(profile_id: str) -> None:
    async with fresh_connection() as connection:
        await connection.execute(
            text(
                "UPDATE creator_profiles SET status = 'approved', reviewed_at = now() "
                "WHERE id = :profile_id"
            ),
            {"profile_id": profile_id},
        )


async def make_creator(client: TestClient, email_cleanup: list[str], name: str) -> tuple[str, str]:
    """Registers an approved creator; returns (email, profile_id)."""
    email = register(client, email_cleanup, name)
    draft = client.put(
        "/api/v1/profiles/me/creator",
        json={
            "display_name": name,
            "city": "Bandung",
            "bio": "Uji booking.",
            "specialty": "wedding",
            "starting_price_idr": 1_500_000,
        },
    )
    assert draft.status_code == 200, draft.text
    profile_id: str = draft.json()["data"]["id"]
    await approve_profile(profile_id)
    client.post("/api/v1/auth/logout")
    return email, profile_id


def request_booking(client: TestClient, profile_id: str, days: int = 30) -> dict:
    response = client.post(
        "/api/v1/bookings",
        json={
            "creator_id": profile_id,
            "event_date": future_date(days),
            "event_city": "Bandung",
            "notes": "Akad pagi.",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def test_bookings_require_authentication() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/bookings").status_code == 401
        assert client.get("/api/v1/bookings/incoming").status_code == 401
        assert (
            client.post(
                "/api/v1/bookings",
                json={
                    "creator_id": str(uuid.uuid4()),
                    "event_date": future_date(),
                    "event_city": "Bandung",
                },
            ).status_code
            == 401
        )


async def test_client_can_request_and_list_booking(email_cleanup: list[str]) -> None:
    with TestClient(create_app()) as client:
        _, profile_id = await make_creator(client, email_cleanup, "Studio Booking")
        register(client, email_cleanup, "Klien Uji")
        booking = request_booking(client, profile_id)
        listing = client.get("/api/v1/bookings")
    assert booking["status"] == "requested"
    assert booking["quoted_price_idr"] == 1_500_000
    assert booking["creator"]["display_name"] == "Studio Booking"
    assert [item["id"] for item in listing.json()["data"]] == [booking["id"]]


async def test_request_validation_rules(email_cleanup: list[str]) -> None:
    with TestClient(create_app()) as client:
        creator_email, profile_id = await make_creator(client, email_cleanup, "Studio Aturan")
        register(client, email_cleanup, "Klien Aturan")
        past = client.post(
            "/api/v1/bookings",
            json={
                "creator_id": profile_id,
                "event_date": "2020-01-01",
                "event_city": "Bandung",
            },
        )
        missing = client.post(
            "/api/v1/bookings",
            json={
                "creator_id": str(uuid.uuid4()),
                "event_date": future_date(),
                "event_city": "Bandung",
            },
        )
        client.post("/api/v1/auth/logout")
        login(client, creator_email)
        self_booking = client.post(
            "/api/v1/bookings",
            json={
                "creator_id": profile_id,
                "event_date": future_date(),
                "event_city": "Bandung",
            },
        )
    assert past.status_code == 422
    assert past.json()["error"]["code"] == "INVALID_EVENT_DATE"
    assert missing.status_code == 404
    assert self_booking.status_code == 422
    assert self_booking.json()["error"]["code"] == "CANNOT_BOOK_SELF"


async def test_creator_accepts_then_completes(email_cleanup: list[str]) -> None:
    with TestClient(create_app()) as client:
        creator_email, profile_id = await make_creator(client, email_cleanup, "Studio Terima")
        client_email = register(client, email_cleanup, "Klien Terima")
        booking = request_booking(client, profile_id)
        client.post("/api/v1/auth/logout")

        login(client, creator_email)
        incoming = client.get("/api/v1/bookings/incoming")
        accepted = client.post(f"/api/v1/bookings/{booking['id']}/accept")
        double_accept = client.post(f"/api/v1/bookings/{booking['id']}/accept")
        completed = client.post(f"/api/v1/bookings/{booking['id']}/complete")
        client.post("/api/v1/auth/logout")

        login(client, client_email)
        seen_by_client = client.get(f"/api/v1/bookings/{booking['id']}")
    assert [item["id"] for item in incoming.json()["data"]] == [booking["id"]]
    assert incoming.json()["data"][0]["client_name"] == "Klien Terima"
    assert accepted.json()["data"]["status"] == "accepted"
    assert double_accept.status_code == 409
    assert double_accept.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"
    assert completed.json()["data"]["status"] == "completed"
    assert seen_by_client.json()["data"]["status"] == "completed"


async def test_accepting_twice_on_the_same_date_is_rejected(
    email_cleanup: list[str],
) -> None:
    with TestClient(create_app()) as client:
        creator_email, profile_id = await make_creator(client, email_cleanup, "Studio Bentrok")
        register(client, email_cleanup, "Klien A")
        first = request_booking(client, profile_id, days=40)
        client.post("/api/v1/auth/logout")
        register(client, email_cleanup, "Klien B")
        second = request_booking(client, profile_id, days=40)
        client.post("/api/v1/auth/logout")

        login(client, creator_email)
        accepted = client.post(f"/api/v1/bookings/{first['id']}/accept")
        clash = client.post(f"/api/v1/bookings/{second['id']}/accept")
    assert accepted.status_code == 200
    assert clash.status_code == 409
    assert clash.json()["error"]["code"] == "DATE_UNAVAILABLE"


async def test_permissions_are_enforced(email_cleanup: list[str]) -> None:
    with TestClient(create_app()) as client:
        _, profile_id = await make_creator(client, email_cleanup, "Studio Izin")
        register(client, email_cleanup, "Klien Izin")
        booking = request_booking(client, profile_id)
        client_cannot_accept = client.post(f"/api/v1/bookings/{booking['id']}/accept")
        client.post("/api/v1/auth/logout")

        register(client, email_cleanup, "Orang Lain")
        stranger_detail = client.get(f"/api/v1/bookings/{booking['id']}")
        stranger_cancel = client.post(f"/api/v1/bookings/{booking['id']}/cancel")
    assert client_cannot_accept.status_code == 404
    assert stranger_detail.status_code == 404
    assert stranger_cancel.status_code == 404


async def test_client_can_cancel_before_completion(email_cleanup: list[str]) -> None:
    with TestClient(create_app()) as client:
        creator_email, profile_id = await make_creator(client, email_cleanup, "Studio Batal")
        register(client, email_cleanup, "Klien Batal")
        booking = request_booking(client, profile_id, days=50)
        cancelled = client.post(f"/api/v1/bookings/{booking['id']}/cancel")
        client.post("/api/v1/auth/logout")

        login(client, creator_email)
        cannot_accept = client.post(f"/api/v1/bookings/{booking['id']}/accept")
    assert cancelled.json()["data"]["status"] == "cancelled"
    assert cannot_accept.status_code == 409
