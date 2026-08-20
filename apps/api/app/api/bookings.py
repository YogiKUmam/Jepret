import uuid

from fastapi import APIRouter, Request, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.api.schemas import (
    BookingCreatorOut,
    BookingEnvelope,
    BookingListEnvelope,
    BookingOut,
    CreateBookingRequest,
)
from app.db.models import Booking, Conversation
from app.realtime import safe_broadcast
from app.services import bookings as booking_service

router = APIRouter(prefix="/api/v1/bookings", tags=["bookings"])


def _booking_out(booking: Booking) -> BookingOut:
    creator = booking.creator_profile
    return BookingOut(
        id=booking.id,
        status=booking.status,
        event_date=booking.event_date,
        event_city=booking.event_city,
        notes=booking.notes,
        quoted_price_idr=booking.quoted_price_idr,
        created_at=booking.created_at,
        creator=BookingCreatorOut(
            id=creator.id,
            display_name=creator.display_name,
            city=creator.city,
            specialty=creator.specialty,
        ),
        client_name=booking.client.full_name,
    )


async def _broadcast_booking_update(
    request: Request, db: DbSession, booking: Booking, data: BookingOut
) -> None:
    conversation_id = await db.scalar(
        select(Conversation.id).where(Conversation.booking_id == booking.id)
    )
    if conversation_id is not None:
        await safe_broadcast(
            request,
            conversation_id,
            {"type": "booking.updated", "data": data.model_dump(mode="json")},
        )


@router.post("", response_model=BookingEnvelope, status_code=status.HTTP_201_CREATED)
async def create_booking(
    payload: CreateBookingRequest, user: CurrentUser, db: DbSession
) -> BookingEnvelope:
    booking = await booking_service.create_booking(
        db,
        client=user,
        creator_id=payload.creator_id,
        event_date=payload.event_date,
        event_city=payload.event_city,
        notes=payload.notes,
    )
    return BookingEnvelope(data=_booking_out(booking))


@router.get("", response_model=BookingListEnvelope)
async def list_my_bookings(user: CurrentUser, db: DbSession) -> BookingListEnvelope:
    bookings = await booking_service.list_for_client(db, client=user)
    return BookingListEnvelope(data=[_booking_out(booking) for booking in bookings])


@router.get("/incoming", response_model=BookingListEnvelope)
async def list_incoming_bookings(user: CurrentUser, db: DbSession) -> BookingListEnvelope:
    bookings = await booking_service.list_for_creator(db, user=user)
    return BookingListEnvelope(data=[_booking_out(booking) for booking in bookings])


@router.get("/{booking_id}", response_model=BookingEnvelope)
async def get_booking(booking_id: uuid.UUID, user: CurrentUser, db: DbSession) -> BookingEnvelope:
    booking = await booking_service.get_for_user(db, booking_id=booking_id, user=user)
    return BookingEnvelope(data=_booking_out(booking))


@router.post("/{booking_id}/accept", response_model=BookingEnvelope)
async def accept_booking(
    booking_id: uuid.UUID, user: CurrentUser, db: DbSession, request: Request
) -> BookingEnvelope:
    booking = await booking_service.accept_booking(db, booking_id=booking_id, user=user)
    data = _booking_out(booking)
    await _broadcast_booking_update(request, db, booking, data)
    return BookingEnvelope(data=data)


@router.post("/{booking_id}/reject", response_model=BookingEnvelope)
async def reject_booking(
    booking_id: uuid.UUID, user: CurrentUser, db: DbSession, request: Request
) -> BookingEnvelope:
    booking = await booking_service.reject_booking(db, booking_id=booking_id, user=user)
    data = _booking_out(booking)
    await _broadcast_booking_update(request, db, booking, data)
    return BookingEnvelope(data=data)


@router.post("/{booking_id}/complete", response_model=BookingEnvelope)
async def complete_booking(
    booking_id: uuid.UUID, user: CurrentUser, db: DbSession, request: Request
) -> BookingEnvelope:
    booking = await booking_service.complete_booking(db, booking_id=booking_id, user=user)
    data = _booking_out(booking)
    await _broadcast_booking_update(request, db, booking, data)
    return BookingEnvelope(data=data)


@router.post("/{booking_id}/cancel", response_model=BookingEnvelope)
async def cancel_booking(
    booking_id: uuid.UUID, user: CurrentUser, db: DbSession, request: Request
) -> BookingEnvelope:
    booking = await booking_service.cancel_booking(db, booking_id=booking_id, user=user)
    data = _booking_out(booking)
    await _broadcast_booking_update(request, db, booking, data)
    return BookingEnvelope(data=data)
