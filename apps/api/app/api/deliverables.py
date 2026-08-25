import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Request, Response, status

from app.api.deps import CurrentUser, DbSession
from app.api.workspace_schemas import (
    CreateDeliverableRequest,
    DeliverableEnvelope,
    DeliverableListEnvelope,
)
from app.integrations.storage import StorageAdapter
from app.realtime import safe_broadcast
from app.services import deliverables as deliverable_service
from app.services.uploads import get_storage_adapter

router = APIRouter(prefix="/api/v1", tags=["deliverables"])
StorageDep = Annotated[StorageAdapter, Depends(get_storage_adapter)]


@router.get(
    "/bookings/{booking_id}/deliverables",
    response_model=DeliverableListEnvelope,
)
async def get_deliverables(
    booking_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> DeliverableListEnvelope:
    return DeliverableListEnvelope(
        data=await deliverable_service.list_deliverables(db, booking_id=booking_id, user=user)
    )


@router.post(
    "/bookings/{booking_id}/deliverables",
    response_model=DeliverableEnvelope,
    status_code=status.HTTP_201_CREATED,
)
async def post_deliverable(
    booking_id: uuid.UUID,
    payload: Annotated[CreateDeliverableRequest, Body()],
    user: CurrentUser,
    db: DbSession,
    request: Request,
) -> DeliverableEnvelope:
    mutation = await deliverable_service.create_deliverable(
        db, booking_id=booking_id, user=user, payload=payload
    )
    if mutation.conversation_id is not None:
        await safe_broadcast(
            request,
            mutation.conversation_id,
            {
                "type": "deliverable.updated",
                "data": mutation.data.model_dump(mode="json"),
            },
        )
    return DeliverableEnvelope(data=mutation.data)


@router.delete("/deliverables/{deliverable_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deliverable(
    deliverable_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    storage: StorageDep,
    request: Request,
) -> Response:
    deletion = await deliverable_service.delete_deliverable(
        db, deliverable_id=deliverable_id, user=user
    )
    try:
        if deletion.conversation_id is not None:
            await safe_broadcast(
                request,
                deletion.conversation_id,
                {
                    "type": "deliverable.updated",
                    "data": {
                        "action": "deleted",
                        "booking_id": str(deletion.booking_id),
                        "deliverable_id": str(deletion.deliverable_id),
                    },
                },
            )
    finally:
        await deliverable_service.cleanup_deleted_object(storage, deletion=deletion)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
