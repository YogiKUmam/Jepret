import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.models import Payment, PaymentEvent, User
from app.main import create_app
from tests.conftest import fresh_connection, unique_email

pytestmark = pytest.mark.integration

PASSWORD = "sandi-aman-123"
INTERNAL_PAYMENT_FIELDS = {
    "provider_reference",
    "idempotency_key",
    "raw_metadata",
    "events",
    "provider_event_id",
    "event_type",
}


def future_date(days: int = 30) -> str:
    return (datetime.now(UTC).date() + timedelta(days=days)).isoformat()


def register(client: TestClient, email_cleanup: list[str], name: str) -> str:
    email = unique_email("pay")
    email_cleanup.append(email)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": name},
    )
    assert response.status_code == 201, response.text
    return email


def login(client: TestClient, email: str) -> None:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text


def logout(client: TestClient) -> None:
    assert client.post("/api/v1/auth/logout").status_code == 200


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
    email = register(client, email_cleanup, name)
    response = client.put(
        "/api/v1/profiles/me/creator",
        json={
            "display_name": name,
            "city": "Bandung",
            "bio": "Uji pembayaran.",
            "specialty": "wedding",
            "starting_price_idr": 1_500_000,
        },
    )
    assert response.status_code == 200, response.text
    profile_id: str = response.json()["data"]["id"]
    await approve_profile(profile_id)
    logout(client)
    return email, profile_id


def request_booking(client: TestClient, profile_id: str, *, days: int = 30) -> dict:
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


def accept_booking(client: TestClient, booking_id: str, creator_email: str) -> None:
    logout(client)
    login(client, creator_email)
    response = client.post(f"/api/v1/bookings/{booking_id}/accept")
    assert response.status_code == 200, response.text
    logout(client)


async def payment_event_count(payment_id: str) -> int:
    async with fresh_connection() as connection:
        count = await connection.scalar(
            select(func.count(PaymentEvent.id)).where(
                PaymentEvent.payment_id == uuid.UUID(payment_id)
            )
        )
    assert count is not None
    return count


async def set_booking_completed(booking_id: str) -> None:
    async with fresh_connection() as connection:
        await connection.execute(
            text("UPDATE bookings SET status = 'completed', completed_at = now() WHERE id = :id"),
            {"id": booking_id},
        )


def create_payment(client: TestClient, booking_id: str, key: str | None = None):
    headers = {"Idempotency-Key": key} if key is not None else {}
    return client.post(f"/api/v1/bookings/{booking_id}/payments", headers=headers)


async def test_payment_endpoints_require_auth_except_webhook(
    email_cleanup: list[str],
) -> None:
    payment_id = str(uuid.uuid4())
    booking_id = str(uuid.uuid4())
    with TestClient(create_app()) as client:
        assert create_payment(client, booking_id, str(uuid.uuid4())).status_code == 401
        assert client.get(f"/api/v1/bookings/{booking_id}/payments").status_code == 401
        assert client.post(f"/api/v1/dev/payments/{payment_id}/simulate-paid").status_code == 401
        assert client.post(f"/api/v1/dev/payments/{payment_id}/simulate-release").status_code == 401
        webhook = client.post(
            "/api/v1/payments/webhooks/mock",
            json={
                "payment_id": payment_id,
                "event_id": "unauthenticated-event",
                "event_type": "paid",
            },
        )
    assert webhook.status_code == 404
    assert webhook.json()["error"]["code"] == "NOT_FOUND"


async def test_create_payment_has_exact_amounts_and_is_idempotent(
    email_cleanup: list[str],
) -> None:
    key = str(uuid.uuid4())
    with TestClient(create_app()) as client:
        creator_email, profile_id = await make_creator(client, email_cleanup, "Studio Pembayaran")
        client_email = register(client, email_cleanup, "Klien Pembayaran")
        booking = request_booking(client, profile_id)
        accept_booking(client, booking["id"], creator_email)
        login(client, client_email)

        created = create_payment(client, booking["id"], key)
        same_key = create_payment(client, booking["id"], key)
        fresh_key = create_payment(client, booking["id"], str(uuid.uuid4()))
        booking_after = client.get(f"/api/v1/bookings/{booking['id']}")

    assert created.status_code == 201, created.text
    assert same_key.status_code == fresh_key.status_code == 200
    payment = created.json()["data"]
    assert payment["amount_idr"] == 1_500_000
    assert payment["platform_fee_idr"] == 150_000
    assert payment["creator_net_idr"] == 1_350_000
    assert payment["status"] == "pending"
    assert same_key.json()["data"]["id"] == fresh_key.json()["data"]["id"] == payment["id"]
    assert booking_after.json()["data"]["status"] == "awaiting_payment"
    assert INTERNAL_PAYMENT_FIELDS.isdisjoint(payment)


