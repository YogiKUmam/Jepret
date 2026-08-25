"""Shared participant authorization for Phase 6 booking workspace domains."""

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import DomainError
from app.db.models import Booking, CreatorProfile, User


@dataclass(frozen=True)
class BookingAccess:
    booking: Booking
    role: Literal["client", "creator"]


def booking_not_found() -> DomainError:
    return DomainError("BOOKING_NOT_FOUND", "Booking tidak ditemukan.", status_code=404)


async def require_booking_participant(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    user: User,
    lock: bool = False,
) -> BookingAccess:
    if user.is_admin:
        raise booking_not_found()
    stmt = (
        select(Booking)
        .join(CreatorProfile, CreatorProfile.id == Booking.creator_profile_id)
        .where(
            Booking.id == booking_id,
            or_(
                Booking.client_id == user.id,
                CreatorProfile.user_id == user.id,
            ),
        )
        .options(selectinload(Booking.creator_profile))
    )
    if lock:
        stmt = stmt.with_for_update(of=Booking)
    booking = await db.scalar(stmt)
    if booking is None:
        raise booking_not_found()
    if booking.client_id == user.id:
        return BookingAccess(booking=booking, role="client")
    return BookingAccess(booking=booking, role="creator")
