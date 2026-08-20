import json
import uuid
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Query, Request, WebSocket, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.websockets import WebSocketDisconnect

from app.api.deps import SESSION_COOKIE, CurrentUser, DbSession
from app.api.workspace_schemas import (
    ConversationEnvelope,
    CreateMessageRequest,
    MessageEnvelope,
    MessagePageEnvelope,
    ReadReceiptEnvelope,
    UnreadEnvelope,
)
from app.core.config import get_settings
from app.core.errors import DomainError
from app.db.models import User
from app.db.session import get_engine, get_session
from app.realtime import get_connection_hub, safe_broadcast
from app.services import conversations as conversation_service
from app.services.auth import get_user_by_session_token

router = APIRouter(tags=["conversations"])
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


@router.get("/api/v1/bookings/{booking_id}/conversation", response_model=ConversationEnvelope)
async def get_booking_conversation(
    booking_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> ConversationEnvelope:
    data = await conversation_service.get_or_create_for_booking(
        db, booking_id=booking_id, user=user
    )
    return ConversationEnvelope(data=data)


@router.get("/api/v1/conversations/unread", response_model=UnreadEnvelope)
async def get_unread(user: CurrentUser, db: DbSession) -> UnreadEnvelope:
    return UnreadEnvelope(data=await conversation_service.unread_counts(db, user=user))


@router.get("/api/v1/conversations/{conversation_id}/messages", response_model=MessagePageEnvelope)
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
    "/api/v1/conversations/{conversation_id}/messages",
    response_model=MessageEnvelope,
    status_code=status.HTTP_201_CREATED,
)
async def post_message(
    conversation_id: uuid.UUID,
    payload: CreateMessageRequest,
    user: CurrentUser,
    db: DbSession,
    _: MessageRateLimit,
    request: Request,
) -> MessageEnvelope:
    data, created = await conversation_service.create_message(
        db,
        conversation_id=conversation_id,
        user=user,
        client_message_id=payload.client_message_id,
        message_type=payload.message_type,
        body=payload.body,
        upload_id=payload.upload_id,
    )
    response = MessageEnvelope(data=data)
    if created:
        await safe_broadcast(
            request,
            conversation_id,
            {"type": "message.created", "data": data.model_dump(mode="json")},
        )
    return response


@router.post("/api/v1/conversations/{conversation_id}/read", response_model=ReadReceiptEnvelope)
async def post_read(
    conversation_id: uuid.UUID, user: CurrentUser, db: DbSession, request: Request
) -> ReadReceiptEnvelope:
    data = await conversation_service.mark_read(db, conversation_id=conversation_id, user=user)
    response = ReadReceiptEnvelope(data=data)
    await safe_broadcast(
        request,
        conversation_id,
        {"type": "message.read", "data": data.model_dump(mode="json")},
    )
    return response


def _normalized_origin(value: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            return None
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return None
    return parsed.scheme.lower(), parsed.hostname.lower(), port


def _valid_websocket_origin(websocket: WebSocket) -> bool:
    supplied = websocket.headers.get("origin")
    if supplied is None:
        return False
    expected = _normalized_origin(str(get_settings().public_origin))
    return expected is not None and _normalized_origin(supplied) == expected


async def _websocket_user(websocket: WebSocket) -> User | None:
    token = websocket.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with factory() as db:
        return await get_user_by_session_token(db, token=token)


async def _authorize_websocket(websocket: WebSocket, conversation_id: uuid.UUID) -> bool:
    if not _valid_websocket_origin(websocket):
        await _deny_websocket(websocket, code=4403)
        return False
    user = await _websocket_user(websocket)
    if user is None:
        await _deny_websocket(websocket, code=4401)
        return False
    factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    try:
        async with factory() as db:
            await conversation_service.require_conversation_participant(
                db, conversation_id=conversation_id, user=user
            )
    except DomainError:
        await _deny_websocket(websocket, code=4403)
        return False
    return True


async def _deny_websocket(websocket: WebSocket, *, code: int) -> None:
    await websocket.accept()
    await websocket.close(code=code)


@router.websocket("/ws/conversations/{conversation_id}")
async def conversation_websocket(websocket: WebSocket, conversation_id: uuid.UUID) -> None:
    if not await _authorize_websocket(websocket, conversation_id):
        return
    hub = get_connection_hub(websocket)
    await hub.connect(conversation_id, websocket)
    registered = True
    try:
        while True:
            frame = await websocket.receive()
            if frame["type"] == "websocket.disconnect":
                return
            raw = frame.get("text")
            if raw is None:
                await hub.disconnect_and_close(conversation_id, websocket, code=1003)
                registered = False
                return
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                await hub.disconnect_and_close(conversation_id, websocket, code=1003)
                registered = False
                return
            if payload != {"type": "ping"}:
                await hub.disconnect_and_close(conversation_id, websocket, code=1003)
                registered = False
                return
            if not await hub.send_to(conversation_id, websocket, {"type": "pong"}):
                registered = False
                return
    except WebSocketDisconnect:
        pass
    finally:
        if registered:
            await hub.disconnect(conversation_id, websocket)
