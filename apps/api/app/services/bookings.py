import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import DomainError
from app.db.models import Booking, CreatorProfile, User
from app.services import payments as payment_service

ACTIVE_STATUSES = frozenset({"requested", "accepted", "awaiting_payment", "confirmed"})
_WITH_RELATIONS = (
    selectinload(Booking.creator_profile),
    selectinload(Booking.client),
)


def _not_found() -> DomainError:
    return DomainError("NOT_FOUND", "Booking tidak ditemukan.", status_code=404)


async def _creator_profile_of(db: AsyncSession, user: User) -> CreatorProfile | None:
    result = await db.scalars(select(CreatorProfile).where(CreatorProfile.user_id == user.id))
    return result.one_or_none()


async def create_booking(
    db: AsyncSession,
    *,
    client: User,
    creator_id: uuid.UUID,
    event_date: date,
    event_city: str,
    notes: str,
) -> Booking:
    if event_date <= datetime.now(UTC).date():
        raise DomainError(
            "INVALID_EVENT_DATE", "Tanggal acara harus di masa depan.", status_code=422
        )
    creator = await db.scalar(
        select(CreatorProfile).where(
            CreatorProfile.id == creator_id, CreatorProfile.status == "approved"
        )
    )
    if creator is None:
        raise DomainError("NOT_FOUND", "Kreator tidak ditemukan.", status_code=404)
    if creator.user_id == client.id:
        raise DomainError(
            "CANNOT_BOOK_SELF", "Kamu tidak dapat memesan dirimu sendiri.", status_code=422
        )
    booking = Booking(
        client_id=client.id,
        creator_profile_id=creator.id,
        event_date=event_date,
        event_city=event_city.strip(),
        notes=notes.strip(),
        status="requested",
        quoted_price_idr=creator.starting_price_idr,
    )
    db.add(booking)
    await db.commit()
    return await get_for_user(db, booking_id=booking.id, user=client)


async def list_for_client(db: AsyncSession, *, client: User) -> Sequence[Booking]:
    stmt = (
        select(Booking)
        .where(Booking.client_id == client.id)
        .options(*_WITH_RELATIONS)
        .order_by(Booking.created_at.desc())
    )
    return list((await db.scalars(stmt)).all())


async def list_for_creator(db: AsyncSession, *, user: User) -> Sequence[Booking]:
    profile = await _creator_profile_of(db, user)
    if profile is None:
        return []
    stmt = (
        select(Booking)
        .where(Booking.creator_profile_id == profile.id)
        .options(*_WITH_RELATIONS)
        .order_by(Booking.created_at.desc())
    )
    return list((await db.scalars(stmt)).all())


async def get_for_user(db: AsyncSession, *, booking_id: uuid.UUID, user: User) -> Booking:
    booking = await db.scalar(
        select(Booking).where(Booking.id == booking_id).options(*_WITH_RELATIONS)
    )
    if booking is None:
        raise _not_found()
    if booking.client_id != user.id:
        profile = await _creator_profile_of(db, user)
        if profile is None or booking.creator_profile_id != profile.id:
            raise _not_found()
    return booking


async def _locked_booking(db: AsyncSession, booking_id: uuid.UUID) -> Booking:
    booking = await db.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
    if booking is None:
        raise _not_found()
    return booking


async def _require_creator(db: AsyncSession, booking: Booking, user: User) -> None:
    profile = await _creator_profile_of(db, user)
    if profile is None or booking.creator_profile_id != profile.id:
        raise _not_found()


def _require_status(booking: Booking, allowed: frozenset[str]) -> None:
    if booking.status not in allowed:
        raise DomainError(
            "INVALID_STATUS_TRANSITION",
            "Status booking tidak memungkinkan aksi ini.",
            status_code=409,
        )


async def _respond(
    db: AsyncSession, *, booking_id: uuid.UUID, user: User, new_status: str
) -> Booking:
    booking = await _locked_booking(db, booking_id)
    await _require_creator(db, booking, user)
    _require_status(booking, frozenset({"requested"}))
    booking.status = new_status
    booking.responded_at = datetime.now(UTC)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise DomainError(
            "DATE_UNAVAILABLE",
            "Kamu sudah menerima booking lain pada tanggal tersebut.",
            status_code=409,
        ) from exc
    return await get_for_user(db, booking_id=booking_id, user=user)


async def accept_booking(db: AsyncSession, *, booking_id: uuid.UUID, user: User) -> Booking:
    return await _respond(db, booking_id=booking_id, user=user, new_status="accepted")


async def reject_booking(db: AsyncSession, *, booking_id: uuid.UUID, user: User) -> Booking:
    return await _respond(db, booking_id=booking_id, user=user, new_status="rejected")


async def complete_booking(db: AsyncSession, *, booking_id: uuid.UUID, user: User) -> Booking:
    booking = await _locked_booking(db, booking_id)
    await _require_creator(db, booking, user)
    _require_status(booking, frozenset({"confirmed"}))
    await payment_service.require_held_payment_for_locked_booking(db, booking)
    booking.status = "completed"
    booking.completed_at = datetime.now(UTC)
    await db.commit()
    return await get_for_user(db, booking_id=booking_id, user=user)


async def cancel_booking(db: AsyncSession, *, booking_id: uuid.UUID, user: User) -> Booking:
    booking = await _locked_booking(db, booking_id)
    if booking.client_id != user.id:
        await _require_creator(db, booking, user)
    _require_status(booking, ACTIVE_STATUSES)
    await payment_service.cancel_for_locked_booking(db, booking)
    booking.status = "cancelled"
    booking.cancelled_at = datetime.now(UTC)
    await db.commit()
    return await get_for_user(db, booking_id=booking_id, user=user)
