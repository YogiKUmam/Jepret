"""Private upload-intent domain service."""

import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import cast

from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.workspace_schemas import (
    CanonicalContentType,
    CreateUploadRequest,
    SignedUploadOut,
    SignedUrlOut,
    UploadOut,
    UploadPurpose,
)
from app.core.config import get_settings
from app.core.errors import DomainError
from app.db.models import UploadIntent, User
from app.integrations.storage import (
    UPLOAD_IF_NONE_MATCH_HEADER,
    UPLOAD_IF_NONE_MATCH_VALUE,
    Boto3StorageAdapter,
    StorageAdapter,
    StorageValidationError,
    validate_signature,
)
from app.services.workspace_access import BookingAccess, require_booking_participant

UPLOAD_LIMITS: dict[str, tuple[int, frozenset[str]]] = {
    "chat_attachment": (
        10 * 1024 * 1024,
        frozenset({"image/jpeg", "image/png", "image/webp", "application/pdf"}),
    ),
    "deliverable": (
        100 * 1024 * 1024,
        frozenset({"image/jpeg", "image/png", "image/webp", "application/pdf", "application/zip"}),
    ),
}
UPLOAD_TTL = timedelta(minutes=10)
_CHAT_WRITABLE_STATUSES = frozenset({"confirmed", "in_progress", "delivered"})


@lru_cache(maxsize=1)
def get_storage_adapter() -> StorageAdapter:
    settings = get_settings()
    return Boto3StorageAdapter(
        internal_endpoint=str(settings.minio_endpoint),
        public_endpoint=str(settings.minio_public_endpoint),
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        bucket=settings.minio_private_bucket,
    )


def _upload_out(intent: UploadIntent) -> UploadOut:
    return UploadOut(
        id=intent.id,
        purpose=cast(UploadPurpose, intent.purpose),
        filename=intent.filename,
        content_type=cast(CanonicalContentType, intent.content_type),
        size_bytes=intent.size_bytes,
        status=cast(str, intent.status),  # type: ignore[arg-type]
        expires_at=intent.expires_at,
        completed_at=intent.completed_at,
    )


def _require_writable(purpose: str, booking_status: str, role: str) -> None:
    if purpose == "deliverable" and role != "creator":
        # Match participant-not-found semantics so role capabilities cannot be enumerated.
        raise DomainError("BOOKING_NOT_FOUND", "Booking tidak ditemukan.", status_code=404)
    allowed = booking_status in (
        frozenset({"in_progress"}) if purpose == "deliverable" else _CHAT_WRITABLE_STATUSES
    )
    if not allowed:
        raise DomainError(
            "UPLOAD_BOOKING_NOT_WRITABLE",
            "Status booking tidak memungkinkan upload ini.",
            status_code=409,
        )


def _validate_limits(payload: CreateUploadRequest) -> None:
    max_size, allowed_types = UPLOAD_LIMITS[payload.purpose]
    if payload.content_type not in allowed_types or payload.size_bytes > max_size:
        raise DomainError(
            "UPLOAD_VALIDATION_FAILED",
            "Jenis atau ukuran file tidak didukung.",
            status_code=422,
        )


def _storage_failure() -> DomainError:
    return DomainError(
        "STORAGE_UNAVAILABLE", "Penyimpanan file sedang tidak tersedia.", status_code=503
    )


def _validation_failure() -> DomainError:
    return DomainError(
        "UPLOAD_VALIDATION_FAILED", "File yang diunggah tidak valid.", status_code=422
    )


def _upload_not_found() -> DomainError:
    return DomainError("UPLOAD_NOT_FOUND", "Upload tidak ditemukan.", status_code=404)


def _is_storage_not_found(exc: ClientError) -> bool:
    code = str(exc.response.get("Error", {}).get("Code", ""))
    return code in {"404", "NoSuchKey", "NotFound", "NoSuchObject"}


async def create_intent(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    user: User,
    payload: CreateUploadRequest,
    storage: StorageAdapter,
) -> SignedUploadOut:
    access = await require_booking_participant(db, booking_id=booking_id, user=user, lock=True)
    _require_writable(payload.purpose, access.booking.status, access.role)
    _validate_limits(payload)
    intent = UploadIntent(
        booking_id=booking_id,
        requested_by_user_id=user.id,
        purpose=payload.purpose,
        object_key=f"{payload.purpose}/{booking_id}/{uuid.uuid4().hex}",
        filename=payload.filename,
        content_type=payload.content_type,
        size_bytes=payload.size_bytes,
        status="pending",
    )
    presign_ttl = min(
        get_settings().storage_signed_url_ttl_seconds, int(UPLOAD_TTL.total_seconds())
    )
    try:
        upload_url = await storage.create_upload_url(
            object_key=intent.object_key,
            content_type=intent.content_type,
            expires_seconds=presign_ttl,
        )
    except Exception as exc:
        await db.rollback()
        raise _storage_failure() from exc
    intent.expires_at = datetime.now(UTC) + UPLOAD_TTL
    db.add(intent)
    await db.commit()
    return SignedUploadOut(
        **_upload_out(intent).model_dump(),
        upload_url=upload_url,
        required_headers={
            "Content-Type": intent.content_type,
            UPLOAD_IF_NONE_MATCH_HEADER: UPLOAD_IF_NONE_MATCH_VALUE,
        },
    )


