import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.errors import DomainError
from app.db.models import Booking, Message, Payment, PaymentEvent, User
from app.integrations.payments import MockPaymentProvider
from app.integrations.payments import PaymentEvent as ProviderPaymentEvent
from app.main import create_app
from app.realtime import ConnectionHub
from app.services import bookings as booking_service
from app.services import payments as payment_service
from tests.conftest import fresh_connection, unique_email

pytestmark = pytest.mark.integration

PASSWORD = "sandi-aman-123"


@pytest.fixture(autouse=True)
async def cleanup_lifecycle_messages(email_cleanup: list[str]):
    yield
    if email_cleanup:
        async with fresh_connection() as connection:
            await connection.execute(
                text(
                    "DELETE FROM deliverables WHERE uploaded_by_user_id IN "
                    "(SELECT id FROM users WHERE email = ANY(:emails))"
                ),
                {"emails": email_cleanup},
            )
            await connection.execute(
                text(
                    "DELETE FROM messages WHERE sender_user_id IN "
                    "(SELECT id FROM users WHERE email = ANY(:emails))"
                ),
                {"emails": email_cleanup},
            )


class RecordingReleaseProvider(MockPaymentProvider):
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.release_calls = 0

    async def release_payment(self, payment_id: uuid.UUID) -> ProviderPaymentEvent:
        self.release_calls += 1
        if self.fail:
            raise RuntimeError("provider release failed")
        return await super().release_payment(payment_id)


class WrongReleaseProvider(RecordingReleaseProvider):
    async def release_payment(self, payment_id: uuid.UUID) -> ProviderPaymentEvent:
        self.release_calls += 1
        return ProviderPaymentEvent(
            provider_event_id=f"mock-refunded-{payment_id}", event_type="refunded"
        )


class BlockingReleaseProvider(RecordingReleaseProvider):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def release_payment(self, payment_id: uuid.UUID) -> ProviderPaymentEvent:
        self.release_calls += 1
        self.started.set()
        await self.release.wait()
        return await MockPaymentProvider.release_payment(self, payment_id)


class RecordingHub(ConnectionHub):
    def __init__(self) -> None:
        self.events: list[tuple[uuid.UUID, dict[str, object]]] = []

    async def broadcast(self, conversation_id: uuid.UUID, event: dict[str, object]) -> None:
        self.events.append((conversation_id, event))

    async def close(self) -> None:
        return None


class ConstraintViolation(Exception):
    def __init__(self, constraint_name: str) -> None:
        super().__init__("database detail must remain private")
        self.constraint_name = constraint_name


class ConflictOnceSession(AsyncSession):
    conflict_raised = False
    committed_event_type = "released"

    async def commit(self) -> None:
        booking = next(
            (
                value
                for value in self.identity_map.values()
                if isinstance(value, Booking) and value.status == "completed"
            ),
            None,
        )
        if booking is not None and not type(self).conflict_raised:
            type(self).conflict_raised = True
            payment = next(
                value
                for value in self.identity_map.values()
                if isinstance(value, Payment) and value.booking_id == booking.id
            )
            event = await self.scalar(
                select(PaymentEvent).where(
                    PaymentEvent.payment_id == payment.id,
                    PaymentEvent.event_type == "released",
                )
            )
            message = await self.scalar(
                select(Message).where(
                    Message.sender_user_id == booking.client_id,
                    Message.client_message_id
                    == uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"jepret:booking:{booking.id}:lifecycle:completed",
                    ),
                )
            )
            assert event is not None and message is not None
            committed_values = {
                "booking_id": booking.id,
                "completed_at": booking.completed_at,
                "payment_id": payment.id,
                "released_at": payment.released_at,
                "event_id": event.id,
                "provider": event.provider,
                "provider_event_id": event.provider_event_id,
                "event_type": type(self).committed_event_type,
                "message_id": message.id,
                "conversation_id": message.conversation_id,
                "sender_user_id": message.sender_user_id,
                "client_message_id": message.client_message_id,
                "message_type": message.message_type,
                "body": message.body,
            }
            await super().rollback()
            async with fresh_connection() as connection:
                await connection.execute(
                    text(
                        "UPDATE bookings SET status='completed', completed_at=:completed_at "
                        "WHERE id=:booking_id"
                    ),
                    committed_values,
                )
                await connection.execute(
                    text(
                        "UPDATE payments SET status='released', released_at=:released_at "
                        "WHERE id=:payment_id"
                    ),
                    committed_values,
                )
                await connection.execute(
                    text(
                        "INSERT INTO payment_events "
                        "(id, payment_id, provider, provider_event_id, event_type) VALUES "
                        "(:event_id, :payment_id, :provider, :provider_event_id, :event_type)"
                    ),
                    committed_values,
                )
                await connection.execute(
                    text(
                        "INSERT INTO messages "
                        "(id, conversation_id, sender_user_id, client_message_id, "
                        "message_type, body) VALUES "
                        "(:message_id, :conversation_id, :sender_user_id, :client_message_id, "
                        ":message_type, :body)"
                    ),
                    committed_values,
                )
            raise IntegrityError(
                "simulated completion conflict",
                {},
                ConstraintViolation("uq_payment_event_provider_id"),
            )
        await super().commit()


