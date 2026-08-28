import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints, field_validator

EmailAddress = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    ),
]


class RegisterRequest(BaseModel):
    email: EmailAddress
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=100)


class LoginRequest(BaseModel):
    email: EmailAddress
    password: str = Field(min_length=1, max_length=128)


class CreatorProfileOut(BaseModel):
    id: uuid.UUID
    display_name: str
    city: str
    bio: str
    specialty: str
    starting_price_idr: int
    status: str
    rating_average: float = 0.0
    review_count: int = 0
    submitted_at: datetime | None
    reviewed_at: datetime | None


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_admin: bool
    creator_profile: CreatorProfileOut | None = None


class UserEnvelope(BaseModel):
    data: UserOut


class MessageEnvelope(BaseModel):
    data: dict[str, str]


class UpdateProfileRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)


class CreatorDraftRequest(BaseModel):
    display_name: str = Field(min_length=2, max_length=100)
    city: str = Field(min_length=2, max_length=100)
    bio: str = Field(default="", max_length=2000)
    specialty: str = Field(min_length=2, max_length=50)
    starting_price_idr: int = Field(ge=0)


class CreatorProfileEnvelope(BaseModel):
    data: CreatorProfileOut


class CreatorApplicationOut(BaseModel):
    profile: CreatorProfileOut
    user_email: str
    user_full_name: str


class CreatorApplicationListEnvelope(BaseModel):
    data: list[CreatorApplicationOut]


class CreatorPublicOut(BaseModel):
    id: uuid.UUID
    display_name: str
    city: str
    bio: str
    specialty: str
    starting_price_idr: int
    rating_average: float = 0.0
    review_count: int = 0


class CreatorPublicEnvelope(BaseModel):
    data: CreatorPublicOut


class CreatorListData(BaseModel):
    items: list[CreatorPublicOut]
    next_cursor: str | None


class CreatorListEnvelope(BaseModel):
    data: CreatorListData


class BookingCreatorOut(BaseModel):
    id: uuid.UUID
    display_name: str
    city: str
    specialty: str


class BookingOut(BaseModel):
    id: uuid.UUID
    status: str
    event_date: date
    event_city: str
    notes: str
    quoted_price_idr: int
    created_at: datetime
    started_at: datetime | None
    delivered_at: datetime | None
    completed_at: datetime | None
    creator: BookingCreatorOut
    client_name: str


class BookingEnvelope(BaseModel):
    data: BookingOut


class BookingListEnvelope(BaseModel):
    data: list[BookingOut]


class CreateBookingRequest(BaseModel):
    creator_id: uuid.UUID
    event_date: date
    event_city: str = Field(min_length=2, max_length=100)
    notes: str = Field(default="", max_length=2000)


class PaymentOut(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    provider: str
    amount_idr: int
    platform_fee_idr: int
    creator_net_idr: int
    status: str
    paid_at: datetime | None
    held_at: datetime | None
    released_at: datetime | None
    refunded_at: datetime | None
    created_at: datetime


class PaymentEnvelope(BaseModel):
    data: PaymentOut


class MockPaymentWebhookRequest(BaseModel):
    payment_id: str
    event_id: str
    event_type: str

    @field_validator("payment_id")
    @classmethod
    def validate_canonical_payment_id(cls, value: str) -> str:
        try:
            parsed = uuid.UUID(value)
        except ValueError as exc:
            raise ValueError("payment_id must be a canonical UUID") from exc
        if value != str(parsed):
            raise ValueError("payment_id must be a canonical UUID")
        return value

    @field_validator("event_id")
    @classmethod
    def normalize_event_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 150:
            raise ValueError("event_id must contain between 1 and 150 characters")
        return normalized
