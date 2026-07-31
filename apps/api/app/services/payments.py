import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import DomainError
from app.db.models import (
    Booking,
    CreatorProfile,
    Payment,
    User,
)
from app.db.models import (
    PaymentEvent as PaymentEventModel,
)
from app.integrations.payments import (
    MockPaymentProvider,
)
from app.integrations.payments import (
    PaymentEvent as ProviderPaymentEvent,
)

PROVIDER = MockPaymentProvider()
FINAL_PAYMENT_STATUSES = frozenset({"released", "refunded", "failed", "expired"})
_PAYMENT_RELATIONS = (selectinload(Payment.booking).selectinload(Booking.creator_profile),)


def _not_found() -> DomainError:
    return DomainError("NOT_FOUND", "Pembayaran tidak ditemukan.", status_code=404)


def _invalid_transition() -> DomainError:
    return DomainError(
        "INVALID_PAYMENT_TRANSITION",
        "Status pembayaran tidak memungkinkan aksi ini.",
        status_code=409,
    )


def _already_final() -> DomainError:
    return DomainError(
        "PAYMENT_ALREADY_FINAL",
        "Pembayaran sudah berada pada status akhir.",
        status_code=409,
    )


async def _creator_profile_of(db: AsyncSession, user: User) -> CreatorProfile | None:
    result = await db.scalars(select(CreatorProfile).where(CreatorProfile.user_id == user.id))
    return result.one_or_none()


async def _payment_by_booking(db: AsyncSession, booking_id: uuid.UUID) -> Payment | None:
    result = await db.scalars(
        select(Payment).where(Payment.booking_id == booking_id).options(*_PAYMENT_RELATIONS)
    )
    return result.one_or_none()


async def _payment_by_id(db: AsyncSession, payment_id: uuid.UUID) -> Payment | None:
    result = await db.scalars(
        select(Payment).where(Payment.id == payment_id).options(*_PAYMENT_RELATIONS)
    )
    return result.one_or_none()


async def create_payment(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    user: User,
    idempotency_key: str,
) -> tuple[Payment, bool]:
    booking = await db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
    if booking is None or booking.client_id != user.id:
        raise _not_found()

    keyed_payment = await db.scalar(
        select(Payment).where(Payment.idempotency_key == idempotency_key)
    )
    if keyed_payment is not None and keyed_payment.booking_id != booking_id:
        raise DomainError(
            "IDEMPOTENCY_CONFLICT",
            "Idempotency key sudah digunakan untuk booking lain.",
            status_code=409,
        )

    existing = await _payment_by_booking(db, booking_id)
    if existing is not None:
        return existing, False
    if booking.status != "accepted":
        raise DomainError(
            "PAYMENT_NOT_ALLOWED",
            "Pembayaran hanya dapat dibuat untuk booking yang diterima.",
            status_code=409,
        )

    amount_idr = booking.quoted_price_idr
    platform_fee_idr = amount_idr * 10 // 100
    payment = Payment(
        id=uuid.uuid4(),
        booking_id=booking.id,
        provider=PROVIDER.name,
        idempotency_key=idempotency_key,
        amount_idr=amount_idr,
        platform_fee_idr=platform_fee_idr,
        creator_net_idr=amount_idr - platform_fee_idr,
        status="pending",
    )
    payment.provider_reference = await PROVIDER.create_payment(
        payment_id=payment.id, amount_idr=amount_idr
    )
    booking.status = "awaiting_payment"
    db.add(payment)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        keyed_payment = await db.scalar(
            select(Payment).where(Payment.idempotency_key == idempotency_key)
        )
        if keyed_payment is not None and keyed_payment.booking_id != booking_id:
            raise DomainError(
                "IDEMPOTENCY_CONFLICT",
                "Idempotency key sudah digunakan untuk booking lain.",
                status_code=409,
            ) from None
        existing = await _payment_by_booking(db, booking_id)
        if existing is None:
            raise DomainError(
                "PAYMENT_CREATE_CONFLICT",
                "Pembayaran tidak dapat dibuat karena permintaan bersamaan.",
                status_code=409,
            ) from None
        return existing, False
    created = await _payment_by_id(db, payment.id)
    assert created is not None
    return created, True