class WrongEventCommittedRaceSession(ConflictOnceSession):
    committed_event_type = "paid"


class UnknownConflictSession(AsyncSession):
    conflict_raised = False

    async def commit(self) -> None:
        completed = any(
            isinstance(value, Booking) and value.status == "completed"
            for value in self.identity_map.values()
        )
        if completed and not type(self).conflict_raised:
            type(self).conflict_raised = True
            raise IntegrityError(
                "simulated completion conflict",
                {},
                ConstraintViolation("fk_unrelated_integrity_failure"),
            )
        await super().commit()


def register(client: TestClient, email_cleanup: list[str], name: str) -> str:
    email = unique_email("life")
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
            text("UPDATE creator_profiles SET status='approved', reviewed_at=now() WHERE id=:id"),
            {"id": profile_id},
        )


async def make_creator(client: TestClient, email_cleanup: list[str], name: str) -> tuple[str, str]:
    email = register(client, email_cleanup, name)
    response = client.put(
        "/api/v1/profiles/me/creator",
        json={
            "display_name": name,
            "city": "Bandung",
            "bio": "Uji lifecycle.",
            "specialty": "wedding",
            "starting_price_idr": 1_500_000,
        },
    )
    assert response.status_code == 200, response.text
    profile_id = response.json()["data"]["id"]
    await approve_profile(profile_id)
    logout(client)
    return email, profile_id


async def held_workspace(
    client: TestClient,
    email_cleanup: list[str],
    *,
    name: str = "Studio Lifecycle",
    create_conversation: bool = True,
) -> tuple[str, str, str, str]:
    creator_email, profile_id = await make_creator(client, email_cleanup, name)
    client_email = register(client, email_cleanup, f"Klien {name}")
    booking = client.post(
        "/api/v1/bookings",
        json={
            "creator_id": profile_id,
            "event_date": (datetime.now(UTC).date() + timedelta(days=80)).isoformat(),
            "event_city": "Bandung",
            "notes": "Dokumentasi acara.",
        },
    ).json()["data"]
    logout(client)
    login(client, creator_email)
    assert client.post(f"/api/v1/bookings/{booking['id']}/accept").status_code == 200
    logout(client)
    login(client, client_email)
    payment = client.post(
        f"/api/v1/bookings/{booking['id']}/payments",
        headers={"Idempotency-Key": str(uuid.uuid4())},
    ).json()["data"]
    assert client.post(f"/api/v1/dev/payments/{payment['id']}/simulate-paid").status_code == 200
    if create_conversation:
        conversation = client.get(f"/api/v1/bookings/{booking['id']}/conversation").json()["data"]
        assert conversation is not None
    return booking["id"], payment["id"], client_email, creator_email


def add_deliverable(client: TestClient, booking_id: str) -> None:
    response = client.post(
        f"/api/v1/bookings/{booking_id}/deliverables",
        json={
            "source_type": "external_link",
            "title": "Galeri final",
            "external_url": "https://example.com/gallery/final",
        },
    )
    assert response.status_code == 201, response.text


async def database_state(booking_id: str) -> tuple[str, str, int, int]:
    async with fresh_connection() as connection:
        booking_status = await connection.scalar(
            select(Booking.status).where(Booking.id == uuid.UUID(booking_id))
        )
        payment_status = await connection.scalar(
            select(Payment.status).where(Payment.booking_id == uuid.UUID(booking_id))
        )
        release_events = await connection.scalar(
            select(func.count(PaymentEvent.id)).where(
                PaymentEvent.payment_id
                == select(Payment.id)
                .where(Payment.booking_id == uuid.UUID(booking_id))
                .scalar_subquery(),
                PaymentEvent.event_type == "released",
            )
        )
        system_messages = await connection.scalar(
            text(
                "SELECT count(*) FROM messages m JOIN conversations c "
                "ON c.id=m.conversation_id WHERE c.booking_id=:booking_id "
                "AND m.message_type='system'"
            ),
            {"booking_id": booking_id},
        )
    return (
        str(booking_status),
        str(payment_status),
        int(release_events or 0),
        int(system_messages or 0),
    )


