import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

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


class CreatorPublicEnvelope(BaseModel):
    data: CreatorPublicOut


class CreatorListData(BaseModel):
    items: list[CreatorPublicOut]
    next_cursor: str | None


class CreatorListEnvelope(BaseModel):
    data: CreatorListData
