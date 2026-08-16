import unicodedata
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

UploadPurpose = Literal["chat_attachment", "deliverable"]
CanonicalContentType = Literal[
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
    "application/zip",
]


class CreateUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: UploadPurpose
    filename: str = Field(strict=True)
    content_type: CanonicalContentType
    size_bytes: int = Field(strict=True, gt=0, le=100 * 1024 * 1024)

    @field_validator("filename", mode="before")
    @classmethod
    def validate_filename(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = unicodedata.normalize("NFKC", value)
        if not normalized or len(normalized) > 255 or normalized != normalized.strip():
            raise ValueError("filename must not have surrounding whitespace")
        if (
            "/" in normalized
            or "\\" in normalized
            or any(unicodedata.category(character).startswith("C") for character in normalized)
        ):
            raise ValueError("filename must be a plain display name")
        return normalized


class UploadOut(BaseModel):
    id: uuid.UUID
    purpose: UploadPurpose
    filename: str
    content_type: CanonicalContentType
    size_bytes: int
    status: Literal["pending", "completed", "expired", "rejected"]
    expires_at: datetime
    completed_at: datetime | None


class SignedUploadOut(UploadOut):
    upload_url: str
    required_headers: dict[str, str]


class UploadEnvelope(BaseModel):
    data: UploadOut


class SignedUploadEnvelope(BaseModel):
    data: SignedUploadOut


class SignedUrlOut(BaseModel):
    url: str


class SignedUrlEnvelope(BaseModel):
    data: SignedUrlOut