async def wait_for_pg_blocker(*, waiter_pid: int, holder_pid: int) -> None:
    async with asyncio.timeout(5):
        while True:
            async with fresh_connection() as connection:
                blockers = await connection.scalar(
                    text("SELECT pg_blocking_pids(:waiter_pid)"), {"waiter_pid": waiter_pid}
                )
            if blockers is not None and holder_pid in blockers:
                return


async def test_creator_starts_delivers_and_client_accepts_once(
    email_cleanup: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = RecordingReleaseProvider()
    monkeypatch.setattr(payment_service, "PROVIDER", provider)
    app = create_app()
    hub = RecordingHub()
    app.state.connection_hub = hub
    with TestClient(app) as client:
        booking_id, _, client_email, creator_email = await held_workspace(client, email_cleanup)
        logout(client)
        login(client, creator_email)
        started = client.post(f"/api/v1/bookings/{booking_id}/start")
        add_deliverable(client, booking_id)
        delivered = client.post(f"/api/v1/bookings/{booking_id}/deliver")
        logout(client)
        login(client, client_email)
        completed = client.post(f"/api/v1/bookings/{booking_id}/complete")
        replay = client.post(f"/api/v1/bookings/{booking_id}/complete")

    assert started.status_code == delivered.status_code == 200
    assert started.json()["data"]["status"] == "in_progress"
    assert started.json()["data"]["started_at"] is not None
    assert delivered.json()["data"]["status"] == "delivered"
    assert delivered.json()["data"]["delivered_at"] is not None
    assert completed.status_code == replay.status_code == 200
    assert completed.json()["data"]["status"] == replay.json()["data"]["status"] == "completed"
    assert completed.json()["data"]["completed_at"] is not None
    assert await database_state(booking_id) == ("completed", "released", 1, 3)
    assert provider.release_calls == 1
    message_events = [event for _, event in hub.events if event["type"] == "message.created"]
    message_data = [event["data"] for event in message_events]
    assert [data["body"] for data in message_data if isinstance(data, dict)] == [
        "Kreator memulai pengerjaan booking.",
        "Kreator mengirim hasil pekerjaan.",
        "Klien menerima hasil pekerjaan dan menyelesaikan booking.",
    ]
    assert all(isinstance(data, dict) and data["message_type"] == "system" for data in message_data)
    booking_events = [event for _, event in hub.events if event["type"] == "booking.updated"]
    assert [
        event["data"]["status"] for event in booking_events if isinstance(event["data"], dict)
    ] == ["in_progress", "delivered", "completed"]


async def test_start_does_not_create_a_conversation_for_a_lifecycle_message(
    email_cleanup: list[str],
) -> None:
    with TestClient(create_app()) as client:
        booking_id, _, _, creator_email = await held_workspace(
            client,
            email_cleanup,
            name="Studio Tanpa Percakapan",
            create_conversation=False,
        )
        logout(client)
        login(client, creator_email)
        started = client.post(f"/api/v1/bookings/{booking_id}/start")
    async with fresh_connection() as connection:
        conversation_count = await connection.scalar(
            text("SELECT count(*) FROM conversations WHERE booking_id=:id"), {"id": booking_id}
        )
        message_count = await connection.scalar(
            text(
                "SELECT count(*) FROM messages m JOIN conversations c "
                "ON c.id=m.conversation_id WHERE c.booking_id=:id"
            ),
            {"id": booking_id},
        )
    assert started.status_code == 200
    assert conversation_count == message_count == 0


async def test_lifecycle_enforces_roles_payment_deliverable_and_cancellation(
    email_cleanup: list[str],
) -> None:
    with TestClient(create_app()) as client:
        booking_id, _, client_email, creator_email = await held_workspace(client, email_cleanup)
        client_start = client.post(f"/api/v1/bookings/{booking_id}/start")
        client_complete_early = client.post(f"/api/v1/bookings/{booking_id}/complete")
        logout(client)
        login(client, creator_email)
        started = client.post(f"/api/v1/bookings/{booking_id}/start")
        stale_start = client.post(f"/api/v1/bookings/{booking_id}/start")
        no_deliverable = client.post(f"/api/v1/bookings/{booking_id}/deliver")
        blocked_cancel = client.post(f"/api/v1/bookings/{booking_id}/cancel")
        add_deliverable(client, booking_id)
        delivered = client.post(f"/api/v1/bookings/{booking_id}/deliver")
        stale_deliver = client.post(f"/api/v1/bookings/{booking_id}/deliver")
        creator_complete = client.post(f"/api/v1/bookings/{booking_id}/complete")
        logout(client)
        login(client, client_email)
        client_deliver = client.post(f"/api/v1/bookings/{booking_id}/deliver")

    assert (
        client_start.status_code
        == creator_complete.status_code
        == client_deliver.status_code
        == 404
    )
    assert client_complete_early.status_code == 409
    assert started.status_code == delivered.status_code == 200
    assert stale_start.status_code == stale_deliver.status_code == 409
    assert no_deliverable.status_code == 409
    assert no_deliverable.json()["error"]["code"] == "DELIVERABLE_REQUIRED"
    assert blocked_cancel.status_code == 409


async def test_active_date_remains_blocked_during_work_and_delivery(
    email_cleanup: list[str],
) -> None:
    with TestClient(create_app()) as client:
        booking_id, _, _, creator_email = await held_workspace(
            client, email_cleanup, name="Studio Tanggal Aktif"
        )
        async with fresh_connection() as connection:
            profile_id = await connection.scalar(
                text("SELECT creator_profile_id FROM bookings WHERE id=:id"), {"id": booking_id}
            )
            event_date = await connection.scalar(
                text("SELECT event_date FROM bookings WHERE id=:id"), {"id": booking_id}
            )
        logout(client)
        second_client = register(client, email_cleanup, "Klien Tanggal Kedua")
        second = client.post(
            "/api/v1/bookings",
            json={
                "creator_id": str(profile_id),
                "event_date": str(event_date),
                "event_city": "Bandung",
            },
        ).json()["data"]
        logout(client)
        login(client, creator_email)
        assert client.post(f"/api/v1/bookings/{booking_id}/start").status_code == 200
        clash_in_progress = client.post(f"/api/v1/bookings/{second['id']}/accept")
        add_deliverable(client, booking_id)
        assert client.post(f"/api/v1/bookings/{booking_id}/deliver").status_code == 200
        clash_delivered = client.post(f"/api/v1/bookings/{second['id']}/accept")
    assert clash_in_progress.status_code == clash_delivered.status_code == 409
    assert clash_in_progress.json()["error"]["code"] == "DATE_UNAVAILABLE"
    assert clash_delivered.json()["error"]["code"] == "DATE_UNAVAILABLE"
    assert second_client != creator_email


async def test_start_requires_a_held_payment(email_cleanup: list[str]) -> None:
    with TestClient(create_app()) as client:
        creator_email, profile_id = await make_creator(client, email_cleanup, "Studio Tanpa Dana")
        register(client, email_cleanup, "Klien Tanpa Dana")
        booking = client.post(
            "/api/v1/bookings",
            json={
                "creator_id": profile_id,
                "event_date": (datetime.now(UTC).date() + timedelta(days=81)).isoformat(),
                "event_city": "Bandung",
            },
        ).json()["data"]
        logout(client)
        login(client, creator_email)
        client.post(f"/api/v1/bookings/{booking['id']}/accept")
        async with fresh_connection() as connection:
            await connection.execute(
                text("UPDATE bookings SET status='confirmed' WHERE id=:id"),
                {"id": booking["id"]},
            )
        missing = client.post(f"/api/v1/bookings/{booking['id']}/start")
    async with fresh_connection() as connection:
        state = (
            await connection.execute(
                text(
                    "SELECT b.status, b.started_at, "
                    "(SELECT count(*) FROM payments p WHERE p.booking_id=b.id), "
                    "(SELECT count(*) FROM conversations c WHERE c.booking_id=b.id), "
                    "(SELECT count(*) FROM payment_events pe JOIN payments p ON p.id=pe.payment_id "
                    "WHERE p.booking_id=b.id) FROM bookings b WHERE b.id=:id"
                ),
                {"id": booking["id"]},
            )
        ).one()
    assert missing.status_code == 409
    assert missing.json()["error"]["code"] == "INVALID_PAYMENT_TRANSITION"
    assert state == ("confirmed", None, 0, 0, 0)


async def test_provider_failure_rolls_back_client_acceptance(
    email_cleanup: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = RecordingReleaseProvider(fail=True)
    monkeypatch.setattr(payment_service, "PROVIDER", provider)
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        booking_id, _, client_email, creator_email = await held_workspace(client, email_cleanup)
        logout(client)
        login(client, creator_email)
        client.post(f"/api/v1/bookings/{booking_id}/start")
        add_deliverable(client, booking_id)
        client.post(f"/api/v1/bookings/{booking_id}/deliver")
        logout(client)
        login(client, client_email)
        failed = client.post(f"/api/v1/bookings/{booking_id}/complete")
    assert failed.status_code == 500
    assert await database_state(booking_id) == ("delivered", "held", 0, 2)
    assert provider.release_calls == 1


async def test_completion_rejects_non_release_provider_event_without_mutation(
    email_cleanup: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = WrongReleaseProvider()
    monkeypatch.setattr(payment_service, "PROVIDER", provider)
    with TestClient(create_app()) as client:
        booking_id, _, client_email, creator_email = await held_workspace(client, email_cleanup)
        logout(client)
        login(client, creator_email)
        client.post(f"/api/v1/bookings/{booking_id}/start")
        add_deliverable(client, booking_id)
        client.post(f"/api/v1/bookings/{booking_id}/deliver")
        logout(client)
        login(client, client_email)
        rejected = client.post(f"/api/v1/bookings/{booking_id}/complete")
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "INVALID_PAYMENT_TRANSITION"
    assert await database_state(booking_id) == ("delivered", "held", 0, 2)
    assert provider.release_calls == 1


async def test_completion_rejects_same_payment_event_id_with_wrong_event_semantics(
    email_cleanup: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = RecordingReleaseProvider()
    monkeypatch.setattr(payment_service, "PROVIDER", provider)
    with TestClient(create_app()) as client:
        booking_id, payment_id, client_email, creator_email = await held_workspace(
            client, email_cleanup
        )
        logout(client)
        login(client, creator_email)
        client.post(f"/api/v1/bookings/{booking_id}/start")
        add_deliverable(client, booking_id)
        client.post(f"/api/v1/bookings/{booking_id}/deliver")
        async with fresh_connection() as connection:
            await connection.execute(
                text(
                    "INSERT INTO payment_events "
                    "(id, payment_id, provider, provider_event_id, event_type) "
                    "VALUES (:id, :payment_id, 'mock', :provider_event_id, 'paid')"
                ),
                {
                    "id": uuid.uuid4(),
                    "payment_id": payment_id,
                    "provider_event_id": f"mock-released-{payment_id}",
                },
            )
        logout(client)
        login(client, client_email)
        rejected = client.post(f"/api/v1/bookings/{booking_id}/complete")
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "INVALID_PAYMENT_TRANSITION"
    assert await database_state(booking_id) == ("delivered", "held", 0, 2)
    assert provider.release_calls == 1


async def test_provider_success_survives_one_local_commit_conflict_without_second_release(
    email_cleanup: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = RecordingReleaseProvider()
    monkeypatch.setattr(payment_service, "PROVIDER", provider)
    with TestClient(create_app()) as client:
        booking_id, _, client_email, creator_email = await held_workspace(client, email_cleanup)
        logout(client)
        login(client, creator_email)
        client.post(f"/api/v1/bookings/{booking_id}/start")
        add_deliverable(client, booking_id)
        client.post(f"/api/v1/bookings/{booking_id}/deliver")

    engine = create_async_engine(get_settings().database_url)
    ConflictOnceSession.conflict_raised = False
    factory = async_sessionmaker(engine, class_=ConflictOnceSession, expire_on_commit=False)
    try:
        async with factory() as db:
            user = await db.scalar(select(User).where(User.email == client_email))
            assert user is not None
            mutation = await booking_service.complete_booking(
                db, booking_id=uuid.UUID(booking_id), user=user
            )
            assert mutation.booking.status == "completed"
            assert mutation.changed is False
    finally:
        await engine.dispose()
    assert ConflictOnceSession.conflict_raised is True
    assert provider.release_calls == 1
    assert await database_state(booking_id) == ("completed", "released", 1, 3)


async def test_commit_race_rejects_committed_event_with_wrong_release_semantics(
    email_cleanup: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = RecordingReleaseProvider()
    monkeypatch.setattr(payment_service, "PROVIDER", provider)
    with TestClient(create_app()) as client:
        booking_id, _, client_email, creator_email = await held_workspace(client, email_cleanup)
        logout(client)
        login(client, creator_email)
        client.post(f"/api/v1/bookings/{booking_id}/start")
        add_deliverable(client, booking_id)
        client.post(f"/api/v1/bookings/{booking_id}/deliver")

    engine = create_async_engine(get_settings().database_url)
    WrongEventCommittedRaceSession.conflict_raised = False
    factory = async_sessionmaker(
        engine, class_=WrongEventCommittedRaceSession, expire_on_commit=False
    )
    try:
        async with factory() as db:
            user = await db.scalar(select(User).where(User.email == client_email))
            assert user is not None
            with pytest.raises(DomainError) as exc_info:
                await booking_service.complete_booking(
                    db, booking_id=uuid.UUID(booking_id), user=user
                )
    finally:
        await engine.dispose()
    assert exc_info.value.code == "INVALID_PAYMENT_TRANSITION"
    assert provider.release_calls == 1
    assert await database_state(booking_id) == ("completed", "released", 0, 3)


async def test_unknown_integrity_failure_is_not_misreported_as_completion(
    email_cleanup: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = RecordingReleaseProvider()
    monkeypatch.setattr(payment_service, "PROVIDER", provider)
    with TestClient(create_app()) as client:
        booking_id, _, client_email, creator_email = await held_workspace(client, email_cleanup)
        logout(client)
        login(client, creator_email)
        client.post(f"/api/v1/bookings/{booking_id}/start")
        add_deliverable(client, booking_id)
        client.post(f"/api/v1/bookings/{booking_id}/deliver")

    engine = create_async_engine(get_settings().database_url)
    UnknownConflictSession.conflict_raised = False
    factory = async_sessionmaker(engine, class_=UnknownConflictSession, expire_on_commit=False)
    try:
        async with factory() as db:
            user = await db.scalar(select(User).where(User.email == client_email))
            assert user is not None
            with pytest.raises(IntegrityError):
                await booking_service.complete_booking(
                    db, booking_id=uuid.UUID(booking_id), user=user
                )
    finally:
        await engine.dispose()
    assert UnknownConflictSession.conflict_raised is True
    assert provider.release_calls == 1
    assert await database_state(booking_id) == ("delivered", "held", 0, 2)


async def test_concurrent_completion_serializes_to_one_provider_release(
    email_cleanup: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = BlockingReleaseProvider()
    monkeypatch.setattr(payment_service, "PROVIDER", provider)
    with TestClient(create_app()) as client:
        booking_id, _, client_email, creator_email = await held_workspace(client, email_cleanup)
        logout(client)
        login(client, creator_email)
        client.post(f"/api/v1/bookings/{booking_id}/start")
        add_deliverable(client, booking_id)
        client.post(f"/api/v1/bookings/{booking_id}/deliver")

    engine = create_async_engine(get_settings().database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    holder_task: asyncio.Task[tuple[str, bool]] | None = None
    waiter_task: asyncio.Task[tuple[str, bool]] | None = None
    try:
        async with factory() as holder, factory() as waiter:
            holder_user = await holder.scalar(select(User).where(User.email == client_email))
            waiter_user = await waiter.scalar(select(User).where(User.email == client_email))
            holder_pid = await holder.scalar(text("SELECT pg_backend_pid()"))
            waiter_pid = await waiter.scalar(text("SELECT pg_backend_pid()"))
            assert holder_user is not None and waiter_user is not None
            assert holder_pid is not None and waiter_pid is not None
            assert holder_pid != waiter_pid

            async def complete(db: AsyncSession, user: User) -> tuple[str, bool]:
                result = await booking_service.complete_booking(
                    db, booking_id=uuid.UUID(booking_id), user=user
                )
                return result.booking.status, result.changed

            holder_task = asyncio.create_task(complete(holder, holder_user))
            await asyncio.wait_for(provider.started.wait(), timeout=5)
            waiter_task = asyncio.create_task(complete(waiter, waiter_user))
            await wait_for_pg_blocker(waiter_pid=waiter_pid, holder_pid=holder_pid)
            assert waiter_task.done() is False
            provider.release.set()
            outcomes = await asyncio.wait_for(asyncio.gather(holder_task, waiter_task), timeout=10)
    finally:
        provider.release.set()
        pending = [
            task for task in (holder_task, waiter_task) if task is not None and not task.done()
        ]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        await engine.dispose()
    assert outcomes == [("completed", True), ("completed", False)]
    assert provider.release_calls == 1
    assert await database_state(booking_id) == ("completed", "released", 1, 3)
