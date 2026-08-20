import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.api.workspace_schemas import (
    CreateUploadRequest,
    SignedUploadEnvelope,
    SignedUrlEnvelope,
    UploadEnvelope,
)
from app.core.errors import DomainError
from app.db.session import get_session
from app.integrations.storage import StorageAdapter
from app.services import uploads as upload_service
from app.services.workspace_access import require_booking_participant

router = APIRouter(prefix="/api/v1", tags=["uploads"])
StorageDep = Annotated[StorageAdapter, Depends(upload_service.get_storage_adapter)]
AuthorizationDb = Annotated[AsyncSession, Depends(get_session, use_cache=False)]


async def enforce_upload_rate_limit(
    request: Request, booking_id: uuid.UUID, user: CurrentUser, auth_db: AuthorizationDb
) -> None:
    await require_booking_participant(auth_db, booking_id=booking_id, user=user)
    limiter = request.app.state.upload_rate_limiter
    if not await limiter.allow(f"{user.id}:{booking_id}"):
        raise DomainError("RATE_LIMITED", "Terlalu banyak permintaan.", 429)


UploadRateLimit = Annotated[None, Depends(enforce_upload_rate_limit)]


@router.post(
    "/bookings/{booking_id}/uploads",
    response_model=SignedUploadEnvelope,
    status_code=status.HTTP_201_CREATED,
)
async def create_upload(
    booking_id: uuid.UUID,
    payload: CreateUploadRequest,
    user: CurrentUser,
    db: DbSession,
    storage: StorageDep,
    _: UploadRateLimit,
) -> SignedUploadEnvelope:
    data = await upload_service.create_intent(
        db, booking_id=booking_id, user=user, payload=payload, storage=storage
    )
    return SignedUploadEnvelope(data=data)


@router.post("/uploads/{upload_id}/complete", response_model=UploadEnvelope)
async def complete_upload(
    upload_id: uuid.UUID, user: CurrentUser, db: DbSession, storage: StorageDep
) -> UploadEnvelope:
    data = await upload_service.complete_intent(db, upload_id=upload_id, user=user, storage=storage)
    return UploadEnvelope(data=data)


@router.post("/uploads/{upload_id}/download", response_model=SignedUrlEnvelope)
async def download_upload(
    upload_id: uuid.UUID, user: CurrentUser, db: DbSession, storage: StorageDep
) -> SignedUrlEnvelope:
    data = await upload_service.authorize_download(
        db, upload_id=upload_id, user=user, storage=storage
    )
    return SignedUrlEnvelope(data=data)
