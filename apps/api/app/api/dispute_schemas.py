import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DisputeReason = Literal["not_delivered", "quality_issue", "unresponsive", "other"]
DisputeStatus = Literal[
    "open",
    "under_review",
    "resolved_client",
    "resolved_creator",
    "closed",
]
DisputeResolution = Literal["resolved_client", "resolved_creator"]


class CreateDisputeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_category: DisputeReason
    description: str = Field(min_length=10, max_length=2000)


class ResolveDisputeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution: DisputeResolution
    resolution_notes: str = Field(min_length=5, max_length=2000)


class DisputeOut(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    opened_by_user_id: uuid.UUID
    opened_by_full_name: str
    reason_category: str
    description: str
    status: str
    resolution_notes: str | None
    resolved_by_admin_user_id: uuid.UUID | None
    created_at: datetime
    resolved_at: datetime | None


class DisputeEnvelope(BaseModel):
    data: DisputeOut | None


class DisputeListEnvelope(BaseModel):
    data: list[DisputeOut]


class AdminOverviewOut(BaseModel):
    total_users: int
    total_creators: int
    pending_creator_applications: int
    total_bookings: int
    active_disputes: int
    total_gmv_idr: int


class AdminOverviewEnvelope(BaseModel):
    data: AdminOverviewOut
