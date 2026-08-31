import uuid

from fastapi import APIRouter, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, DbSession
from app.api.schemas import (
    BookingCreatorOut,
    BookingEnvelope,
    BookingListEnvelope,
    BookingOut,
    CreateBookingRequest,
)
from app.api.workspace_schemas import (
    WorkspaceBookingOut,
    WorkspaceEnvelope,
    WorkspaceOut,
    WorkspacePaymentOut,
)
from app.db.models import Booking, Conversation, CreatorProfile, Deliverable, Message, Payment
from app.realtime import safe_broadcast
from app.services import bookings as booking_service
from app.services.conversations import _conversation_out
from app.services.deliverables import _out as _deliverable_out
from app.services.workspace_access import booking_not_found, require_booking_participant

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
        started_at=booking.started_at,
        delivered_at=booking.delivered_at,
        completed_at=booking.completed_at,
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


async def _broadcast_lifecycle(
    request: Request, db: DbSession, mutation: booking_service.LifecycleMutation
) -> BookingOut:
    data = _booking_out(mutation.booking)
    if not mutation.changed:
        return data
    await _broadcast_booking_update(request, db, mutation.booking, data)
    if mutation.conversation_id is not None and mutation.message is not None:
        await safe_broadcast(
            request,
            mutation.conversation_id,
            {"type": "message.created", "data": mutation.message.model_dump(mode="json")},
        )
    return data


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


@router.get("/{booking_id}/workspace", response_model=WorkspaceEnvelope)
async def get_booking_workspace(
    booking_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> WorkspaceEnvelope:
    _ACTIVE_STATUSES = frozenset({"confirmed", "in_progress", "delivered", "disputed"})
    access = await require_booking_participant(
        db,
        booking_id=booking_id,
        user=user,
        lock=False,
    )
    unread_count = (
        select(func.count(Message.id))
        .where(
            Message.conversation_id == Conversation.id,
            Message.sender_user_id != user.id,
            Message.read_at.is_(None),
        )
        .correlate(Conversation)
        .scalar_subquery()
    )
    rows = (
        await db.execute(
            select(Booking, Conversation, Deliverable, Payment, unread_count)
            .join(CreatorProfile, CreatorProfile.id == Booking.creator_profile_id)
            .outerjoin(Conversation, Conversation.booking_id == Booking.id)
            .outerjoin(Deliverable, Deliverable.booking_id == Booking.id)
            .outerjoin(Payment, Payment.booking_id == Booking.id)
            .where(
                Booking.id == booking_id,
                or_(
                    Booking.client_id == user.id,
                    CreatorProfile.user_id == user.id,
                ),
            )
            .options(joinedload(Booking.client), joinedload(Booking.creator_profile))
            .order_by(
                Deliverable.created_at.asc().nulls_last(),
                Deliverable.id.asc().nulls_last(),
            )
        )
    ).all()
    if not rows:
        raise booking_not_found()
    booking, conversation, _, payment, count = rows[0]

    # Auto-create conversation on first workspace access for active bookings
    if conversation is None and access.booking.status in _ACTIVE_STATUSES:
        conversation = Conversation(booking_id=booking_id)
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)

    public_booking = _booking_out(booking)
    deliverables = [_deliverable_out(row[2]) for row in rows if row[2] is not None]
    payment_summary = None
    if payment is not None:
        payment_summary = WorkspacePaymentOut(
            id=payment.id,
            status=payment.status,  # type: ignore[arg-type]
            amount_idr=payment.amount_idr,
            platform_fee_idr=payment.platform_fee_idr,
            creator_net_idr=payment.creator_net_idr,
            paid_at=payment.paid_at,
            held_at=payment.held_at,
            released_at=payment.released_at,
            refunded_at=payment.refunded_at,
        )
    return WorkspaceEnvelope(
        data=WorkspaceOut(
            role=access.role,
            booking=WorkspaceBookingOut(**public_booking.model_dump()),
            conversation=_conversation_out(conversation) if conversation is not None else None,
            deliverables=deliverables,
            unread_count=int(count or 0),
            payment=payment_summary,
        )
    )


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
    mutation = await booking_service.complete_booking(db, booking_id=booking_id, user=user)
    data = await _broadcast_lifecycle(request, db, mutation)
    return BookingEnvelope(data=data)


@router.post("/{booking_id}/start", response_model=BookingEnvelope)
async def start_booking(
    booking_id: uuid.UUID, user: CurrentUser, db: DbSession, request: Request
) -> BookingEnvelope:
    mutation = await booking_service.start_booking(db, booking_id=booking_id, user=user)
    return BookingEnvelope(data=await _broadcast_lifecycle(request, db, mutation))


@router.post("/{booking_id}/deliver", response_model=BookingEnvelope)
async def deliver_booking(
    booking_id: uuid.UUID, user: CurrentUser, db: DbSession, request: Request
) -> BookingEnvelope:
    mutation = await booking_service.deliver_booking(db, booking_id=booking_id, user=user)
    return BookingEnvelope(data=await _broadcast_lifecycle(request, db, mutation))


@router.post("/{booking_id}/cancel", response_model=BookingEnvelope)
async def cancel_booking(
    booking_id: uuid.UUID, user: CurrentUser, db: DbSession, request: Request
) -> BookingEnvelope:
    booking = await booking_service.cancel_booking(db, booking_id=booking_id, user=user)
    data = _booking_out(booking)
    await _broadcast_booking_update(request, db, booking, data)
    return BookingEnvelope(data=data)
