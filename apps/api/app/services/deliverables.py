"""Private booking deliverable domain service."""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import cast
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.workspace_schemas import CreateDeliverableRequest, DeliverableOut
from app.core.errors import DomainError
from app.db.models import Conversation, Deliverable, UploadIntent, User
from app.integrations.storage import StorageAdapter
from app.services.workspace_access import require_booking_participant

logger = logging.getLogger(__name__)
_UPLOAD_UNIQUE_CONSTRAINT = "deliverables_upload_id_key"
_PRIVATE_CLEANUP_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class DeliverableMutation:
    data: DeliverableOut
    conversation_id: uuid.UUID | None


@dataclass(frozen=True)
class DeliverableDeletion:
    booking_id: uuid.UUID
    deliverable_id: uuid.UUID
    conversation_id: uuid.UUID | None
    upload_id: uuid.UUID | None
    object_key: str | None


def _not_found() -> DomainError:
    return DomainError("DELIVERABLE_NOT_FOUND", "Hasil tidak ditemukan.", 404)


def _upload_not_found() -> DomainError:
    return DomainError("UPLOAD_NOT_FOUND", "Upload tidak ditemukan.", 404)


def _has_revisions() -> DomainError:
    return DomainError(
        "DELIVERABLE_HAS_REVISIONS",
        "Hasil yang sudah memiliki revisi tidak dapat dihapus.",
        409,
    )


def _require_creator(role: str) -> None:
    if role != "creator":
        raise _not_found()


def _require_writable(status: str) -> None:
    if status != "in_progress":
        raise DomainError(
            "DELIVERABLE_BOOKING_NOT_WRITABLE",
            "Status booking tidak memungkinkan perubahan hasil.",
            409,
        )


def _out(value: Deliverable) -> DeliverableOut:
    external_host = None
    if value.external_url is not None:
        external_host = urlsplit(value.external_url).hostname
    return DeliverableOut(
        id=value.id,
        booking_id=value.booking_id,
        uploaded_by_user_id=value.uploaded_by_user_id,
        title=value.title,
        description=value.description,
        source_type=cast(str, value.source_type),  # type: ignore[arg-type]
        upload_id=value.upload_id,
        external_url=value.external_url,
        external_host=external_host,
        media_type=value.media_type,
        filename=value.filename,
        content_type=value.content_type,
        size_bytes=value.size_bytes,
        replaces_deliverable_id=value.replaces_deliverable_id,
        downloadable=value.source_type == "private_file" and value.upload_id is not None,
        created_at=value.created_at,
    )


def _constraint_name(exc: IntegrityError) -> str | None:
    original = exc.orig
    name = getattr(original, "constraint_name", None)
    if isinstance(name, str):
        return name
    diagnostic = getattr(original, "diag", None)
    name = getattr(diagnostic, "constraint_name", None)
    return name if isinstance(name, str) else None


async def _conversation_id(db: AsyncSession, booking_id: uuid.UUID) -> uuid.UUID | None:
    return await db.scalar(select(Conversation.id).where(Conversation.booking_id == booking_id))


async def list_deliverables(
    db: AsyncSession, *, booking_id: uuid.UUID, user: User
) -> list[DeliverableOut]:
    await require_booking_participant(db, booking_id=booking_id, user=user)
    rows = (
        await db.scalars(
            select(Deliverable)
            .where(Deliverable.booking_id == booking_id)
            .order_by(Deliverable.created_at, Deliverable.id)
        )
    ).all()
    return [_out(row) for row in rows]


