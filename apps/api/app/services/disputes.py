import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import DomainError
from app.db.models import Booking, Conversation, CreatorProfile, Dispute, Message, Payment, User
from app.services import payments as payment_service


async def open_booking_dispute(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    client_user: User,
    reason_category: str,
    description: str,
) -> Dispute:
    booking_stmt = select(Booking).where(Booking.id == booking_id).with_for_update()
    booking = (await db.scalars(booking_stmt)).first()
    if not booking:
        raise DomainError("NOT_FOUND", "Booking tidak ditemukan.", 404)

    if booking.client_id != client_user.id:
        raise DomainError(
            "FORBIDDEN", "Hanya klien pembuat booking yang dapat mengajukan sengketa.", 403
        )

    if booking.status not in ("confirmed", "in_progress", "delivered"):
        raise DomainError(
            "INVALID_STATUS",
            "Sengketa hanya dapat diajukan pada booking yang sedang aktif "
            "(confirmed, in_progress, delivered).",
            409,
        )

    existing = (await db.scalars(select(Dispute).where(Dispute.booking_id == booking_id))).first()
    if existing:
        raise DomainError(
            "DISPUTE_ALREADY_EXISTS", "Sengketa untuk booking ini sudah pernah diajukan.", 409
        )

    clean_desc = description.strip()
    if len(clean_desc) < 10:
        raise DomainError("INVALID_DESCRIPTION", "Deskripsi sengketa minimal 10 karakter.", 422)

    # 1. Update booking status
    booking.status = "disputed"

    # 2. Create dispute
    dispute = Dispute(
        id=uuid.uuid4(),
        booking_id=booking.id,
        opened_by_user_id=client_user.id,
        reason_category=reason_category,
        description=clean_desc,
        status="open",
        created_at=datetime.now(UTC),
    )
    db.add(dispute)

    # 3. Post system message to conversation if conversation exists
    conversation = (
        await db.scalars(select(Conversation).where(Conversation.booking_id == booking.id))
    ).first()
    if conversation:
        system_msg = Message(
            id=uuid.uuid4(),
            conversation_id=conversation.id,
            sender_user_id=client_user.id,
            client_message_id=uuid.uuid4(),
            message_type="system",
            body=(
                "Sengketa telah diajukan oleh klien. Dana ditahan sementara menunggu mediasi admin."
            ),
            created_at=datetime.now(UTC),
        )
        db.add(system_msg)

    await db.commit()

    reloaded_stmt = (
        select(Dispute).options(selectinload(Dispute.opened_by)).where(Dispute.id == dispute.id)
    )
    return (await db.scalars(reloaded_stmt)).one()


async def get_booking_dispute(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    user: User,
) -> Dispute | None:
    booking = (await db.scalars(select(Booking).where(Booking.id == booking_id))).first()
    if not booking:
        raise DomainError("NOT_FOUND", "Booking tidak ditemukan.", 404)

    if not user.is_admin and booking.client_id != user.id:
        creator_profile = (
            await db.scalars(
                select(CreatorProfile).where(
                    CreatorProfile.id == booking.creator_profile_id,
                    CreatorProfile.user_id == user.id,
                )
            )
        ).first()
        if not creator_profile:
            raise DomainError(
                "FORBIDDEN", "Anda tidak memiliki akses ke sengketa booking ini.", 403
            )

    stmt = (
        select(Dispute)
        .options(selectinload(Dispute.opened_by))
        .where(Dispute.booking_id == booking_id)
    )
    return (await db.scalars(stmt)).first()


async def list_disputes_for_admin(
    db: AsyncSession,
    *,
    status: str | None = None,
) -> list[Dispute]:
    stmt = select(Dispute).options(selectinload(Dispute.opened_by))
    if status:
        stmt = stmt.where(Dispute.status == status)
    stmt = stmt.order_by(Dispute.created_at.desc())
    return list((await db.scalars(stmt)).all())


async def resolve_dispute_for_admin(
    db: AsyncSession,
    *,
    dispute_id: uuid.UUID,
    admin_user: User,
    resolution: str,
    resolution_notes: str,
) -> Dispute:
    if resolution not in ("resolved_client", "resolved_creator"):
        raise DomainError(
            "INVALID_RESOLUTION",
            "Resolusi harus bernilai resolved_client atau resolved_creator.",
            422,
        )

    dispute_stmt = (
        select(Dispute)
        .options(selectinload(Dispute.opened_by))
        .where(Dispute.id == dispute_id)
        .with_for_update()
    )
    dispute = (await db.scalars(dispute_stmt)).first()
    if not dispute:
        raise DomainError("NOT_FOUND", "Sengketa tidak ditemukan.", 404)

    if dispute.status in ("resolved_client", "resolved_creator", "closed"):
        raise DomainError(
            "DISPUTE_ALREADY_RESOLVED", "Sengketa ini sudah pernah diselesaikan.", 409
        )

    booking_stmt = select(Booking).where(Booking.id == dispute.booking_id).with_for_update()
    booking = (await db.scalars(booking_stmt)).one()

    payment_stmt = select(Payment).where(Payment.booking_id == booking.id).with_for_update()
    payment = (await db.scalars(payment_stmt)).first()

    now = datetime.now(UTC)

    if resolution == "resolved_client":
        booking.status = "cancelled"
        booking.cancelled_at = now
        if payment and payment.status == "held":
            provider_event = await payment_service.PROVIDER.refund_payment(payment.id)
            await payment_service._stage_locked_provider_event(
                db,
                payment=payment,
                booking=booking,
                event=provider_event,
            )
        resolution_msg = (
            "Sengketa telah diselesaikan oleh admin. Keputusan: Memenangkan Klien. "
            "Pembayaran dikembalikan (refund) dan booking dibatalkan."
        )
    else:  # resolved_creator
        booking.status = "completed"
        booking.completed_at = now
        if payment and payment.status == "held":
            provider_event = await payment_service.PROVIDER.release_payment(payment.id)
            await payment_service.stage_release_for_locked_completion(
                db,
                payment=payment,
                booking=booking,
                event=provider_event,
            )
        resolution_msg = (
            "Sengketa telah diselesaikan oleh admin. Keputusan: Memenangkan Kreator. "
            "Pembayaran telah dilepas ke saldo kreator dan booking selesai."
        )

    dispute.status = resolution
    dispute.resolution_notes = resolution_notes.strip()
    dispute.resolved_by_admin_user_id = admin_user.id
    dispute.resolved_at = now

    conversation = (
        await db.scalars(select(Conversation).where(Conversation.booking_id == booking.id))
    ).first()
    if conversation:
        system_msg = Message(
            id=uuid.uuid4(),
            conversation_id=conversation.id,
            sender_user_id=admin_user.id,
            client_message_id=uuid.uuid4(),
            message_type="system",
            body=resolution_msg,
            created_at=now,
        )
        db.add(system_msg)

    await db.commit()

    reloaded_stmt = (
        select(Dispute).options(selectinload(Dispute.opened_by)).where(Dispute.id == dispute.id)
    )
    return (await db.scalars(reloaded_stmt)).one()