async def get_for_booking(db: AsyncSession, *, booking_id: uuid.UUID, user: User) -> Payment:
    payment = await _payment_by_booking(db, booking_id)
    if payment is None:
        raise _not_found()
    booking = payment.booking
    if booking.client_id != user.id and booking.creator_profile.user_id != user.id:
        raise _not_found()
    return payment


async def _locked_payment_and_booking(
    db: AsyncSession, payment_id: uuid.UUID
) -> tuple[Payment, Booking]:
    booking_id = await db.scalar(select(Payment.booking_id).where(Payment.id == payment_id))
    if booking_id is None:
        raise _not_found()
    booking = await db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
    if booking is None:
        raise _not_found()
    payment = await db.scalar(
        select(Payment)
        .where(Payment.id == payment_id, Payment.booking_id == booking.id)
        .with_for_update()
    )
    if payment is None:
        raise _not_found()
    return payment, booking


async def _payment_id_for_event(
    db: AsyncSession, *, provider: str, provider_event_id: str
) -> uuid.UUID | None:
    result = await db.scalars(
        select(PaymentEventModel.payment_id).where(
            PaymentEventModel.provider == provider,
            PaymentEventModel.provider_event_id == provider_event_id,
        )
    )
    return result.one_or_none()


def _event_collision() -> DomainError:
    return DomainError(
        "INVALID_PAYMENT_TRANSITION",
        "Event pembayaran sudah digunakan untuk pembayaran lain.",
        status_code=409,
    )


def _apply_transition(
    payment: Payment,
    booking: Booking,
    event: ProviderPaymentEvent,
) -> None:
    if payment.status in FINAL_PAYMENT_STATUSES:
        raise _already_final()
    now = datetime.now(UTC)
    if event.event_type == "paid":
        if payment.status != "pending" or booking.status != "awaiting_payment":
            raise _invalid_transition()
        payment.status = "held"
        payment.paid_at = now
        payment.held_at = now
        booking.status = "confirmed"
    elif event.event_type == "failed":
        if payment.status != "pending":
            raise _invalid_transition()
        payment.status = "failed"
    elif event.event_type == "refunded":
        if payment.status != "held":
            raise _invalid_transition()
        payment.status = "refunded"
        payment.refunded_at = now
    elif event.event_type == "released":
        if payment.status != "held" or booking.status != "completed":
            raise _invalid_transition()
        payment.status = "released"
        payment.released_at = now
    else:
        raise _invalid_transition()


def _normalize_provider_event(event: ProviderPaymentEvent) -> ProviderPaymentEvent:
    if event.event_type not in {"paid", "failed", "refunded", "released"}:
        raise _invalid_transition()
    provider_event_id = event.provider_event_id.strip()
    if not provider_event_id or len(provider_event_id) > 150:
        raise _invalid_transition()
    return ProviderPaymentEvent(
        provider_event_id=provider_event_id,
        event_type=event.event_type,
    )


async def _stage_locked_provider_event(
    db: AsyncSession,
    *,
    payment: Payment,
    booking: Booking,
    event: ProviderPaymentEvent,
) -> Payment:
    event = _normalize_provider_event(event)
    provider = payment.provider
    payment_id = payment.id

    event_payment_id = await _payment_id_for_event(
        db, provider=provider, provider_event_id=event.provider_event_id
    )
    if event_payment_id is not None:
        if event_payment_id != payment_id:
            raise _event_collision()
        return payment

    _apply_transition(payment, booking, event)
    db.add(
        PaymentEventModel(
            payment_id=payment.id,
            provider=provider,
            provider_event_id=event.provider_event_id,
            event_type=event.event_type,
        )
    )
    await db.flush()
    return payment


