import uuid

from fastapi import APIRouter, Query

from app.api.deps import AdminUser, DbSession
from app.api.dispute_schemas import (
    AdminOverviewEnvelope,
    DisputeEnvelope,
    DisputeListEnvelope,
    DisputeOut,
    ResolveDisputeRequest,
)
from app.api.schemas import (
    CreatorApplicationListEnvelope,
    CreatorApplicationOut,
    CreatorProfileEnvelope,
    CreatorProfileOut,
)
from app.services import admin as admin_service
from app.services import disputes as dispute_service
from app.services import profiles as profile_service

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/overview", response_model=AdminOverviewEnvelope)
async def get_admin_overview(_: AdminUser, db: DbSession) -> AdminOverviewEnvelope:
    overview = await admin_service.get_admin_overview(db)
    return AdminOverviewEnvelope(data=overview)


@router.get("/disputes", response_model=DisputeListEnvelope)
async def list_admin_disputes(
    _: AdminUser,
    db: DbSession,
    status: str | None = Query(default=None),
) -> DisputeListEnvelope:
    items = await dispute_service.list_disputes_for_admin(db, status=status)
    return DisputeListEnvelope(
        data=[
            DisputeOut(
                id=d.id,
                booking_id=d.booking_id,
                opened_by_user_id=d.opened_by_user_id,
                opened_by_full_name=d.opened_by.full_name,
                reason_category=d.reason_category,
                description=d.description,
                status=d.status,
                resolution_notes=d.resolution_notes,
                resolved_by_admin_user_id=d.resolved_by_admin_user_id,
                created_at=d.created_at,
                resolved_at=d.resolved_at,
            )
            for d in items
        ]
    )


@router.post("/disputes/{dispute_id}/resolve", response_model=DisputeEnvelope)
async def resolve_admin_dispute(
    dispute_id: uuid.UUID,
    payload: ResolveDisputeRequest,
    admin_user: AdminUser,
    db: DbSession,
) -> DisputeEnvelope:
    dispute = await dispute_service.resolve_dispute_for_admin(
        db,
        dispute_id=dispute_id,
        admin_user=admin_user,
        resolution=payload.resolution,
        resolution_notes=payload.resolution_notes,
    )
    return DisputeEnvelope(
        data=DisputeOut(
            id=dispute.id,
            booking_id=dispute.booking_id,
            opened_by_user_id=dispute.opened_by_user_id,
            opened_by_full_name=dispute.opened_by.full_name,
            reason_category=dispute.reason_category,
            description=dispute.description,
            status=dispute.status,
            resolution_notes=dispute.resolution_notes,
            resolved_by_admin_user_id=dispute.resolved_by_admin_user_id,
            created_at=dispute.created_at,
            resolved_at=dispute.resolved_at,
        )
    )


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
