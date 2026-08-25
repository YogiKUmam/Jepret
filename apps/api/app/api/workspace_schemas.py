import unicodedata
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

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


class ConversationOut(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    created_at: datetime


class ConversationEnvelope(BaseModel):
    data: ConversationOut | None


class MessageSenderOut(BaseModel):
    id: uuid.UUID
    full_name: str


class AttachmentOut(BaseModel):
    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int


class MessageOut(BaseModel):
    id: uuid.UUID
    client_message_id: uuid.UUID
    message_type: Literal["text", "attachment", "system"]
    body: str | None
    attachment: AttachmentOut | None
    sender: MessageSenderOut
    read_at: datetime | None
    created_at: datetime


class CreateMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_message_id: uuid.UUID
    message_type: Literal["text", "attachment"]
    body: str | None = None
    upload_id: uuid.UUID | None = None


class MessageEnvelope(BaseModel):
    data: MessageOut


class MessagePageOut(BaseModel):
    items: list[MessageOut]
    next_cursor: str | None


class MessagePageEnvelope(BaseModel):
    data: MessagePageOut


class ReadReceiptOut(BaseModel):
    count: int
    read_at: datetime


class ReadReceiptEnvelope(BaseModel):
    data: ReadReceiptOut


class UnreadCountOut(BaseModel):
    booking_id: uuid.UUID
    count: int


class UnreadEnvelope(BaseModel):
    data: list[UnreadCountOut]


def _normalize_plain_text(value: object, *, allow_empty: bool) -> object:
    if not isinstance(value, str):
        return value
    if any(
        character == "\x00"
        or unicodedata.category(character) == "Cs"
        or (unicodedata.category(character).startswith("C") and character not in {"\n", "\t"})
        for character in value
    ):
        raise ValueError("text contains unsafe control characters")
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not allow_empty and not normalized:
        raise ValueError("text must not be empty")
    return normalized


class DeliverableRequestBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(strict=True, min_length=1, max_length=150)
    description: str | None = Field(default=None, strict=True, max_length=2000)
    replaces_deliverable_id: uuid.UUID | None = None

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: object) -> object:
        return _normalize_plain_text(value, allow_empty=False)

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: object) -> object:
        if value is None:
            return None
        normalized = _normalize_plain_text(value, allow_empty=True)
        return normalized or None


class PrivateDeliverableRequest(DeliverableRequestBase):
    source_type: Literal["private_file"]
    upload_id: uuid.UUID


class ExternalDeliverableRequest(DeliverableRequestBase):
    source_type: Literal["external_link"]
    external_url: AnyHttpUrl

    @field_validator("external_url")
    @classmethod
    def require_safe_https(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.scheme != "https" or value.username is not None or value.password is not None:
            raise ValueError("external URL must use HTTPS without credentials")
        return value


CreateDeliverableRequest = Annotated[
    PrivateDeliverableRequest | ExternalDeliverableRequest,
    Field(discriminator="source_type"),
]


class DeliverableOut(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    uploaded_by_user_id: uuid.UUID
    title: str
    description: str | None
    source_type: Literal["private_file", "external_link"]
    upload_id: uuid.UUID | None
    external_url: str | None
    external_host: str | None
    media_type: str | None
    filename: str | None
    content_type: str | None
    size_bytes: int | None
    replaces_deliverable_id: uuid.UUID | None
    downloadable: bool
    created_at: datetime


class DeliverableEnvelope(BaseModel):
    data: DeliverableOut


class DeliverableListEnvelope(BaseModel):
    data: list[DeliverableOut]
