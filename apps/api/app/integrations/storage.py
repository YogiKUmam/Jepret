from dataclasses import dataclass
from functools import partial
from typing import Any, Final, Protocol

import anyio
import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]


class StorageValidationError(ValueError):
    """Raised when stored file content does not match an allowed format."""


@dataclass(frozen=True)
class StoredObject:
    size_bytes: int
    content_type: str
    signature: bytes


class StorageAdapter(Protocol):
    async def create_upload_url(
        self, *, object_key: str, content_type: str, expires_seconds: int
    ) -> str: ...

    async def inspect_object(self, *, object_key: str) -> StoredObject: ...

    async def create_download_url(self, *, object_key: str, expires_seconds: int) -> str: ...

    async def delete_object(self, *, object_key: str) -> None: ...


# Browser uploaders must send this signed header. Storage CORS must allow it.
UPLOAD_IF_NONE_MATCH_HEADER: Final = "If-None-Match"
UPLOAD_IF_NONE_MATCH_VALUE: Final = "*"

_SUPPORTED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
    "application/zip",
}


def sniff_content_type(signature: bytes) -> str:
    """Identify a file type from its magic header, not validate full file integrity."""
    if (
        len(signature) >= 6
        and signature.startswith(b"\xff\xd8\xff")
        and signature[3] not in {0x00, 0x01, *range(0xD0, 0xDA), 0xFF}
        and int.from_bytes(signature[4:6], "big") >= 2
    ):
        return "image/jpeg"
    if signature.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(signature) >= 12 and signature.startswith(b"RIFF") and signature[8:12] == b"WEBP":
        return "image/webp"
    if (
        len(signature) >= 8
        and signature.startswith(b"%PDF-")
        and signature[5] in b"0123456789"
        and signature[6:7] == b"."
        and signature[7] in b"0123456789"
    ):
        return "application/pdf"
    if (
        len(signature) >= 10
        and signature.startswith(b"PK\x03\x04")
        and 10 <= int.from_bytes(signature[4:6], "little") <= 63
    ):
        return "application/zip"
    if len(signature) >= 16 and signature.startswith(b"PK\x05\x06"):
        return "application/zip"
    if len(signature) >= 8 and signature.startswith(b"PK\x07\x08"):
        return "application/zip"
    raise StorageValidationError("Unknown or truncated file signature")


def validate_signature(claimed_content_type: str, signature: bytes) -> None:
    if claimed_content_type not in _SUPPORTED_CONTENT_TYPES:
        raise StorageValidationError(f"Unsupported content type: {claimed_content_type}")
    detected_content_type = sniff_content_type(signature)
    if detected_content_type != claimed_content_type:
        raise StorageValidationError(
            f"File signature {detected_content_type} does not match {claimed_content_type}"
        )


def _require_etag(metadata: dict[str, Any]) -> str:
    etag = metadata.get("ETag")
    if (
        not isinstance(etag, str)
        or len(etag) < 3
        or not etag.startswith('"')
        or not etag.endswith('"')
    ):
        raise StorageValidationError("Storage object has a missing or invalid ETag")
    if any(
        character == '"' or ord(character) < 0x20 or ord(character) == 0x7F
        for character in etag[1:-1]
    ):
        raise StorageValidationError("Storage object has a missing or invalid ETag")
    return etag


def _read_signature_and_close(body: Any) -> bytes:
    try:
        return bytes(body.read(16))[:16]
    finally:
        body.close()


class Boto3StorageAdapter:
    def __init__(
        self,
        *,
        internal_endpoint: str,
        public_endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
    ) -> None:
        client_options: dict[str, Any] = {
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "config": Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        }
        self._internal_client: Any = boto3.client(
            "s3", endpoint_url=internal_endpoint, **client_options
        )
        self._public_client: Any = boto3.client(
            "s3", endpoint_url=public_endpoint, **client_options
        )
        self._bucket = bucket

    async def create_upload_url(
        self, *, object_key: str, content_type: str, expires_seconds: int
    ) -> str:
        result = await anyio.to_thread.run_sync(
            partial(
                self._public_client.generate_presigned_url,
                "put_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": object_key,
                    "ContentType": content_type,
                    "IfNoneMatch": UPLOAD_IF_NONE_MATCH_VALUE,
                },
                ExpiresIn=expires_seconds,
            )
        )
        return str(result)

    async def inspect_object(self, *, object_key: str) -> StoredObject:
        object_location = {"Bucket": self._bucket, "Key": object_key}
        metadata = await anyio.to_thread.run_sync(
            partial(self._internal_client.head_object, **object_location)
        )
        etag = _require_etag(metadata)
        response = await anyio.to_thread.run_sync(
            partial(
                self._internal_client.get_object,
                **object_location,
                Range="bytes=0-15",
                IfMatch=etag,
            )
        )
        body = response["Body"]
        with anyio.CancelScope(shield=True):
            signature = await anyio.to_thread.run_sync(partial(_read_signature_and_close, body))
        await anyio.lowlevel.checkpoint()

        content_type = str(metadata["ContentType"])
        validate_signature(content_type, signature)
        return StoredObject(
            size_bytes=int(metadata["ContentLength"]),
            content_type=content_type,
            signature=signature,
        )

    async def create_download_url(self, *, object_key: str, expires_seconds: int) -> str:
        result = await anyio.to_thread.run_sync(
            partial(
                self._public_client.generate_presigned_url,
                "get_object",
                Params={"Bucket": self._bucket, "Key": object_key},
                ExpiresIn=expires_seconds,
            )
        )
        return str(result)

    async def delete_object(self, *, object_key: str) -> None:
        await anyio.to_thread.run_sync(
            partial(
                self._internal_client.delete_object,
                Bucket=self._bucket,
                Key=object_key,
            )
        )