async def test_idempotency_key_validation_and_cross_booking_conflict(
    email_cleanup: list[str],
) -> None:
    key = str(uuid.uuid4())
    with TestClient(create_app()) as client:
        creator_email, profile_id = await make_creator(client, email_cleanup, "Studio Kunci")
        client_email = register(client, email_cleanup, "Klien Kunci")
        first = request_booking(client, profile_id, days=41)
        second = request_booking(client, profile_id, days=42)
        accept_booking(client, first["id"], creator_email)
        login(client, client_email)
        accept_booking(client, second["id"], creator_email)
        login(client, client_email)

        missing = create_payment(client, first["id"])
        malformed = create_payment(client, first["id"], "not-a-canonical-uuid")
        overlong = create_payment(client, first["id"], "a" * 101)
        created = create_payment(client, first["id"], key)
        conflict = create_payment(client, second["id"], key)

    for response in (missing, malformed, overlong):
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_IDEMPOTENCY_KEY"
    assert created.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


async def test_payment_creation_requires_accepted_booking_and_client_owner(
    email_cleanup: list[str],
) -> None:
    with TestClient(create_app()) as client:
        creator_email, profile_id = await make_creator(client, email_cleanup, "Studio Izin Bayar")
        client_email = register(client, email_cleanup, "Klien Pemilik")
        booking = request_booking(client, profile_id)
        before_accept = create_payment(client, booking["id"], str(uuid.uuid4()))
        logout(client)
        register(client, email_cleanup, "Klien Lain")
        stranger = create_payment(client, booking["id"], str(uuid.uuid4()))
        logout(client)
        login(client, creator_email)
        creator = create_payment(client, booking["id"], str(uuid.uuid4()))
        logout(client)
        login(client, client_email)

    assert before_accept.status_code == 409
    assert before_accept.json()["error"]["code"] == "PAYMENT_NOT_ALLOWED"
    assert stranger.status_code == creator.status_code == 404
    assert stranger.json()["error"]["code"] == creator.json()["error"]["code"] == "NOT_FOUND"


async def test_related_users_can_get_payment_but_stranger_cannot(
    email_cleanup: list[str],
) -> None:
    with TestClient(create_app()) as client:
        creator_email, profile_id = await make_creator(client, email_cleanup, "Studio Ringkasan")
        client_email = register(client, email_cleanup, "Klien Ringkasan")
        booking = request_booking(client, profile_id)
        accept_booking(client, booking["id"], creator_email)
        login(client, client_email)
        created = create_payment(client, booking["id"], str(uuid.uuid4()))
        owner_get = client.get(f"/api/v1/bookings/{booking['id']}/payments")
        logout(client)
        login(client, creator_email)
        creator_get = client.get(f"/api/v1/bookings/{booking['id']}/payments")
        logout(client)
        register(client, email_cleanup, "Orang Asing")
        stranger_get = client.get(f"/api/v1/bookings/{booking['id']}/payments")
        missing_get = client.get(f"/api/v1/bookings/{uuid.uuid4()}/payments")

    assert created.status_code == 201
    assert owner_get.status_code == creator_get.status_code == 200
    assert creator_get.json() == owner_get.json()
    assert INTERNAL_PAYMENT_FIELDS.isdisjoint(creator_get.json()["data"])
    assert stranger_get.status_code == missing_get.status_code == 404
    assert stranger_get.json()["error"]["code"] == "NOT_FOUND"


async def test_simulate_paid_is_atomic_and_replay_is_idempotent(
    email_cleanup: list[str],
) -> None:
    with TestClient(create_app()) as client:
        creator_email, profile_id = await make_creator(client, email_cleanup, "Studio Paid")
        client_email = register(client, email_cleanup, "Klien Paid")
        booking = request_booking(client, profile_id)
        accept_booking(client, booking["id"], creator_email)
        login(client, client_email)
        payment = create_payment(client, booking["id"], str(uuid.uuid4())).json()["data"]

        paid = client.post(f"/api/v1/dev/payments/{payment['id']}/simulate-paid")
        replay = client.post(f"/api/v1/dev/payments/{payment['id']}/simulate-paid")
        booking_after = client.get(f"/api/v1/bookings/{booking['id']}")

    assert paid.status_code == replay.status_code == 200
    assert paid.json() == replay.json()
    assert paid.json()["data"]["status"] == "held"
    assert paid.json()["data"]["paid_at"] is not None
    assert paid.json()["data"]["held_at"] is not None
    assert booking_after.json()["data"]["status"] == "confirmed"
    assert await payment_event_count(payment["id"]) == 1


