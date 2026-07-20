import uuid

from fastapi import APIRouter

from app.api.deps import AdminUser, DbSession
from app.api.schemas import (
    CreatorApplicationListEnvelope,
    CreatorApplicationOut,
    CreatorProfileEnvelope,
    CreatorProfileOut,
)
from app.services import profiles as profile_service

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/creator-applications", response_model=CreatorApplicationListEnvelope)
async def list_creator_applications(_: AdminUser, db: DbSession) -> CreatorApplicationListEnvelope:
    rows = await profile_service.list_pending_applications(db)
    return CreatorApplicationListEnvelope(
        data=[
            CreatorApplicationOut(
                profile=CreatorProfileOut.model_validate(profile, from_attributes=True),
                user_email=user.email,
                user_full_name=user.full_name,
            )
            for profile, user in rows
        ]
    )


@router.post("/creator-applications/{profile_id}/approve", response_model=CreatorProfileEnvelope)
async def approve_creator_application(
    profile_id: uuid.UUID, _: AdminUser, db: DbSession
) -> CreatorProfileEnvelope:
    profile = await profile_service.approve_application(db, profile_id=profile_id)
    return CreatorProfileEnvelope(
        data=CreatorProfileOut.model_validate(profile, from_attributes=True)
    )


@router.post("/creator-applications/{profile_id}/reject", response_model=CreatorProfileEnvelope)
async def reject_creator_application(
    profile_id: uuid.UUID, _: AdminUser, db: DbSession
) -> CreatorProfileEnvelope:
    profile = await profile_service.reject_application(db, profile_id=profile_id)
    return CreatorProfileEnvelope(
        data=CreatorProfileOut.model_validate(profile, from_attributes=True)
    )