async def _persist_locked_provider_event(
    db: AsyncSession,
    *,
    payment: Payment,
    booking: Booking,
    event: ProviderPaymentEvent,
) -> Payment:
    provider = payment.provider
    payment_id = payment.id
    event = _normalize_provider_event(event)
    try:
        await _stage_locked_provider_event(
            db,
            payment=payment,
            booking=booking,
            event=event,
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        event_payment_id = await _payment_id_for_event(
            db,
            provider=provider,
            provider_event_id=event.provider_event_id,
        )
        if event_payment_id is None:
            raise
        if event_payment_id != payment_id:
            raise _event_collision() from None
        current = await _payment_by_id(db, payment_id)
        if current is None:
            raise _not_found() from None
        return current
    current = await _payment_by_id(db, payment_id)
    assert current is not None
    return current


async def require_held_payment_for_locked_booking(db: AsyncSession, booking: Booking) -> Payment:
    payment = await db.scalar(
        select(Payment).where(Payment.booking_id == booking.id).with_for_update()
    )
    if payment is None or payment.status != "held":
        raise _invalid_transition()
    return payment


async def cancel_for_locked_booking(db: AsyncSession, booking: Booking) -> Payment | None:
    payment = await db.scalar(
        select(Payment).where(Payment.booking_id == booking.id).with_for_update()
    )
    if booking.status in {"requested", "accepted"}:
        if payment is not None:
            raise _invalid_transition()
        return None
    if booking.status == "awaiting_payment":
        if payment is None:
            raise _invalid_transition()
        if payment.status == "pending":
            payment.status = "expired"
        elif payment.status != "failed":
            raise _invalid_transition()
        await db.flush()
        return payment
    if booking.status == "confirmed":
        if payment is None or payment.status != "held":
            raise _invalid_transition()
        event = await PROVIDER.refund_payment(payment.id)
        return await _stage_locked_provider_event(
            db,
            payment=payment,
            booking=booking,
            event=event,
        )
    raise _invalid_transition()


async def _apply_provider_event(
    db: AsyncSession,
    *,
    payment_id: uuid.UUID,
    event: ProviderPaymentEvent,
    user: User | None = None,
    required_role: str | None = None,
) -> Payment:
    payment, booking = await _locked_payment_and_booking(db, payment_id)
    if required_role == "client" and (user is None or booking.client_id != user.id):
        raise _not_found()
    if required_role == "creator":
        profile = None if user is None else await _creator_profile_of(db, user)
        if profile is None or booking.creator_profile_id != profile.id:
            raise _not_found()
    return await _persist_locked_provider_event(
        db,
        payment=payment,
        booking=booking,
        event=event,
    )


async def apply_webhook(
    db: AsyncSession,
    *,
    payment_id: uuid.UUID,
    event: ProviderPaymentEvent,
) -> Payment:
    return await _apply_provider_event(db, payment_id=payment_id, event=event)


async def simulate_paid(db: AsyncSession, *, payment_id: uuid.UUID, user: User) -> Payment:
    event = await PROVIDER.simulate_paid(payment_id)
    return await _apply_provider_event(
        db,
        payment_id=payment_id,
        event=event,
        user=user,
        required_role="client",
    )


async def simulate_release(db: AsyncSession, *, payment_id: uuid.UUID, user: User) -> Payment:
    payment, booking = await _locked_payment_and_booking(db, payment_id)
    profile = await _creator_profile_of(db, user)
    if profile is None or booking.creator_profile_id != profile.id:
        raise _not_found()
    if payment.status == "released":
        return payment
    if payment.status in FINAL_PAYMENT_STATUSES:
        raise _already_final()
    if payment.status != "held" or booking.status != "completed":
        raise _invalid_transition()
    event = await PROVIDER.release_payment(payment_id)
    return await _persist_locked_provider_event(
        db,
        payment=payment,
        booking=booking,
        event=event,
    )