async def create_deliverable(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    user: User,
    payload: CreateDeliverableRequest,
) -> DeliverableMutation:
    access = await require_booking_participant(db, booking_id=booking_id, user=user, lock=True)
    _require_creator(access.role)
    _require_writable(access.booking.status)

    if payload.replaces_deliverable_id is not None:
        prior = await db.scalar(
            select(Deliverable)
            .where(Deliverable.id == payload.replaces_deliverable_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if prior is None or prior.booking_id != booking_id or prior.uploaded_by_user_id != user.id:
            await db.rollback()
            raise _not_found()

    upload: UploadIntent | None = None
    external_url: str | None = None
    if payload.source_type == "private_file":
        upload = await db.scalar(
            select(UploadIntent)
            .where(UploadIntent.id == payload.upload_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            upload is None
            or upload.booking_id != booking_id
            or upload.requested_by_user_id != user.id
            or upload.purpose != "deliverable"
            or upload.status != "completed"
        ):
            await db.rollback()
            raise _upload_not_found()
        consumed = await db.scalar(select(Deliverable.id).where(Deliverable.upload_id == upload.id))
        if consumed is not None:
            await db.rollback()
            raise DomainError("UPLOAD_ALREADY_USED", "Upload sudah digunakan.", 409)
    else:
        external_url = str(payload.external_url)

    value = Deliverable(
        booking_id=booking_id,
        uploaded_by_user_id=user.id,
        title=payload.title,
        description=payload.description,
        source_type=payload.source_type,
        upload_id=upload.id if upload is not None else None,
        external_url=external_url,
        media_type=upload.content_type.split("/", 1)[0] if upload is not None else None,
        filename=upload.filename if upload is not None else None,
        content_type=upload.content_type if upload is not None else None,
        size_bytes=upload.size_bytes if upload is not None else None,
        replaces_deliverable_id=payload.replaces_deliverable_id,
    )
    try:
        async with db.begin_nested():
            db.add(value)
            await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if upload is not None and _constraint_name(exc) == _UPLOAD_UNIQUE_CONSTRAINT:
            raise DomainError("UPLOAD_ALREADY_USED", "Upload sudah digunakan.", 409) from exc
        raise
    conversation_id = await _conversation_id(db, booking_id)
    await db.refresh(value)
    data = _out(value)
    await db.commit()
    return DeliverableMutation(data=data, conversation_id=conversation_id)


async def delete_deliverable(
    db: AsyncSession,
    *,
    deliverable_id: uuid.UUID,
    user: User,
) -> DeliverableDeletion:
    initial = await db.scalar(select(Deliverable).where(Deliverable.id == deliverable_id))
    if initial is None:
        raise _not_found()
    try:
        access = await require_booking_participant(
            db, booking_id=initial.booking_id, user=user, lock=True
        )
    except DomainError as exc:
        if exc.status_code == 404:
            raise _not_found() from exc
        raise
    _require_creator(access.role)
    _require_writable(access.booking.status)
    value = await db.scalar(
        select(Deliverable)
        .where(Deliverable.id == deliverable_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if value is None or value.booking_id != access.booking.id:
        await db.rollback()
        raise _not_found()
    replacement_id = await db.scalar(
        select(Deliverable.id).where(Deliverable.replaces_deliverable_id == value.id).limit(1)
    )
    if replacement_id is not None:
        await db.rollback()
        raise _has_revisions()

    upload_id: uuid.UUID | None = None
    object_key: str | None = None
    if value.upload_id is not None:
        upload = await db.scalar(
            select(UploadIntent)
            .where(UploadIntent.id == value.upload_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if upload is None or upload.booking_id != value.booking_id:
            await db.rollback()
            raise _not_found()
        upload_id = upload.id
        object_key = upload.object_key
        upload.status = "rejected"
    booking_id = value.booking_id
    conversation_id = await _conversation_id(db, booking_id)
    await db.delete(value)
    await db.commit()

    return DeliverableDeletion(
        booking_id=booking_id,
        deliverable_id=deliverable_id,
        conversation_id=conversation_id,
        upload_id=upload_id,
        object_key=object_key,
    )


async def _cleanup_private_object(
    storage: StorageAdapter, *, deletion: DeliverableDeletion
) -> None:
    if deletion.object_key is None or deletion.upload_id is None:
        return
    try:
        async with asyncio.timeout(_PRIVATE_CLEANUP_TIMEOUT_SECONDS):
            await storage.delete_object(object_key=deletion.object_key)
    except Exception as exc:
        logger.warning(
            "Private deliverable storage cleanup requires maintenance "
            "deliverable_id=%s upload_id=%s failure_class=%s",
            deletion.deliverable_id,
            deletion.upload_id,
            type(exc).__name__,
        )


async def cleanup_deleted_object(storage: StorageAdapter, *, deletion: DeliverableDeletion) -> None:
    if deletion.object_key is None or deletion.upload_id is None:
        return
    cleanup = asyncio.create_task(_cleanup_private_object(storage, deletion=deletion))
    try:
        await asyncio.shield(cleanup)
    except asyncio.CancelledError:
        await asyncio.shield(cleanup)
        raise