async def _locked_intent(db: AsyncSession, upload_id: uuid.UUID) -> UploadIntent:
    intent = await db.scalar(
        select(UploadIntent)
        .where(UploadIntent.id == upload_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if intent is None:
        raise _upload_not_found()
    return intent


async def _authorized_intent(
    db: AsyncSession, *, upload_id: uuid.UUID, user: User, lock: bool
) -> tuple[UploadIntent, BookingAccess]:
    # The initial unlocked lookup only discovers the booking lock target. Every
    # stateful path then locks booking before intent, matching booking workflows.
    initial_intent = await db.scalar(select(UploadIntent).where(UploadIntent.id == upload_id))
    if initial_intent is None:
        raise _upload_not_found()
    try:
        access = await require_booking_participant(
            db, booking_id=initial_intent.booking_id, user=user, lock=lock
        )
    except DomainError as exc:
        if exc.status_code == 404:
            raise _upload_not_found() from exc
        raise
    if not lock:
        return initial_intent, access
    resolved_intent = await _locked_intent(db, upload_id)
    if resolved_intent.booking_id != access.booking.id:
        raise _upload_not_found()
    return resolved_intent, access


def _require_pending(intent: UploadIntent) -> None:
    if intent.status == "completed":
        raise DomainError("UPLOAD_ALREADY_COMPLETED", "Upload sudah diselesaikan.", status_code=409)
    if intent.status == "expired":
        raise DomainError("UPLOAD_EXPIRED", "Upload sudah kedaluwarsa.", status_code=410)
    if intent.status == "rejected":
        raise DomainError("UPLOAD_REJECTED", "Upload ditolak.", status_code=409)


async def complete_intent(
    db: AsyncSession, *, upload_id: uuid.UUID, user: User, storage: StorageAdapter
) -> UploadOut:
    intent, access = await _authorized_intent(db, upload_id=upload_id, user=user, lock=True)
    if intent.requested_by_user_id != user.id:
        raise _upload_not_found()
    _require_pending(intent)
    now = datetime.now(UTC)
    expires_at = intent.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        intent.status = "expired"
        await db.commit()
        raise DomainError("UPLOAD_EXPIRED", "Upload sudah kedaluwarsa.", status_code=410)
    if intent.purpose == "deliverable" and access.role != "creator":
        raise _upload_not_found()
    _require_writable(intent.purpose, access.booking.status, access.role)
    try:
        stored = await storage.inspect_object(object_key=intent.object_key)
    except FileNotFoundError as exc:
        raise _validation_failure() from exc
    except StorageValidationError as exc:
        raise _validation_failure() from exc
    except ClientError as exc:
        if _is_storage_not_found(exc):
            raise _validation_failure() from exc
        raise _storage_failure() from exc
    except BotoCoreError as exc:
        raise _storage_failure() from exc
    except OSError as exc:
        raise _storage_failure() from exc
    if stored.size_bytes != intent.size_bytes or stored.content_type != intent.content_type:
        raise _validation_failure()
    try:
        validate_signature(intent.content_type, stored.signature)
    except StorageValidationError as exc:
        raise _validation_failure() from exc
    # Revalidate immediately before finalization while both booking and intent
    # locks are held. The bounded storage call above cannot overlap a transition.
    _require_writable(intent.purpose, access.booking.status, access.role)
    final_now = datetime.now(UTC)
    if expires_at <= final_now:
        intent.status = "expired"
        await db.commit()
        raise DomainError("UPLOAD_EXPIRED", "Upload sudah kedaluwarsa.", status_code=410)
    intent.status = "completed"
    intent.completed_at = final_now
    await db.commit()
    return _upload_out(intent)


async def authorize_download(
    db: AsyncSession, *, upload_id: uuid.UUID, user: User, storage: StorageAdapter
) -> SignedUrlOut:
    intent, _ = await _authorized_intent(db, upload_id=upload_id, user=user, lock=True)
    if intent.status == "pending":
        now = datetime.now(UTC)
        expires_at = intent.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            intent.status = "expired"
            await db.commit()
            raise DomainError("UPLOAD_EXPIRED", "Upload sudah kedaluwarsa.", status_code=410)
        raise DomainError("UPLOAD_NOT_READY", "Upload belum siap diunduh.", status_code=409)
    if intent.status == "expired":
        raise DomainError("UPLOAD_EXPIRED", "Upload sudah kedaluwarsa.", status_code=410)
    if intent.status == "rejected":
        raise DomainError("UPLOAD_REJECTED", "Upload ditolak.", status_code=409)
    try:
        url = await storage.create_download_url(
            object_key=intent.object_key,
            expires_seconds=get_settings().storage_signed_url_ttl_seconds,
        )
    except Exception as exc:
        raise _storage_failure() from exc
    return SignedUrlOut(url=url)
