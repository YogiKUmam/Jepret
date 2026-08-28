"""Durable booking conversation domain service."""

import base64
import binascii
import json
import unicodedata
import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.workspace_schemas import (
    AttachmentOut,
    ConversationOut,
    MessageOut,
    MessagePageOut,
    MessageSenderOut,
    ReadReceiptOut,
    UnreadCountOut,
)
from app.core.errors import DomainError
from app.db.models import Booking, Conversation, CreatorProfile, Message, UploadIntent, User
from app.services.workspace_access import require_booking_participant

_ACTIVE = frozenset({"confirmed", "in_progress", "delivered", "disputed"})
_TERMINAL = frozenset({"completed", "cancelled"})


def _conversation_not_found() -> DomainError:
    return DomainError("CONVERSATION_NOT_FOUND", "Percakapan tidak ditemukan.", 404)


def _conversation_out(value: Conversation) -> ConversationOut:
    return ConversationOut(id=value.id, booking_id=value.booking_id, created_at=value.created_at)


def _message_out(value: Message) -> MessageOut:
    attachment = None
    if value.upload_id is not None:
        attachment = AttachmentOut(
            id=value.upload_id,
            filename=value.attachment_filename or "",
            content_type=value.attachment_content_type or "application/octet-stream",
            size_bytes=value.attachment_size_bytes or 0,
        )
    return MessageOut(
        id=value.id,
        client_message_id=value.client_message_id,
        message_type=value.message_type,  # type: ignore[arg-type]
        body=value.body,
        attachment=attachment,
        sender=MessageSenderOut(id=value.sender.id, full_name=value.sender.full_name),
        read_at=value.read_at,
        created_at=value.created_at,
    )


async def get_or_create_for_booking(
    db: AsyncSession, *, booking_id: uuid.UUID, user: User
) -> ConversationOut | None:
    access = await require_booking_participant(db, booking_id=booking_id, user=user, lock=True)
    existing = await db.scalar(select(Conversation).where(Conversation.booking_id == booking_id))
    if existing is not None:
        await db.commit()
        return _conversation_out(existing)
    if access.booking.status not in _ACTIVE:
        await db.rollback()
        return None
    conversation = Conversation(booking_id=booking_id)
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return _conversation_out(conversation)


async def _authorized_conversation(
    db: AsyncSession, *, conversation_id: uuid.UUID, user: User, lock: bool = False
) -> tuple[Conversation, Booking]:
    if user.is_admin:
        raise _conversation_not_found()
    stmt = (
        select(Conversation)
        .join(Conversation.booking)
        .join(Booking.creator_profile)
        .where(
            Conversation.id == conversation_id,
            or_(Booking.client_id == user.id, CreatorProfile.user_id == user.id),
        )
    )
    conversation = await db.scalar(stmt.options(joinedload(Conversation.booking)))
    if conversation is None:
        raise _conversation_not_found()
    if lock:
        access = await require_booking_participant(
            db, booking_id=conversation.booking_id, user=user, lock=True
        )
        await db.refresh(access.booking)
        resolved = await db.scalar(
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .with_for_update(of=Conversation)
            .options(joinedload(Conversation.booking))
        )
        if resolved is None or resolved.booking_id != access.booking.id:
            raise _conversation_not_found()
        return resolved, access.booking
    return conversation, conversation.booking


async def require_conversation_participant(
    db: AsyncSession, *, conversation_id: uuid.UUID, user: User
) -> None:
    await _authorized_conversation(db, conversation_id=conversation_id, user=user)


