import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.api.dispute_schemas import CreateDisputeRequest, DisputeEnvelope, DisputeOut
from app.services import disputes as dispute_service

router = APIRouter(tags=["disputes"])


@router.post("/api/v1/bookings/{booking_id}/disputes", response_model=DisputeEnvelope)
async def open_booking_dispute(
    booking_id: uuid.UUID,
    payload: CreateDisputeRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> DisputeEnvelope:
    dispute = await dispute_service.open_booking_dispute(
        db,
        booking_id=booking_id,
        client_user=current_user,
        reason_category=payload.reason_category,
        description=payload.description,
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


@router.get("/api/v1/bookings/{booking_id}/dispute", response_model=DisputeEnvelope)
async def get_booking_dispute(
    booking_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> DisputeEnvelope:
    dispute = await dispute_service.get_booking_dispute(
        db,
        booking_id=booking_id,
        user=current_user,
    )
    if not dispute:
        return DisputeEnvelope(data=None)

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
