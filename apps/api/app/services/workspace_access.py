"""Shared participant authorization for Phase 6 booking workspace domains."""

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import DomainError
from app.db.models import Booking, User


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
    stmt = select(Booking).where(Booking.id == booking_id)
    if lock:
        stmt = stmt.with_for_update()
    booking = await db.scalar(stmt.options(selectinload(Booking.creator_profile)))
    if booking is None:
        raise booking_not_found()
    if booking.client_id == user.id:
        return BookingAccess(booking=booking, role="client")
    if booking.creator_profile.user_id == user.id:
        return BookingAccess(booking=booking, role="creator")
    raise booking_not_found()