def encode_cursor(created_at: datetime, message_id: uuid.UUID) -> str:
    timestamp = created_at.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    raw = json.dumps(
        {"v": 1, "created_at": timestamp, "id": str(message_id)}, separators=(",", ":")
    )
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw_bytes = base64.b64decode(padded, altchars=b"-_", validate=True)
        if base64.urlsafe_b64encode(raw_bytes).decode().rstrip("=") != cursor:
            raise ValueError("non-canonical cursor")
        value = json.loads(raw_bytes)
        if not isinstance(value, dict) or set(value) != {"v", "created_at", "id"}:
            raise ValueError("invalid cursor payload")
        version = value["v"]
        timestamp_raw = value["created_at"]
        identifier_raw = value["id"]
        if type(version) is not int or version != 1:
            raise ValueError("invalid cursor version")
        if type(timestamp_raw) is not str or not timestamp_raw.endswith("Z"):
            raise ValueError("invalid timestamp")
        if type(identifier_raw) is not str:
            raise ValueError("invalid UUID")
        timestamp = datetime.fromisoformat(timestamp_raw[:-1] + "+00:00")
        if timestamp.tzinfo is None or timestamp.utcoffset() != datetime.now(UTC).utcoffset():
            raise ValueError("timestamp must be UTC")
        canonical_timestamp = (
            timestamp.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
        )
        if timestamp_raw != canonical_timestamp:
            raise ValueError("non-canonical timestamp")
        identifier = uuid.UUID(identifier_raw)
        if str(identifier) != identifier_raw:
            raise ValueError("non-canonical UUID")
        return timestamp, identifier
    except (
        ValueError,
        OverflowError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        binascii.Error,
    ) as exc:
        raise DomainError("INVALID_CURSOR", "Cursor tidak valid.", 422) from exc


