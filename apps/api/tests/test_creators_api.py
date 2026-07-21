import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from tests.conftest import fresh_connection, unique_email

pytestmark = pytest.mark.integration

PASSWORD = "sandi-aman-123"
BASE_REVIEWED_AT = datetime(2026, 7, 21, 8, 0, tzinfo=UTC)


async def _approve(profile_id: str, reviewed_at: datetime) -> None:
    async with fresh_connection() as connection:
        await connection.execute(
            text(
                "UPDATE creator_profiles SET status = 'approved', reviewed_at = :reviewed_at "
                "WHERE id = :profile_id"
            ),
            {"reviewed_at": reviewed_at, "profile_id": profile_id},
        )


async def create_creator(
    client: TestClient,
    email_cleanup: list[str],
    *,
    display_name: str,
    marker: str,
    city: str = "Bandung",
    specialty: str = "wedding",
    price: int = 1_000_000,
    approve_offset_minutes: int | None = 0,
    submit: bool = True,
) -> str:
    """Registers a fresh user with a creator draft; returns the profile id."""
    email = unique_email("mkt")
    email_cleanup.append(email)
    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": "Uji Marketplace"},
    )
    assert register.status_code == 201, register.text
    draft = client.put(
        "/api/v1/profiles/me/creator",
        json={
            "display_name": display_name,
            "city": city,
            "bio": f"Portofolio {marker}",
            "specialty": specialty,
            "starting_price_idr": price,
        },
    )
    assert draft.status_code == 200, draft.text
    profile_id: str = draft.json()["data"]["id"]
    if submit:
        assert client.post("/api/v1/profiles/me/creator/submit").status_code == 200
    if approve_offset_minutes is not None:
        await _approve(profile_id, BASE_REVIEWED_AT + timedelta(minutes=approve_offset_minutes))
    client.post("/api/v1/auth/logout")
    return profile_id


def _listing(client: TestClient, **params: object) -> dict[str, object]:
    response = client.get("/api/v1/creators", params=params)
    assert response.status_code == 200, response.text
    data: dict[str, object] = response.json()["data"]
    return data


async def test_only_approved_creators_are_listed(email_cleanup: list[str]) -> None:
    marker = uuid.uuid4().hex
    with TestClient(create_app()) as client:
        approved = await create_creator(
            client, email_cleanup, display_name="Terlihat", marker=marker
        )
        await create_creator(
            client,
            email_cleanup,
            display_name="Masih Pending",
            marker=marker,
            approve_offset_minutes=None,
        )
        await create_creator(
            client,
            email_cleanup,
            display_name="Masih Draft",
            marker=marker,
            submit=False,
            approve_offset_minutes=None,
        )
        data = _listing(client, q=marker)
    items = data["items"]
    assert isinstance(items, list)
    assert [item["id"] for item in items] == [approved]
    assert data["next_cursor"] is None


async def test_filters_narrow_the_listing(email_cleanup: list[str]) -> None:
    marker = uuid.uuid4().hex
    with TestClient(create_app()) as client:
        bandung = await create_creator(
            client,
            email_cleanup,
            display_name="Studio Bandung",
            marker=marker,
            city="Bandung",
            specialty="wedding",
            price=2_000_000,
            approve_offset_minutes=0,
        )
        jakarta = await create_creator(
            client,
            email_cleanup,
            display_name="Studio Jakarta",
            marker=marker,
            city="Jakarta",
            specialty="product",
            price=500_000,
            approve_offset_minutes=1,
        )
        by_city = _listing(client, q=marker, city="bandung")
        by_specialty = _listing(client, q=marker, specialty="PRODUCT")
        by_price = _listing(client, q=marker, min_price=1_000_000)
        by_max = _listing(client, q=marker, max_price=600_000)
    assert [item["id"] for item in by_city["items"]] == [bandung]
    assert [item["id"] for item in by_specialty["items"]] == [jakarta]
    assert [item["id"] for item in by_price["items"]] == [bandung]
    assert [item["id"] for item in by_max["items"]] == [jakarta]


async def test_cursor_pagination_has_no_gaps_or_duplicates(
    email_cleanup: list[str],
) -> None:
    marker = uuid.uuid4().hex
    with TestClient(create_app()) as client:
        ids = [
            await create_creator(
                client,
                email_cleanup,
                display_name=f"Studio {index}",
                marker=marker,
                approve_offset_minutes=index,
            )
            for index in range(3)
        ]
        first_page = _listing(client, q=marker, limit=2)
        assert isinstance(first_page["next_cursor"], str)
        second_page = _listing(client, q=marker, limit=2, cursor=first_page["next_cursor"])
    first_ids = [item["id"] for item in first_page["items"]]
    second_ids = [item["id"] for item in second_page["items"]]
    # Terbaru dulu: offset menit terbesar muncul pertama.
    assert first_ids == [ids[2], ids[1]]
    assert second_ids == [ids[0]]
    assert second_page["next_cursor"] is None


def test_listing_rejects_bad_parameters() -> None:
    with TestClient(create_app()) as client:
        invalid_cursor = client.get("/api/v1/creators", params={"cursor": "%%%"})
        limit_low = client.get("/api/v1/creators", params={"limit": 0})
        limit_high = client.get("/api/v1/creators", params={"limit": 51})
    assert invalid_cursor.status_code == 422
    assert invalid_cursor.json()["error"]["code"] == "INVALID_CURSOR"
    assert limit_low.status_code == 422
    assert limit_high.status_code == 422


async def test_detail_returns_only_approved(email_cleanup: list[str]) -> None:
    marker = uuid.uuid4().hex
    with TestClient(create_app()) as client:
        approved = await create_creator(
            client, email_cleanup, display_name="Studio Detail", marker=marker
        )
        pending = await create_creator(
            client,
            email_cleanup,
            display_name="Studio Pending",
            marker=marker,
            approve_offset_minutes=None,
        )
        ok = client.get(f"/api/v1/creators/{approved}")
        hidden = client.get(f"/api/v1/creators/{pending}")
        missing = client.get(f"/api/v1/creators/{uuid.uuid4()}")
    assert ok.status_code == 200
    body = ok.json()["data"]
    assert body["display_name"] == "Studio Detail"
    assert "status" not in body
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "NOT_FOUND"
    assert missing.status_code == 404
