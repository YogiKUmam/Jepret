import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.api.workspace_schemas import (
    ConversationEnvelope,
    CreateMessageRequest,
    MessageEnvelope,
    MessagePageEnvelope,
    ReadReceiptEnvelope,
    UnreadEnvelope,
)
from app.core.errors import DomainError
from app.db.session import get_session
from app.services import conversations as conversation_service

router = APIRouter(prefix="/api/v1", tags=["conversations"])
AuthorizationDb = Annotated[AsyncSession, Depends(get_session, use_cache=False)]


async def enforce_message_rate_limit(
    request: Request,
    conversation_id: uuid.UUID,
    user: CurrentUser,
    auth_db: AuthorizationDb,
) -> None:
    await conversation_service.require_conversation_participant(
        auth_db, conversation_id=conversation_id, user=user
    )
    limiter = request.app.state.message_rate_limiter
    if not await limiter.allow(f"{user.id}:{conversation_id}"):
        raise DomainError("RATE_LIMITED", "Terlalu banyak permintaan.", 429)


MessageRateLimit = Annotated[None, Depends(enforce_message_rate_limit)]


@router.get("/bookings/{booking_id}/conversation", response_model=ConversationEnvelope)
async def get_booking_conversation(
    booking_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> ConversationEnvelope:
    data = await conversation_service.get_or_create_for_booking(
        db, booking_id=booking_id, user=user
    )
    return ConversationEnvelope(data=data)


@router.get("/conversations/unread", response_model=UnreadEnvelope)
async def get_unread(user: CurrentUser, db: DbSession) -> UnreadEnvelope:
    return UnreadEnvelope(data=await conversation_service.unread_counts(db, user=user))


@router.get("/conversations/{conversation_id}/messages", response_model=MessagePageEnvelope)
async def get_messages(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    cursor: str | None = Query(default=None, max_length=500),
    limit: int = Query(default=50, ge=1, le=100),
) -> MessagePageEnvelope:
    return MessagePageEnvelope(
        data=await conversation_service.list_messages(
            db, conversation_id=conversation_id, user=user, cursor=cursor, limit=limit
        )
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageEnvelope,
    status_code=status.HTTP_201_CREATED,
)
async def post_message(
    conversation_id: uuid.UUID,
    payload: CreateMessageRequest,
    user: CurrentUser,
    db: DbSession,
    _: MessageRateLimit,
) -> MessageEnvelope:
    data, _created = await conversation_service.create_message(
        db,
        conversation_id=conversation_id,
        user=user,
        client_message_id=payload.client_message_id,
        message_type=payload.message_type,
        body=payload.body,
        upload_id=payload.upload_id,
    )
    return MessageEnvelope(data=data)


@router.post("/conversations/{conversation_id}/read", response_model=ReadReceiptEnvelope)
async def post_read(
    conversation_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> ReadReceiptEnvelope:
    return ReadReceiptEnvelope(
        data=await conversation_service.mark_read(db, conversation_id=conversation_id, user=user)
    )