async def list_messages(
    db: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user: User,
    cursor: str | None,
    limit: int,
) -> MessagePageOut:
    await _authorized_conversation(db, conversation_id=conversation_id, user=user)
    stmt = select(Message).where(Message.conversation_id == conversation_id)
    if cursor is not None:
        created_at, message_id = decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Message.created_at > created_at,
                and_(Message.created_at == created_at, Message.id > message_id),
            )
        )
    rows = list(
        (
            await db.scalars(
                stmt.options(joinedload(Message.sender))
                .order_by(Message.created_at, Message.id)
                .limit(limit + 1)
            )
        ).all()
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = encode_cursor(page[-1].created_at, page[-1].id) if has_more else None
    return MessagePageOut(items=[_message_out(row) for row in page], next_cursor=next_cursor)


def _normalize_input(
    message_type: str, body: str | None, upload_id: uuid.UUID | None
) -> tuple[str | None, uuid.UUID | None]:
    if message_type == "text":
        if upload_id is not None or body is None:
            raise DomainError("MESSAGE_VALIDATION_FAILED", "Pesan tidak valid.", 422)
        if any(
            character == "\x00" or unicodedata.category(character) == "Cs" for character in body
        ):
            raise DomainError("MESSAGE_VALIDATION_FAILED", "Pesan tidak valid.", 422)
        normalized = unicodedata.normalize("NFKC", body).strip()
        if (
            not normalized
            or len(normalized) > 2000
            or any(
                character == "\x00" or unicodedata.category(character) == "Cs"
                for character in normalized
            )
        ):
            raise DomainError("MESSAGE_VALIDATION_FAILED", "Pesan tidak valid.", 422)
        return normalized, None
    if message_type == "attachment" and body is None and upload_id is not None:
        return None, upload_id
    raise DomainError("MESSAGE_VALIDATION_FAILED", "Pesan tidak valid.", 422)


def _constraint_name(error: IntegrityError) -> str | None:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        name = getattr(current, "constraint_name", None)
        if isinstance(name, str):
            return name
        current = current.__cause__ or current.__context__
    return None


def _matches_request(
    message: Message,
    *,
    message_type: str,
    body: str | None,
    upload_id: uuid.UUID | None,
    attachment: UploadIntent | None = None,
) -> bool:
    if (
        message.message_type != message_type
        or message.body != body
        or message.upload_id != upload_id
    ):
        return False
    if attachment is None:
        return True
    return (
        message.attachment_filename == attachment.filename
        and message.attachment_content_type == attachment.content_type
        and message.attachment_size_bytes == attachment.size_bytes
    )


async def create_message(
    db: AsyncSession,
    *,
    conversation_id: uuid.UUID,
    user: User,
    client_message_id: uuid.UUID,
    message_type: str,
    body: str | None,
    upload_id: uuid.UUID | None,
) -> tuple[MessageOut, bool]:
    normalized_body, normalized_upload = _normalize_input(message_type, body, upload_id)
    _, booking = await _authorized_conversation(
        db, conversation_id=conversation_id, user=user, lock=True
    )
    existing = await db.scalar(
        select(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.sender_user_id == user.id,
            Message.client_message_id == client_message_id,
        )
        .options(joinedload(Message.sender))
    )
    if existing is not None:
        same = _matches_request(
            existing,
            message_type=message_type,
            body=normalized_body,
            upload_id=normalized_upload,
        )
        if not same:
            await db.rollback()
            raise DomainError("IDEMPOTENCY_CONFLICT", "ID pesan sudah digunakan.", 409)
        output = _message_out(existing)
        await db.rollback()
        return output, False
    if booking.status not in _ACTIVE:
        await db.rollback()
        raise DomainError("CONVERSATION_READ_ONLY", "Percakapan hanya dapat dibaca.", 409)
    attachment: UploadIntent | None = None
    if normalized_upload is not None:
        attachment = await db.scalar(
            select(UploadIntent).where(UploadIntent.id == normalized_upload).with_for_update()
        )
        if (
            attachment is None
            or attachment.booking_id != booking.id
            or attachment.requested_by_user_id != user.id
            or attachment.purpose != "chat_attachment"
            or attachment.status != "completed"
        ):
            await db.rollback()
            raise DomainError("UPLOAD_NOT_FOUND", "Upload tidak ditemukan.", 404)
        consumed = await db.scalar(select(Message.id).where(Message.upload_id == normalized_upload))
        if consumed is not None:
            await db.rollback()
            raise DomainError("UPLOAD_ALREADY_USED", "Upload sudah digunakan.", 409)
    message = Message(
        conversation_id=conversation_id,
        sender_user_id=user.id,
        client_message_id=client_message_id,
        message_type=message_type,
        body=normalized_body,
        upload_id=normalized_upload,
        attachment_filename=attachment.filename if attachment else None,
        attachment_content_type=attachment.content_type if attachment else None,
        attachment_size_bytes=attachment.size_bytes if attachment else None,
    )
    try:
        async with db.begin_nested():
            db.add(message)
            await db.flush()
    except IntegrityError as exc:
        constraint = _constraint_name(exc)
        if constraint == "uq_message_client_id":
            winner = await db.scalar(
                select(Message)
                .where(
                    Message.conversation_id == conversation_id,
                    Message.sender_user_id == user.id,
                    Message.client_message_id == client_message_id,
                )
                .options(joinedload(Message.sender))
            )
            if winner is None:
                raise
            if not _matches_request(
                winner,
                message_type=message_type,
                body=normalized_body,
                upload_id=normalized_upload,
                attachment=attachment,
            ):
                await db.rollback()
                raise DomainError("IDEMPOTENCY_CONFLICT", "ID pesan sudah digunakan.", 409) from exc
            output = _message_out(winner)
            await db.commit()
            return output, False
        if constraint == "messages_upload_id_key":
            await db.rollback()
            raise DomainError("UPLOAD_ALREADY_USED", "Upload sudah digunakan.", 409) from exc
        raise
    await db.commit()
    resolved_message = await db.scalar(
        select(Message).where(Message.id == message.id).options(joinedload(Message.sender))
    )
    assert resolved_message is not None
    return _message_out(resolved_message), True


async def mark_read(db: AsyncSession, *, conversation_id: uuid.UUID, user: User) -> ReadReceiptOut:
    await _authorized_conversation(db, conversation_id=conversation_id, user=user)
    now = datetime.now(UTC)
    result = await db.execute(
        update(Message)
        .where(
            Message.conversation_id == conversation_id,
            Message.sender_user_id != user.id,
            Message.read_at.is_(None),
        )
        .values(read_at=now)
    )
    await db.commit()
    return ReadReceiptOut(count=result.rowcount, read_at=now)  # type: ignore[attr-defined]


async def unread_counts(db: AsyncSession, *, user: User) -> list[UnreadCountOut]:
    if user.is_admin:
        raise _conversation_not_found()
    rows = (
        await db.execute(
            select(Conversation.booking_id, func.count(Message.id))
            .join(Conversation.booking)
            .join(Booking.creator_profile)
            .join(Message, Message.conversation_id == Conversation.id)
            .where(
                or_(Booking.client_id == user.id, CreatorProfile.user_id == user.id),
                Message.sender_user_id != user.id,
                Message.read_at.is_(None),
            )
            .group_by(Conversation.booking_id)
            .order_by(Conversation.booking_id)
        )
    ).all()
    return [UnreadCountOut(booking_id=booking_id, count=count) for booking_id, count in rows]
