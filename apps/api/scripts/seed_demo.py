"""Seed idempotent demo accounts for local development only."""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.security import hash_password
from app.db.models import (
    Booking,
    Conversation,
    CreatorProfile,
    Deliverable,
    Message,
    Payment,
    User,
)
from app.db.session import dispose_engine, get_engine

BASE_REVIEWED_AT = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
BOOKING_CREATED_AT = BASE_REVIEWED_AT
BOOKING_UPDATED_AT = BASE_REVIEWED_AT
PAYMENT_CREATED_AT = BASE_REVIEWED_AT + timedelta(hours=1)
PAYMENT_PAID_AT = BASE_REVIEWED_AT + timedelta(days=1)
PAYMENT_HELD_AT = PAYMENT_PAID_AT + timedelta(minutes=5)
BOOKING_RESPONDED_AT = BASE_REVIEWED_AT + timedelta(minutes=30)
BOOKING_STARTED_AT = PAYMENT_HELD_AT + timedelta(minutes=5)
BOOKING_DELIVERED_AT = PAYMENT_HELD_AT + timedelta(hours=1)
PAYMENT_RELEASED_AT = BASE_REVIEWED_AT + timedelta(days=2)
WORKSPACE_DELIVERABLE_TITLE = "Galeri demo Jepret"
WORKSPACE_DELIVERABLE_DESCRIPTION = "Contoh hasil eksternal untuk alur booking delivered."
WORKSPACE_DELIVERABLE_URL = "https://example.com/jepret-demo-gallery"
# Stable cross-process PostgreSQL transaction lock for the demo booking reconciler.
DEMO_SEED_ADVISORY_LOCK_KEY = 0x4A4550524554
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
    DemoBooking("in-progress", date(2026, 10, 31), "in_progress", "held"),
    DemoBooking("delivered", date(2026, 11, 15), "delivered", "held"),
    DemoBooking("completed-released", date(2026, 7, 13), "completed", "released"),
]


async def _reconcile_workspace_demo(
    db: AsyncSession,
    *,
    bookings: dict[str, Booking],
    client: User,
    creator: User,
) -> None:
    in_progress = bookings["in-progress"]
    delivered = bookings["delivered"]
    conversation_ids = {
        booking.id: uuid.uuid5(uuid.NAMESPACE_URL, f"jepret:seed:{booking.id}:conversation")
        for booking in bookings.values()
    }
    target_conversation_id = conversation_ids[in_progress.id]

    conversations = list(
        (
            await db.scalars(
                select(Conversation).where(
                    Conversation.booking_id.in_([booking.id for booking in bookings.values()])
                )
            )
        ).all()
    )
    conversation = next(
        (
            value
            for value in conversations
            if value.id == target_conversation_id and value.booking_id == in_progress.id
        ),
        None,
    )
    occupied_target = next(
        (value for value in conversations if value.booking_id == in_progress.id), None
    )
    for value in conversations:
        expected_id = conversation_ids[value.booking_id]
        if value.id != expected_id or value.id == target_conversation_id:
            continue
        seed_message_ids = {
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"jepret:seed:{value.booking_id}:message-row:{index}",
            )
            for index in (1, 2)
        }
        messages = list(
            (await db.scalars(select(Message).where(Message.conversation_id == value.id))).all()
        )
        for message in messages:
            if message.id in seed_message_ids:
                await db.delete(message)
        if all(message.id in seed_message_ids for message in messages):
            await db.delete(value)
    target_id_exists = any(value.id == target_conversation_id for value in conversations)
    if conversation is None and occupied_target is None and not target_id_exists:
        conversation = Conversation(
            id=target_conversation_id,
            booking_id=in_progress.id,
            created_at=BOOKING_STARTED_AT,
            updated_at=BOOKING_STARTED_AT,
        )
        db.add(conversation)
        await db.flush()
        print("created workspace demo conversation")

    if conversation is not None:
        desired_messages = (
            (1, creator.id, "Halo, saya siap mengerjakan dokumentasi ini."),
            (2, client.id, "Terima kasih, detail acara sudah sesuai."),
        )
        existing_messages = list(
            (
                await db.scalars(select(Message).where(Message.conversation_id == conversation.id))
            ).all()
        )
        by_id = {value.id: value for value in existing_messages}
        for index, sender_id, body in desired_messages:
            client_message_id = uuid.uuid5(
                uuid.NAMESPACE_URL, f"jepret:seed:{in_progress.id}:message:{index}"
            )
            message_id = uuid.uuid5(
                uuid.NAMESPACE_URL, f"jepret:seed:{in_progress.id}:message-row:{index}"
            )
            value = by_id.get(message_id)
            created_at = BOOKING_STARTED_AT + timedelta(minutes=index)
            if value is None:
                occupied_client_id = any(
                    message.sender_user_id == sender_id
                    and message.client_message_id == client_message_id
                    for message in existing_messages
                )
                if occupied_client_id:
                    continue
                value = Message(
                    id=message_id,
                    conversation_id=conversation.id,
                    sender_user_id=sender_id,
                    client_message_id=client_message_id,
                    message_type="text",
                    body=body,
                    created_at=created_at,
                )
                db.add(value)
            else:
                value.sender_user_id = sender_id
                value.client_message_id = client_message_id
                value.message_type = "text"
                value.body = body
                value.upload_id = None
                value.attachment_filename = None
                value.attachment_content_type = None
                value.attachment_size_bytes = None
                value.read_at = None
                value.created_at = created_at
                value.edited_at = None

    deliverable_ids = {
        booking.id: uuid.uuid5(uuid.NAMESPACE_URL, f"jepret:seed:{booking.id}:deliverable")
        for booking in bookings.values()
    }
    desired_deliverable_id = deliverable_ids[delivered.id]
    deliverables = list(
        (
            await db.scalars(
                select(Deliverable).where(Deliverable.id.in_(deliverable_ids.values()))
            )
        ).all()
    )
    deliverable = next(
        (value for value in deliverables if value.id == desired_deliverable_id), None
    )
    expected_booking_by_id = {
        deliverable_id: booking_id for booking_id, deliverable_id in deliverable_ids.items()
    }

    def is_seed_owned(value: Deliverable) -> bool:
        return (
            value.booking_id == expected_booking_by_id[value.id]
            and value.uploaded_by_user_id == creator.id
        )

    for value in deliverables:
        if value.id == desired_deliverable_id or not is_seed_owned(value):
            continue
        has_revisions = await db.scalar(
            select(Deliverable.id).where(Deliverable.replaces_deliverable_id == value.id).limit(1)
        )
        if has_revisions is None:
            await db.delete(value)
    deliverable_is_owned = deliverable is not None and is_seed_owned(deliverable)
    desired_id_is_occupied = deliverable is not None and not deliverable_is_owned
    if deliverable is None and not desired_id_is_occupied:
        deliverable = Deliverable(
            id=desired_deliverable_id,
            booking_id=delivered.id,
            uploaded_by_user_id=creator.id,
            title=WORKSPACE_DELIVERABLE_TITLE,
            description=WORKSPACE_DELIVERABLE_DESCRIPTION,
            source_type="external_link",
            external_url=WORKSPACE_DELIVERABLE_URL,
            created_at=BOOKING_DELIVERED_AT,
        )
        db.add(deliverable)
        print("created workspace demo deliverable")
    elif deliverable_is_owned:
        deliverable.uploaded_by_user_id = creator.id
        deliverable.title = WORKSPACE_DELIVERABLE_TITLE
        deliverable.description = WORKSPACE_DELIVERABLE_DESCRIPTION
        deliverable.source_type = "external_link"
        deliverable.upload_id = None
        deliverable.external_url = WORKSPACE_DELIVERABLE_URL
        deliverable.media_type = None
        deliverable.filename = None
        deliverable.content_type = None
        deliverable.size_bytes = None
        deliverable.replaces_deliverable_id = None
        deliverable.created_at = BOOKING_DELIVERED_AT


