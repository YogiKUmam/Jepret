import uuid

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.api.review_schemas import (
    CreateReviewRequest,
    ReviewEnvelope,
    ReviewOut,
    ReviewPageEnvelope,
    ReviewPageOut,
)
from app.services import reviews as review_service

router = APIRouter(tags=["reviews"])


@router.post("/api/v1/bookings/{booking_id}/reviews", response_model=ReviewEnvelope)
async def create_booking_review(
    booking_id: uuid.UUID,
    payload: CreateReviewRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> ReviewEnvelope:
    review = await review_service.create_booking_review(
        db,
        booking_id=booking_id,
        client_user=current_user,
        rating=payload.rating,
        comment=payload.comment,
    )
    return ReviewEnvelope(
        data=ReviewOut(
            id=review.id,
            booking_id=review.booking_id,
            client_user_id=review.client_user_id,
            client_full_name=review.client.full_name,
            creator_profile_id=review.creator_profile_id,
            rating=review.rating,
            comment=review.comment,
            created_at=review.created_at,
        )
    )


@router.get("/api/v1/bookings/{booking_id}/review", response_model=ReviewEnvelope)
async def get_booking_review(
    booking_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> ReviewEnvelope:
    review = await review_service.get_booking_review(
        db,
        booking_id=booking_id,
        user=current_user,
    )
    if not review:
        return ReviewEnvelope(data=None)

    return ReviewEnvelope(
        data=ReviewOut(
            id=review.id,
            booking_id=review.booking_id,
            client_user_id=review.client_user_id,
            client_full_name=review.client.full_name,
            creator_profile_id=review.creator_profile_id,
            rating=review.rating,
            comment=review.comment,
            created_at=review.created_at,
        )
    )


@router.get("/api/v1/creators/{creator_id}/reviews", response_model=ReviewPageEnvelope)
async def list_creator_reviews(
    creator_id: uuid.UUID,
    db: DbSession,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
) -> ReviewPageEnvelope:
    items, next_cursor, rating_avg, review_count = await review_service.list_creator_reviews(
        db,
        creator_profile_id=creator_id,
        cursor=cursor,
        limit=limit,
    )
    return ReviewPageEnvelope(
        data=ReviewPageOut(
            items=[
                ReviewOut(
                    id=review.id,
                    booking_id=review.booking_id,
                    client_user_id=review.client_user_id,
                    client_full_name=review.client.full_name,
                    creator_profile_id=review.creator_profile_id,
                    rating=review.rating,
                    comment=review.comment,
                    created_at=review.created_at,
                )
                for review in items
            ],
            next_cursor=next_cursor,
            rating_average=rating_avg,
            review_count=review_count,
        )
    )
