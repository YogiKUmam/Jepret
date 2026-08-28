import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreateReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)


class ReviewOut(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    client_user_id: uuid.UUID
    client_full_name: str
    creator_profile_id: uuid.UUID
    rating: int
    comment: str | None
    created_at: datetime


class ReviewEnvelope(BaseModel):
    data: ReviewOut | None


class ReviewPageOut(BaseModel):
    items: list[ReviewOut]
    next_cursor: str | None
    rating_average: float
    review_count: int


class ReviewPageEnvelope(BaseModel):
    data: ReviewPageOut
