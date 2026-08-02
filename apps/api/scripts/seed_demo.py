"""Seed idempotent demo accounts for local development only."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.security import hash_password
from app.db.models import Booking, CreatorProfile, Payment, User
from app.db.session import dispose_engine, get_engine

BASE_REVIEWED_AT = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
PAYMENT_CREATED_AT = BASE_REVIEWED_AT + timedelta(hours=1)
PAYMENT_PAID_AT = BASE_REVIEWED_AT + timedelta(days=1)
PAYMENT_HELD_AT = PAYMENT_PAID_AT + timedelta(minutes=5)
PAYMENT_RELEASED_AT = BASE_REVIEWED_AT + timedelta(days=2)
LEGACY_BOOKING_NOTE = "Booking demo."
DEMO_CLIENT_EMAIL = "klien@jepret.local"
DEMO_CREATOR_EMAIL = "kreator@jepret.local"

DEMO_USERS = [
    {
        "email": "admin@jepret.local",
        "password": "admin12345",
        "full_name": "Admin Jepret",
        "is_admin": True,
    },
    {
        "email": DEMO_CLIENT_EMAIL,
        "password": "klien12345",
        "full_name": "Klien Demo",
        "is_admin": False,
    },
]

# reviewed_at berjenjang: indeks lebih besar = di-approve lebih baru = tampil lebih dulu.
DEMO_CREATORS: list[dict[str, Any]] = [
    {
        "email": DEMO_CREATOR_EMAIL,
        "password": "kreator12345",
        "full_name": "Kreator Demo",
        "profile": {
            "display_name": "Studio Cahaya",
            "city": "Bandung",
            "bio": "Fotografer dan videografer pernikahan di Bandung.",
            "specialty": "wedding",
            "starting_price_idr": 1_500_000,
        },
    },
    {
        "email": "kreator2@jepret.local",
        "password": "kreator12345",
        "full_name": "Rana Lestari",
        "profile": {
            "display_name": "Rana Potret",
            "city": "Jakarta",
            "bio": "Spesialis potret keluarga dan personal branding.",
            "specialty": "portrait",
            "starting_price_idr": 750_000,
        },
    },
    {
        "email": "kreator3@jepret.local",
        "password": "kreator12345",
        "full_name": "Bagus Wijaya",
        "profile": {
            "display_name": "Kilat Studio",
            "city": "Jakarta",
            "bio": "Foto produk untuk UMKM dan katalog e-commerce.",
            "specialty": "product",
            "starting_price_idr": 500_000,
        },
    },
    {
        "email": "kreator4@jepret.local",
        "password": "kreator12345",
        "full_name": "Sari Utami",
        "profile": {
            "display_name": "Cerita Senja",
            "city": "Yogyakarta",
            "bio": "Dokumentasi pernikahan adat dan prewedding.",
            "specialty": "wedding",
            "starting_price_idr": 2_000_000,
        },
    },
    {
        "email": "kreator5@jepret.local",
        "password": "kreator12345",
        "full_name": "Dimas Pratama",
        "profile": {
            "display_name": "Gerak Frame",
            "city": "Surabaya",
            "bio": "Videografer acara perusahaan dan aftermovie.",
            "specialty": "video",
            "starting_price_idr": 3_000_000,
        },
    },
    {
        "email": "kreator6@jepret.local",
        "password": "kreator12345",
        "full_name": "Made Ayu",
        "profile": {
            "display_name": "Pulau Lensa",
            "city": "Denpasar",
            "bio": "Foto destinasi dan elopement di Bali.",
            "specialty": "wedding",
            "starting_price_idr": 4_500_000,
        },
    },
    {
        "email": "kreator7@jepret.local",
        "password": "kreator12345",
        "full_name": "Tono Saputra",
        "profile": {
            "display_name": "Panggung Kota",
            "city": "Bandung",
            "bio": "Dokumentasi konser, festival, dan acara komunitas.",
            "specialty": "event",
            "starting_price_idr": 1_000_000,
        },
    },
    {
        "email": "kreator8@jepret.local",
        "password": "kreator12345",
        "full_name": "Nina Kartika",
        "profile": {
            "display_name": "Piksel Rasa",
            "city": "Yogyakarta",
            "bio": "Foto kuliner untuk restoran dan kafe.",
            "specialty": "product",
            "starting_price_idr": 650_000,
        },
    },
]


async def _upsert_user(db: AsyncSession, entry: dict[str, Any]) -> User:
    user = await db.scalar(select(User).where(User.email == entry["email"]))
    if user is None:
        user = User(
            email=entry["email"],
            password_hash=hash_password(entry["password"]),
            full_name=entry["full_name"],
            is_admin=entry.get("is_admin", False),
        )
        db.add(user)
        await db.flush()
        print(f"created {entry['email']}")
    else:
        print(f"exists  {entry['email']}")
    return user


@dataclass(frozen=True)
class DemoBooking:
    scenario: str
    event_date: date
    status: str
    payment_status: str | None

    @property
    def note(self) -> str:
        return f"Booking demo [{self.scenario}]."


DEMO_BOOKINGS = [
    DemoBooking("requested", date(2026, 9, 1), "requested", None),
    DemoBooking("accepted", date(2026, 9, 16), "accepted", None),
    DemoBooking("awaiting-payment", date(2026, 10, 1), "awaiting_payment", "pending"),
    DemoBooking("confirmed-held", date(2026, 10, 16), "confirmed", "held"),
    DemoBooking("completed-released", date(2026, 7, 13), "completed", "released"),
]


async def _seed_bookings(db: AsyncSession) -> None:
    client = await db.scalar(select(User).where(User.email == DEMO_CLIENT_EMAIL))
    creator_user = await db.scalar(select(User).where(User.email == DEMO_CREATOR_EMAIL))
    if client is None or creator_user is None:
        return
    profile = await db.scalar(
        select(CreatorProfile).where(CreatorProfile.user_id == creator_user.id)
    )
    if profile is None:
        return

    legacy_bookings = list(
        (
            await db.scalars(
                select(Booking).where(
                    Booking.client_id == client.id,
                    Booking.creator_profile_id == profile.id,
                    Booking.notes == LEGACY_BOOKING_NOTE,
                )
            )
        ).all()
    )
    for legacy_booking in legacy_bookings:
        await db.delete(legacy_booking)
        print(f"removed legacy booking demo {legacy_booking.event_date}")
    await db.flush()

    for entry in DEMO_BOOKINGS:
        result = await db.execute(
            select(Booking)
            .options(selectinload(Booking.payment))
            .where(
                Booking.client_id == client.id,
                Booking.creator_profile_id == profile.id,
                Booking.notes == entry.note,
            )
        )
        booking = result.scalar_one_or_none()
        if booking is None:
            booking = Booking(
                client_id=client.id,
                creator_profile_id=profile.id,
                event_date=entry.event_date,
                event_city=profile.city,
                notes=entry.note,
                status=entry.status,
                quoted_price_idr=profile.starting_price_idr,
                payment=None,
            )
            db.add(booking)
            print(f"created booking demo {entry.status} {entry.event_date}")
        else:
            booking.event_date = entry.event_date
            booking.event_city = profile.city
            booking.status = entry.status
            booking.quoted_price_idr = profile.starting_price_idr

        if entry.payment_status is None:
            if booking.payment is not None:
                booking.payment = None
            continue

        await db.flush()
        paid_at = None
        held_at = None
        released_at = None
        if entry.payment_status in {"held", "released"}:
            paid_at = PAYMENT_PAID_AT
            held_at = PAYMENT_HELD_AT
        if entry.payment_status == "released":
            released_at = PAYMENT_RELEASED_AT

        amount = booking.quoted_price_idr
        fee = amount * 10 // 100
        if booking.payment is None:
            booking.payment = Payment(
                booking_id=booking.id,
                provider="mock",
                provider_reference=f"mock-{booking.id}",
                idempotency_key=f"seed-{booking.id}",
                amount_idr=amount,
                platform_fee_idr=fee,
                creator_net_idr=amount - fee,
                status=entry.payment_status,
                paid_at=paid_at,
                held_at=held_at,
                released_at=released_at,
                created_at=PAYMENT_CREATED_AT,
                updated_at=released_at or held_at or PAYMENT_CREATED_AT,
            )
            print(f"created payment demo {entry.payment_status} {entry.event_date}")
        else:
            payment = booking.payment
            payment.provider = "mock"
            payment.provider_reference = f"mock-{booking.id}"
            payment.idempotency_key = f"seed-{booking.id}"
            payment.amount_idr = amount
            payment.platform_fee_idr = fee
            payment.creator_net_idr = amount - fee
            payment.status = entry.payment_status
            payment.paid_at = paid_at
            payment.held_at = held_at
            payment.released_at = released_at
            payment.refunded_at = None
            payment.raw_metadata = None
            payment.created_at = PAYMENT_CREATED_AT
            payment.updated_at = released_at or held_at or PAYMENT_CREATED_AT
            print(f"reconciled payment demo {entry.payment_status} {entry.event_date}")


async def seed() -> None:
    factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with factory() as db:
        for user_entry in DEMO_USERS:
            await _upsert_user(db, user_entry)

        for index, creator_entry in enumerate(DEMO_CREATORS):
            user = await _upsert_user(db, creator_entry)
            profile = await db.scalar(
                select(CreatorProfile).where(CreatorProfile.user_id == user.id)
            )
            if profile is None:
                reviewed_at = BASE_REVIEWED_AT + timedelta(minutes=index)
                db.add(
                    CreatorProfile(
                        user_id=user.id,
                        status="approved",
                        submitted_at=reviewed_at,
                        reviewed_at=reviewed_at,
                        **creator_entry["profile"],
                    )
                )
                profile_name = creator_entry["profile"]["display_name"]
                print(f"created creator profile {profile_name} (approved)")

        await db.flush()
        await _seed_bookings(db)
        await db.commit()
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(seed())
