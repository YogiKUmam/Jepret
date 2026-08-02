import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.models import Booking, CreatorProfile, Payment, PaymentEvent, User
from scripts import seed_demo

pytestmark = pytest.mark.integration

EXPECTED_EVENT_DATES = {
    "Booking demo [requested].": date(2026, 9, 1),
    "Booking demo [accepted].": date(2026, 9, 16),
    "Booking demo [awaiting-payment].": date(2026, 10, 1),
    "Booking demo [confirmed-held].": date(2026, 10, 16),
    "Booking demo [completed-released].": date(2026, 7, 13),
}
EXPECTED_BOOKING_TIMESTAMP = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)


class FutureClock(datetime):
    @classmethod
    def now(cls, tz: object = None) -> datetime:
        del tz
        return datetime(2042, 1, 1, tzinfo=UTC)


async def test_booking_seed_is_time_independent_and_reconciles_partial_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_email = f"seed-client-{uuid.uuid4().hex}@jepret.local"
    creator_email = f"seed-creator-{uuid.uuid4().hex}@jepret.local"
    monkeypatch.setattr(seed_demo, "DEMO_CLIENT_EMAIL", client_email)
    monkeypatch.setattr(seed_demo, "DEMO_CREATOR_EMAIL", creator_email)
    engine = create_async_engine(get_settings().database_url, poolclass=None)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as db:
            client = User(
                email=client_email,
                password_hash="seed-test",
                full_name="Klien Demo",
            )
            creator_user = User(
                email=creator_email,
                password_hash="seed-test",
                full_name="Kreator Demo",
            )
            profile = CreatorProfile(
                user=creator_user,
                display_name="Studio Cahaya",
                city="Bandung",
                bio="Seed test.",
                specialty="wedding",
                starting_price_idr=1_500_000,
                status="approved",
            )
            db.add_all([client, creator_user, profile])
            await db.commit()

            await seed_demo._seed_bookings(db)
            await db.commit()

            initial_bookings = list(
                (
                    await db.scalars(
                        select(Booking).where(
                            Booking.client_id == client.id,
                            Booking.creator_profile_id == profile.id,
                            Booking.notes.in_(EXPECTED_EVENT_DATES),
                        )
                    )
                ).all()
            )
            assert {
                booking.notes: booking.event_date for booking in initial_bookings
            } == EXPECTED_EVENT_DATES

            confirmed = await db.scalar(
                select(Booking)
                .options(selectinload(Booking.payment))
                .where(
                    Booking.client_id == client.id,
                    Booking.creator_profile_id == profile.id,
                    Booking.notes == "Booking demo [confirmed-held].",
                )
            )
            assert confirmed is not None and confirmed.payment is not None
            confirmed.status = "requested"
            confirmed.payment.status = "pending"
            confirmed.payment.paid_at = None
            confirmed.payment.held_at = None

            pending = await db.scalar(
                select(Booking)
                .options(selectinload(Booking.payment))
                .where(
                    Booking.client_id == client.id,
                    Booking.creator_profile_id == profile.id,
                    Booking.notes == "Booking demo [awaiting-payment].",
                )
            )
            assert pending is not None and pending.payment is not None
            db.add(
                PaymentEvent(
                    payment_id=pending.payment.id,
                    provider="mock",
                    provider_event_id=f"stale-seed-{pending.payment.id}",
                    event_type="paid",
                    processed_at=seed_demo.PAYMENT_PAID_AT,
                )
            )

            unrelated = Booking(
                client_id=client.id,
                creator_profile_id=profile.id,
                event_date=date(2042, 2, 1),
                event_city="Bandung",
                notes="Booking buatan pengguna.",
                status="completed",
                quoted_price_idr=1_500_000,
                payment=None,
            )
            db.add(unrelated)
            await db.flush()
            unrelated_payment = Payment(
                booking_id=unrelated.id,
                provider="mock",
                provider_reference=f"user-{unrelated.id}",
                idempotency_key=f"user-{unrelated.id}",
                amount_idr=1_500_000,
                platform_fee_idr=150_000,
                creator_net_idr=1_350_000,
                status="released",
            )
            db.add(unrelated_payment)
            await db.flush()
            db.add(
                PaymentEvent(
                    payment_id=unrelated_payment.id,
                    provider="mock",
                    provider_event_id=f"user-event-{unrelated_payment.id}",
                    event_type="released",
                    processed_at=seed_demo.PAYMENT_RELEASED_AT,
                )
            )

            db.add(
                Booking(
                    client_id=client.id,
                    creator_profile_id=profile.id,
                    event_date=date(2041, 12, 31),
                    event_city="Bandung",
                    notes="Booking demo.",
                    status="requested",
                    quoted_price_idr=1_500_000,
                )
            )
            await db.commit()

            monkeypatch.setattr(seed_demo, "datetime", FutureClock)
            await seed_demo._seed_bookings(db)
            await db.commit()

            bookings = list(
                (
                    await db.scalars(
                        select(Booking)
                        .options(selectinload(Booking.payment))
                        .where(
                            Booking.client_id == client.id,
                            Booking.creator_profile_id == profile.id,
                            Booking.notes.in_(EXPECTED_EVENT_DATES),
                        )
                    )
                ).all()
            )
            assert len(bookings) == 5
            assert {
                booking.notes: booking.event_date for booking in bookings
            } == EXPECTED_EVENT_DATES
            legacy_count = await db.scalar(
                select(func.count(Booking.id)).where(
                    Booking.client_id == client.id,
                    Booking.creator_profile_id == profile.id,
                    Booking.notes == "Booking demo.",
                )
            )
            assert legacy_count == 0

            by_note = {booking.notes: booking for booking in bookings}
            for booking in bookings:
                assert booking.created_at == EXPECTED_BOOKING_TIMESTAMP
                assert booking.updated_at == EXPECTED_BOOKING_TIMESTAMP
                if booking.payment is not None:
                    payment = booking.payment
                    assert booking.created_at <= payment.created_at
                    if payment.paid_at is not None:
                        assert payment.created_at <= payment.paid_at
                    if payment.held_at is not None:
                        assert payment.paid_at is not None
                        assert payment.paid_at <= payment.held_at
                    if payment.released_at is not None:
                        assert payment.held_at is not None
                        assert payment.held_at <= payment.released_at

            seed_payment_ids = [
                booking.payment.id for booking in bookings if booking.payment is not None
            ]
            seed_event_count = await db.scalar(
                select(func.count(PaymentEvent.id)).where(
                    PaymentEvent.payment_id.in_(seed_payment_ids)
                )
            )
            unrelated_event_count = await db.scalar(
                select(func.count(PaymentEvent.id)).where(
                    PaymentEvent.payment_id == unrelated_payment.id
                )
            )
            assert seed_event_count == 0
            assert unrelated_event_count == 1

            reconciled = by_note["Booking demo [confirmed-held]."]
            assert reconciled.status == "confirmed"
            assert reconciled.payment is not None
            assert reconciled.payment.status == "held"
            assert reconciled.payment.released_at is None

            payment_pairs = {
                booking.notes: booking.payment.status if booking.payment else None
                for booking in bookings
            }
            assert payment_pairs == {
                "Booking demo [requested].": None,
                "Booking demo [accepted].": None,
                "Booking demo [awaiting-payment].": "pending",
                "Booking demo [confirmed-held].": "held",
                "Booking demo [completed-released].": "released",
            }

            released = by_note["Booking demo [completed-released]."].payment
            assert released is not None

            pending = by_note["Booking demo [awaiting-payment]."].payment
            assert pending is not None
            assert pending.paid_at is pending.held_at is pending.released_at is None

    finally:
        async with factory() as db:
            users = list(
                (
                    await db.scalars(
                        select(User).where(User.email.in_([client_email, creator_email]))
                    )
                ).all()
            )
            for user in users:
                await db.delete(user)
            await db.commit()
        await engine.dispose()