async def _acquire_demo_seed_lock(db: AsyncSession) -> None:
    """Serialize the complete deterministic seed transaction across processes."""
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": DEMO_SEED_ADVISORY_LOCK_KEY},
    )


async def _seed_bookings(db: AsyncSession) -> None:
    await _acquire_demo_seed_lock(db)
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

    seeded_bookings: dict[str, Booking] = {}
    for entry in DEMO_BOOKINGS:
        result = await db.execute(
            select(Booking)
            .options(selectinload(Booking.payment).selectinload(Payment.events))
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
                created_at=BOOKING_CREATED_AT,
                updated_at=BOOKING_UPDATED_AT,
            )
            db.add(booking)
            print(f"created booking demo {entry.status} {entry.event_date}")
        else:
            booking.event_date = entry.event_date
            booking.event_city = profile.city
            booking.status = entry.status
            booking.quoted_price_idr = profile.starting_price_idr
            booking.created_at = BOOKING_CREATED_AT
            booking.updated_at = BOOKING_UPDATED_AT

        booking.responded_at = None if entry.status == "requested" else BOOKING_RESPONDED_AT
        booking.started_at = (
            BOOKING_STARTED_AT
            if entry.status in {"in_progress", "delivered", "completed"}
            else None
        )
        booking.delivered_at = (
            BOOKING_DELIVERED_AT if entry.status in {"delivered", "completed"} else None
        )
        booking.completed_at = PAYMENT_RELEASED_AT if entry.status == "completed" else None
        booking.cancelled_at = None
        booking.updated_at = max(
            value
            for value in (
                BOOKING_UPDATED_AT,
                booking.responded_at,
                booking.started_at,
                booking.delivered_at,
                booking.completed_at,
            )
            if value is not None
        )
        seeded_bookings[entry.scenario] = booking

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
        booking.updated_at = max(
            booking.updated_at,
            released_at or held_at or paid_at or PAYMENT_CREATED_AT,
        )

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
            payment.events.clear()
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

    await db.flush()
    await _reconcile_workspace_demo(
        db,
        bookings=seeded_bookings,
        client=client,
        creator=creator_user,
    )


async def seed() -> None:
    factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with factory() as db:
        # Acquire before any user/profile/workspace reconciliation so two CLI
        # processes cannot race on an earlier unique key.
        await _acquire_demo_seed_lock(db)
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
