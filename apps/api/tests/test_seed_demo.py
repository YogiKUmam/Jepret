import asyncio
import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db.models import (
    Booking,
    Conversation,
    CreatorProfile,
    Deliverable,
    Message,
    Payment,
    PaymentEvent,
    User,
)
from scripts import seed_demo

pytestmark = pytest.mark.integration

EXPECTED_EVENT_DATES = {
    "Booking demo [requested].": date(2026, 9, 1),
    "Booking demo [accepted].": date(2026, 9, 16),
    "Booking demo [awaiting-payment].": date(2026, 10, 1),
    "Booking demo [confirmed-held].": date(2026, 10, 16),
    "Booking demo [in-progress].": date(2026, 10, 31),
    "Booking demo [delivered].": date(2026, 11, 15),
    "Booking demo [completed-released].": date(2026, 7, 13),
}
EXPECTED_BOOKING_TIMESTAMP = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
EXPECTED_DEMO_SEED_LOCK_KEY = 0x4A4550524554


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
            initial_by_note = {booking.notes: booking for booking in initial_bookings}
            accepted_booking = initial_by_note["Booking demo [accepted]."]
            confirmed_booking = initial_by_note["Booking demo [confirmed-held]."]
            in_progress_booking = initial_by_note["Booking demo [in-progress]."]
            delivered_booking = initial_by_note["Booking demo [delivered]."]
            seed_conversation_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"jepret:seed:{in_progress_booking.id}:conversation",
            )
            unknown_conversation_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"jepret:test:user-conversation:{delivered_booking.id}",
            )
            unknown_seed_thread_message_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"jepret:test:user-message:{seed_conversation_id}",
            )
            unknown_conversation_message_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"jepret:test:user-message:{unknown_conversation_id}",
            )
            unknown_deliverable_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"jepret:test:user-deliverable:{delivered_booking.id}",
            )
            stale_seed_conversation_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"jepret:seed:{accepted_booking.id}:conversation",
            )
            stale_seed_message_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"jepret:seed:{accepted_booking.id}:message-row:1",
            )
            stale_seed_deliverable_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"jepret:seed:{confirmed_booking.id}:deliverable",
            )
            removable_seed_deliverable_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"jepret:seed:{accepted_booking.id}:deliverable",
            )
            unknown_revision_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"jepret:test:user-revision:{stale_seed_deliverable_id}",
            )
            desired_seed_deliverable_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"jepret:seed:{delivered_booking.id}:deliverable",
            )
            desired_seed_deliverable = await db.get(
                Deliverable,
                desired_seed_deliverable_id,
            )
            assert desired_seed_deliverable is not None
            desired_seed_deliverable.title = "Judul seed lama"
            desired_seed_deliverable.description = "Deskripsi seed lama."
            desired_seed_deliverable.external_url = "https://example.com/legacy-demo-gallery"
            db.add_all(
                [
                    Conversation(
                        id=unknown_conversation_id,
                        booking_id=delivered_booking.id,
                    ),
                    Message(
                        id=unknown_seed_thread_message_id,
                        conversation_id=seed_conversation_id,
                        sender_user_id=client.id,
                        client_message_id=unknown_seed_thread_message_id,
                        message_type="text",
                        body="Pesan pengguna pada percakapan demo.",
                    ),
                    Message(
                        id=unknown_conversation_message_id,
                        conversation_id=unknown_conversation_id,
                        sender_user_id=creator_user.id,
                        client_message_id=unknown_conversation_message_id,
                        message_type="text",
                        body="Percakapan pengguna harus tetap utuh.",
                    ),
                    Deliverable(
                        id=unknown_deliverable_id,
                        booking_id=delivered_booking.id,
                        uploaded_by_user_id=creator_user.id,
                        title="Galeri milik pengguna",
                        description="Bukan data yang dimiliki seed.",
                        source_type="external_link",
                        external_url="https://example.com/user-demo-gallery",
                    ),
                    Conversation(
                        id=stale_seed_conversation_id,
                        booking_id=accepted_booking.id,
                    ),
                    Message(
                        id=stale_seed_message_id,
                        conversation_id=stale_seed_conversation_id,
                        sender_user_id=creator_user.id,
                        client_message_id=uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"jepret:seed:{accepted_booking.id}:message:1",
                        ),
                        message_type="text",
                        body="Varian seed yang sudah tidak dipakai.",
                    ),
                    Deliverable(
                        id=stale_seed_deliverable_id,
                        booking_id=confirmed_booking.id,
                        uploaded_by_user_id=creator_user.id,
                        title="Galeri seed versi lama yang direvisi pengguna",
                        description="Metadata versi seed sebelumnya.",
                        source_type="external_link",
                        external_url="https://example.com/legacy-referenced-gallery",
                    ),
                    Deliverable(
                        id=removable_seed_deliverable_id,
                        booking_id=accepted_booking.id,
                        uploaded_by_user_id=creator_user.id,
                        title="Galeri seed versi lama tanpa referensi",
                        description="Metadata versi seed sebelumnya.",
                        source_type="external_link",
                        external_url="https://example.com/legacy-unreferenced-gallery",
                    ),
                    Deliverable(
                        id=unknown_revision_id,
                        booking_id=confirmed_booking.id,
                        uploaded_by_user_id=creator_user.id,
                        title="Revisi milik pengguna",
                        source_type="external_link",
                        external_url="https://example.com/user-revision",
                        replaces_deliverable_id=stale_seed_deliverable_id,
                    ),
                ]
            )

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
            assert len(bookings) == 7
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
                transition_times = [
                    value
                    for value in (
                        seed_demo.BOOKING_UPDATED_AT,
                        booking.responded_at,
                        booking.started_at,
                        booking.delivered_at,
                        booking.completed_at,
                        booking.payment.created_at if booking.payment is not None else None,
                        booking.payment.paid_at if booking.payment is not None else None,
                        booking.payment.held_at if booking.payment is not None else None,
                        booking.payment.released_at if booking.payment is not None else None,
                    )
                    if value is not None
                ]
                assert booking.updated_at >= max(transition_times)
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
                "Booking demo [in-progress].": "held",
                "Booking demo [delivered].": "held",
                "Booking demo [completed-released].": "released",
            }

            seed_booking_ids = [booking.id for booking in bookings]
            conversations = list(
                (
                    await db.scalars(
                        select(Conversation).where(Conversation.booking_id.in_(seed_booking_ids))
                    )
                ).all()
            )
            assert {conversation.id for conversation in conversations} == {
                seed_conversation_id,
                unknown_conversation_id,
            }
            assert await db.get(Conversation, stale_seed_conversation_id) is None
            assert await db.get(Message, stale_seed_message_id) is None
            seed_conversation = next(
                conversation
                for conversation in conversations
                if conversation.id == seed_conversation_id
            )
            assert seed_conversation.booking_id == by_note["Booking demo [in-progress]."].id
            messages = list(
                (
                    await db.scalars(
                        select(Message)
                        .where(Message.conversation_id == seed_conversation.id)
                        .order_by(Message.created_at, Message.id)
                    )
                ).all()
            )
            seed_message_ids = {
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"jepret:seed:{seed_conversation.booking_id}:message-row:{index}",
                )
                for index in (1, 2)
            }
            seed_messages = [message for message in messages if message.id in seed_message_ids]
            assert len(seed_messages) == 2
            assert [message.body for message in seed_messages] == [
                "Halo, saya siap mengerjakan dokumentasi ini.",
                "Terima kasih, detail acara sudah sesuai.",
            ]
            assert all(
                message.client_message_id
                == uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"jepret:seed:{by_note['Booking demo [in-progress].'].id}:message:{index}",
                )
                for index, message in enumerate(seed_messages, start=1)
            )
            unknown_seed_thread_message = next(
                message for message in messages if message.id == unknown_seed_thread_message_id
            )
            assert unknown_seed_thread_message.body == "Pesan pengguna pada percakapan demo."
            unknown_conversation_message = await db.get(Message, unknown_conversation_message_id)
            assert unknown_conversation_message is not None
            assert unknown_conversation_message.body == "Percakapan pengguna harus tetap utuh."

            deliverables = list(
                (
                    await db.scalars(
                        select(Deliverable).where(Deliverable.booking_id.in_(seed_booking_ids))
                    )
                ).all()
            )
            seed_deliverable_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"jepret:seed:{by_note['Booking demo [delivered].'].id}:deliverable",
            )
            assert {deliverable.id for deliverable in deliverables} == {
                seed_deliverable_id,
                unknown_deliverable_id,
                stale_seed_deliverable_id,
                unknown_revision_id,
            }
            assert await db.get(Deliverable, stale_seed_deliverable_id) is not None
            assert await db.get(Deliverable, unknown_revision_id) is not None
            assert await db.get(Deliverable, removable_seed_deliverable_id) is None
            seed_deliverable = next(
                deliverable for deliverable in deliverables if deliverable.id == seed_deliverable_id
            )
            assert seed_deliverable.booking_id == by_note["Booking demo [delivered]."].id
            assert seed_deliverable.title == seed_demo.WORKSPACE_DELIVERABLE_TITLE
            assert seed_deliverable.description == seed_demo.WORKSPACE_DELIVERABLE_DESCRIPTION
            assert seed_deliverable.external_url == "https://example.com/jepret-demo-gallery"
            assert seed_deliverable.source_type == "external_link"
            assert seed_deliverable.upload_id is None
            assert seed_deliverable.created_at == seed_demo.BOOKING_DELIVERED_AT
            assert "signed" not in seed_deliverable.external_url
            preserved_stale_seed = await db.get(Deliverable, stale_seed_deliverable_id)
            assert preserved_stale_seed is not None
            assert preserved_stale_seed.title == "Galeri seed versi lama yang direvisi pengguna"
            assert (
                preserved_stale_seed.external_url == "https://example.com/legacy-referenced-gallery"
            )
            unknown_deliverable = next(
                deliverable
                for deliverable in deliverables
                if deliverable.id == unknown_deliverable_id
            )
            assert unknown_deliverable.title == "Galeri milik pengguna"
            assert unknown_deliverable.external_url == "https://example.com/user-demo-gallery"
            assert unknown_deliverable.upload_id is None

            await db.delete(seed_conversation)
            await db.flush()
            occupied_conversation_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"jepret:test:occupied-conversation:{in_progress_booking.id}",
            )
            occupied_message_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"jepret:test:occupied-message:{in_progress_booking.id}",
            )
            db.add_all(
                [
                    Conversation(
                        id=occupied_conversation_id,
                        booking_id=in_progress_booking.id,
                    ),
                    Message(
                        id=occupied_message_id,
                        conversation_id=occupied_conversation_id,
                        sender_user_id=client.id,
                        client_message_id=occupied_message_id,
                        message_type="text",
                        body="Slot percakapan ini milik pengguna.",
                    ),
                ]
            )
            await db.commit()

            await seed_demo._seed_bookings(db)
            await db.commit()

            assert await db.get(Conversation, seed_conversation_id) is None
            occupied_conversation = await db.get(Conversation, occupied_conversation_id)
            assert occupied_conversation is not None
            occupied_message = await db.get(Message, occupied_message_id)
            assert occupied_message is not None
            assert occupied_message.body == "Slot percakapan ini milik pengguna."
            assert await db.get(Deliverable, unknown_deliverable_id) is not None

            current_seed_deliverable = await db.get(Deliverable, seed_deliverable_id)
            assert current_seed_deliverable is not None
            await db.delete(current_seed_deliverable)
            await db.flush()
            collision_title = "Konten pengguna dengan UUID bentrok"
            db.add(
                Deliverable(
                    id=seed_deliverable_id,
                    booking_id=unrelated.id,
                    uploaded_by_user_id=creator_user.id,
                    title=collision_title,
                    source_type="external_link",
                    external_url="https://example.com/user-collision",
                )
            )
            await db.commit()

            await seed_demo._seed_bookings(db)
            await db.commit()

            collision = await db.get(Deliverable, seed_deliverable_id)
            assert collision is not None
            assert collision.booking_id == unrelated.id
            assert collision.uploaded_by_user_id == creator_user.id
            assert collision.title == collision_title
            assert collision.external_url == "https://example.com/user-collision"

            await db.delete(collision)
            await db.flush()
            wrong_uploader_title = "Konten pengguna pada booking target"
            db.add(
                Deliverable(
                    id=seed_deliverable_id,
                    booking_id=delivered_booking.id,
                    uploaded_by_user_id=client.id,
                    title=wrong_uploader_title,
                    source_type="external_link",
                    external_url="https://example.com/wrong-uploader-collision",
                )
            )
            await db.commit()

            await seed_demo._seed_bookings(db)
            await db.commit()

            wrong_uploader_collision = await db.get(Deliverable, seed_deliverable_id)
            assert wrong_uploader_collision is not None
            assert wrong_uploader_collision.booking_id == delivered_booking.id
            assert wrong_uploader_collision.uploaded_by_user_id == client.id
            assert wrong_uploader_collision.title == wrong_uploader_title
            assert (
                wrong_uploader_collision.external_url
                == "https://example.com/wrong-uploader-collision"
            )

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
            user_ids = [user.id for user in users]
            await db.execute(delete(Message).where(Message.sender_user_id.in_(user_ids)))
            await db.execute(
                delete(Deliverable).where(Deliverable.uploaded_by_user_id.in_(user_ids))
            )
            for user in users:
                await db.delete(user)
            await db.commit()
        await engine.dispose()


