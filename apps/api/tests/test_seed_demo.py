import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.models import Booking, CreatorProfile, User
from scripts import seed_demo

pytestmark = pytest.mark.integration


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

            confirmed = await db.scalar(
                select(Booking)
                .options(selectinload(Booking.payment))
                .where(Booking.notes == "Booking demo [confirmed-held].")
            )
            assert confirmed is not None and confirmed.payment is not None
            confirmed.status = "requested"
            confirmed.payment.status = "pending"
            confirmed.payment.paid_at = None
            confirmed.payment.held_at = None

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
                        )
                    )
                ).all()
            )
            assert len(bookings) == 5
            assert all(booking.notes != "Booking demo." for booking in bookings)

            by_note = {booking.notes: booking for booking in bookings}
            reconciled = by_note["Booking demo [confirmed-held]."]
            assert reconciled.status == "confirmed"
            assert reconciled.payment is not None
            assert reconciled.payment.status == "held"
            assert reconciled.payment.created_at <= reconciled.payment.paid_at
            assert reconciled.payment.paid_at <= reconciled.payment.held_at
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
            assert released.created_at <= released.paid_at <= released.held_at
            assert released.held_at <= released.released_at

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