async def test_webhook_replay_failed_path_and_invalid_transitions(
    email_cleanup: list[str],
) -> None:
    with TestClient(create_app()) as client:
        creator_email, profile_id = await make_creator(client, email_cleanup, "Studio Webhook")
        client_email = register(client, email_cleanup, "Klien Webhook")
        first = request_booking(client, profile_id, days=51)
        second = request_booking(client, profile_id, days=52)
        accept_booking(client, first["id"], creator_email)
        login(client, client_email)
        accept_booking(client, second["id"], creator_email)
        login(client, client_email)
        held_payment = create_payment(client, first["id"], str(uuid.uuid4())).json()["data"]
        failed_payment = create_payment(client, second["id"], str(uuid.uuid4())).json()["data"]

        paid_payload = {
            "payment_id": held_payment["id"],
            "event_id": "provider-paid-1",
            "event_type": "paid",
        }
        paid = client.post("/api/v1/payments/webhooks/mock", json=paid_payload)
        replay = client.post("/api/v1/payments/webhooks/mock", json=paid_payload)
        invalid = client.post(
            "/api/v1/payments/webhooks/mock",
            json={**paid_payload, "event_id": "provider-paid-2"},
        )
        failed = client.post(
            "/api/v1/payments/webhooks/mock",
            json={
                "payment_id": failed_payment["id"],
                "event_id": "provider-failed-1",
                "event_type": "failed",
            },
        )
        terminal = client.post(
            "/api/v1/payments/webhooks/mock",
            json={
                "payment_id": failed_payment["id"],
                "event_id": "provider-failed-2",
                "event_type": "paid",
            },
        )

    assert paid.status_code == replay.status_code == 200
    assert paid.json() == replay.json()
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "INVALID_PAYMENT_TRANSITION"
    assert failed.status_code == 200
    assert failed.json()["data"]["status"] == "failed"
    assert terminal.status_code == 409
    assert terminal.json()["error"]["code"] == "PAYMENT_ALREADY_FINAL"
    assert await payment_event_count(held_payment["id"]) == 1


async def test_webhook_validates_provider_and_payload(email_cleanup: list[str]) -> None:
    with TestClient(create_app()) as client:
        unknown = client.post("/api/v1/payments/webhooks/stripe", json={})
        malformed = client.post(
            "/api/v1/payments/webhooks/mock",
            json={"payment_id": "not-canonical", "event_id": "", "event_type": "other"},
        )
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "NOT_FOUND"
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "REQUEST_VALIDATION_FAILED"


async def test_release_authorization_state_and_success(email_cleanup: list[str]) -> None:
    with TestClient(create_app()) as client:
        creator_email, profile_id = await make_creator(client, email_cleanup, "Studio Rilis")
        client_email = register(client, email_cleanup, "Klien Rilis")
        booking = request_booking(client, profile_id)
        accept_booking(client, booking["id"], creator_email)
        login(client, client_email)
        payment = create_payment(client, booking["id"], str(uuid.uuid4())).json()["data"]
        client.post(f"/api/v1/dev/payments/{payment['id']}/simulate-paid")
        client_forbidden = client.post(f"/api/v1/dev/payments/{payment['id']}/simulate-release")
        logout(client)
        register(client, email_cleanup, "Kreator Tak Terkait")
        unrelated = client.post(f"/api/v1/dev/payments/{payment['id']}/simulate-release")
        logout(client)
        login(client, creator_email)
        before_completed = client.post(f"/api/v1/dev/payments/{payment['id']}/simulate-release")
        await set_booking_completed(booking["id"])
        released = client.post(f"/api/v1/dev/payments/{payment['id']}/simulate-release")
        replay = client.post(f"/api/v1/dev/payments/{payment['id']}/simulate-release")

    assert client_forbidden.status_code == unrelated.status_code == 404
    assert before_completed.status_code == 409
    assert before_completed.json()["error"]["code"] == "INVALID_PAYMENT_TRANSITION"
    assert released.status_code == replay.status_code == 200
    assert released.json()["data"]["status"] == "released"
    assert released.json()["data"]["released_at"] is not None
    assert await payment_event_count(payment["id"]) == 2


async def test_production_disables_mock_mutation_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JEPRET_ENVIRONMENT", "production")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            dev = client.post(f"/api/v1/dev/payments/{uuid.uuid4()}/simulate-paid")
            webhook = client.post(
                "/api/v1/payments/webhooks/mock",
                json={
                    "payment_id": str(uuid.uuid4()),
                    "event_id": "production-event",
                    "event_type": "paid",
                },
            )
    finally:
        get_settings.cache_clear()
    assert dev.status_code == webhook.status_code == 404
    assert (
        dev.json()["error"]["code"] == webhook.json()["error"]["code"] == ("DEV_ENDPOINT_DISABLED")
    )


async def test_concurrent_create_produces_one_payment(email_cleanup: list[str]) -> None:
    with TestClient(create_app()) as client:
        creator_email, profile_id = await make_creator(client, email_cleanup, "Studio Konkuren")
        client_email = register(client, email_cleanup, "Klien Konkuren")
        booking = request_booking(client, profile_id)
        accept_booking(client, booking["id"], creator_email)

    from app.services.payments import create_payment as service_create_payment

    engine = create_async_engine(get_settings().database_url, poolclass=None)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def worker(key: str) -> str:
        async with factory() as session:
            user = await session.scalar(select(User).where(User.email == client_email))
            assert user is not None
            payment, _ = await service_create_payment(
                session,
                booking_id=uuid.UUID(booking["id"]),
                user=user,
                idempotency_key=key,
            )
            return str(payment.id)

    try:
        payment_ids = await asyncio.gather(
            worker(str(uuid.uuid4())),
            worker(str(uuid.uuid4())),
        )
        async with factory() as session:
            count = await session.scalar(
                select(func.count(Payment.id)).where(Payment.booking_id == uuid.UUID(booking["id"]))
            )
    finally:
        await engine.dispose()

    assert payment_ids[0] == payment_ids[1]
    assert count == 1