async def test_concurrent_seed_runs_are_serialized_and_remain_unique(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_email = f"seed-race-client-{uuid.uuid4().hex}@jepret.local"
    creator_email = f"seed-race-creator-{uuid.uuid4().hex}@jepret.local"
    monkeypatch.setattr(seed_demo, "DEMO_CLIENT_EMAIL", client_email)
    monkeypatch.setattr(seed_demo, "DEMO_CREATOR_EMAIL", creator_email)
    engine = create_async_engine(get_settings().database_url, poolclass=None)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    waiter_task: asyncio.Task[None] | None = None
    try:
        async with factory() as setup:
            client = User(email=client_email, password_hash="seed-test", full_name="Klien Race")
            creator = User(
                email=creator_email,
                password_hash="seed-test",
                full_name="Kreator Race",
            )
            profile = CreatorProfile(
                user=creator,
                display_name="Studio Race",
                city="Bandung",
                bio="Seed concurrency test.",
                specialty="wedding",
                starting_price_idr=1_500_000,
                status="approved",
            )
            setup.add_all([client, creator, profile])
            await setup.commit()
            client_id = client.id
            creator_id = creator.id
            profile_id = profile.id

        async with factory() as holder, factory() as waiter, factory() as probe:
            await holder.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": EXPECTED_DEMO_SEED_LOCK_KEY},
            )
            await seed_demo._seed_bookings(holder)
            waiter_pid = await waiter.scalar(text("SELECT pg_backend_pid()"))
            assert waiter_pid is not None
            waiter_task = asyncio.create_task(seed_demo._seed_bookings(waiter))

            async with asyncio.timeout(5):
                while True:
                    if waiter_task.done():
                        await waiter_task
                        pytest.fail("seed kedua tidak menunggu advisory lock lintas transaksi")
                    blockers = await probe.scalar(
                        text("SELECT pg_blocking_pids(:waiter_pid)"),
                        {"waiter_pid": waiter_pid},
                    )
                    if blockers:
                        break

            await holder.commit()
            await asyncio.wait_for(waiter_task, timeout=5)
            await waiter.commit()

        async with factory() as verify:
            bookings = list(
                (
                    await verify.scalars(
                        select(Booking).where(
                            Booking.client_id == client_id,
                            Booking.creator_profile_id == profile_id,
                            Booking.notes.in_(EXPECTED_EVENT_DATES),
                        )
                    )
                ).all()
            )
            assert len(bookings) == 7
            by_note = {booking.notes: booking for booking in bookings}
            in_progress = by_note["Booking demo [in-progress]."]
            delivered = by_note["Booking demo [delivered]."]
            conversation_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"jepret:seed:{in_progress.id}:conversation",
            )
            assert (
                await verify.scalar(
                    select(func.count(Conversation.id)).where(Conversation.id == conversation_id)
                )
                == 1
            )
            assert (
                await verify.scalar(
                    select(func.count(Message.id)).where(
                        Message.id.in_(
                            [
                                uuid.uuid5(
                                    uuid.NAMESPACE_URL,
                                    f"jepret:seed:{in_progress.id}:message-row:{index}",
                                )
                                for index in (1, 2)
                            ]
                        )
                    )
                )
                == 2
            )
            deliverable_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"jepret:seed:{delivered.id}:deliverable",
            )
            assert (
                await verify.scalar(
                    select(func.count(Deliverable.id)).where(Deliverable.id == deliverable_id)
                )
                == 1
            )
    finally:
        if waiter_task is not None and not waiter_task.done():
            waiter_task.cancel()
            await asyncio.gather(waiter_task, return_exceptions=True)
        async with factory() as cleanup:
            await cleanup.execute(
                delete(Message).where(Message.sender_user_id.in_([client_id, creator_id]))
            )
            await cleanup.execute(
                delete(Deliverable).where(
                    Deliverable.uploaded_by_user_id.in_([client_id, creator_id])
                )
            )
            await cleanup.execute(delete(User).where(User.id.in_([client_id, creator_id])))
            await cleanup.commit()
        await engine.dispose()
