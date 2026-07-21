import uuid

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.api.schemas import (
    CreatorListData,
    CreatorListEnvelope,
    CreatorPublicEnvelope,
    CreatorPublicOut,
)
from app.services import creators as creator_service

router = APIRouter(prefix="/api/v1/creators", tags=["creators"])


@router.get("", response_model=CreatorListEnvelope)
async def list_creators(
    db: DbSession,
    q: str | None = Query(default=None, max_length=100),
    city: str | None = Query(default=None, max_length=100),
    specialty: str | None = Query(default=None, max_length=50),
    min_price: int | None = Query(default=None, ge=0),
    max_price: int | None = Query(default=None, ge=0),
    cursor: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=12, ge=1, le=50),
) -> CreatorListEnvelope:
    items, next_cursor = await creator_service.list_creators(
        db,
        q=q,
        city=city,
        specialty=specialty,
        min_price=min_price,
        max_price=max_price,
        cursor=cursor,
        limit=limit,
    )
    return CreatorListEnvelope(
        data=CreatorListData(
            items=[CreatorPublicOut.model_validate(item, from_attributes=True) for item in items],
            next_cursor=next_cursor,
        )
    )


@router.get("/{creator_id}", response_model=CreatorPublicEnvelope)
async def get_creator(creator_id: uuid.UUID, db: DbSession) -> CreatorPublicEnvelope:
    profile = await creator_service.get_creator(db, creator_id=creator_id)
    return CreatorPublicEnvelope(
        data=CreatorPublicOut.model_validate(profile, from_attributes=True)
    )
