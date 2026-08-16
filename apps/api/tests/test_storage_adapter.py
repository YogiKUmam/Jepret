from collections.abc import Callable
from inspect import Parameter, signature
from io import BytesIO
from threading import Event
from typing import Any
from urllib.parse import parse_qs, urlparse

import anyio
import pytest

from app.integrations import storage
from app.integrations.storage import (
    Boto3StorageAdapter,
    StorageAdapter,
    StorageValidationError,
    sniff_content_type,
    validate_signature,
)


@pytest.mark.parametrize("adapter_type", [StorageAdapter, Boto3StorageAdapter])
@pytest.mark.parametrize(
    ("method_name", "parameter_names"),
    [
        ("create_upload_url", ("object_key", "content_type", "expires_seconds")),
        ("inspect_object", ("object_key",)),
        ("create_download_url", ("object_key", "expires_seconds")),
        ("delete_object", ("object_key",)),
    ],
)
def test_storage_adapter_operations_require_keyword_arguments(
    adapter_type: type[StorageAdapter] | type[Boto3StorageAdapter],
    method_name: str,
    parameter_names: tuple[str, ...],
) -> None:
    parameters = signature(getattr(adapter_type, method_name)).parameters

    assert all(parameters[name].kind is Parameter.KEYWORD_ONLY for name in parameter_names)


class FakeBody(BytesIO):
    def __init__(self, value: bytes) -> None:
        super().__init__(value)
        self.was_closed = False
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return super().read(size)

    def close(self) -> None:
        self.was_closed = True
        super().close()


class FakeS3Client:
    def __init__(self, name: str, signature: bytes = b"%PDF-1.7\n") -> None:
        self.name = name
        self.signature = signature
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.body: FakeBody | None = None

    def generate_presigned_url(self, operation: str, **kwargs: Any) -> str:
        self.calls.append(("generate_presigned_url", {"operation": operation, **kwargs}))
        return f"https://{self.name}.example/{operation}"

    def head_object(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("head_object", kwargs))
        return {
            "ContentLength": 9,
            "ContentType": "application/pdf",
            "ETag": '"etag-value"',
        }

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_object", kwargs))
        self.body = FakeBody(self.signature)
        return {"Body": self.body}

    def delete_object(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("delete_object", kwargs))
        return {}


@pytest.fixture
def clients(monkeypatch: pytest.MonkeyPatch) -> tuple[FakeS3Client, FakeS3Client]:
    internal = FakeS3Client("internal")
    public = FakeS3Client("public")
    created_clients = iter((internal, public))
    expected_endpoints = iter(("http://minio:9000", "http://localhost:9000"))

    def fake_client(service_name: str, **kwargs: Any) -> FakeS3Client:
        assert service_name == "s3"
        assert kwargs["aws_access_key_id"] == "access"
        assert kwargs["aws_secret_access_key"] == "secret"
        assert kwargs["config"].s3 == {"addressing_style": "path"}
        assert kwargs["config"].connect_timeout == 3
        assert kwargs["config"].read_timeout == 10
        assert kwargs["config"].retries == {"mode": "standard", "max_attempts": 2}
        assert kwargs["endpoint_url"] == next(expected_endpoints)
        return next(created_clients)

    monkeypatch.setattr("boto3.client", fake_client)
    return internal, public


def make_adapter() -> Boto3StorageAdapter:
    return Boto3StorageAdapter(
        internal_endpoint="http://minio:9000",
        public_endpoint="http://localhost:9000",
        access_key="access",
        secret_key="secret",
        bucket="jepret-private",
    )


def test_sniff_content_type_recognizes_supported_signatures() -> None:
    assert sniff_content_type(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00") == "image/jpeg"
    assert sniff_content_type(b"\x89PNG\r\n\x1a\n") == "image/png"
    assert sniff_content_type(b"RIFF\x00\x00\x00\x00WEBP") == "image/webp"
    assert sniff_content_type(b"%PDF-1.7\n") == "application/pdf"
    assert sniff_content_type(b"%PDF-2.0\n") == "application/pdf"
    assert (
        sniff_content_type(b"PK\x03\x04\x14\x00\x00\x00\x08\x00\x00\x00\x00\x00\x00\x00")
        == "application/zip"
    )


@pytest.mark.parametrize(
    "signature",
    [
        b"",
        b"\xff\xd8\xff\xe0",
        b"%PD",
        b"%PDF-1.",
        b"%PDF-a.7",
        b"%PDF-2.a",
        b"PK\x03",
        b"PK\x03\x04",
        b"not-a-file",
    ],
)
def test_sniff_content_type_rejects_unknown_or_truncated_signatures(signature: bytes) -> None:
    with pytest.raises(StorageValidationError, match="signature"):
        sniff_content_type(signature)


def test_validate_signature_rejects_claimed_mime_mismatch() -> None:
    with pytest.raises(StorageValidationError, match="does not match"):
        validate_signature("image/png", b"%PDF-1.7\n")


def test_validate_signature_rejects_unsupported_mime() -> None:
    with pytest.raises(StorageValidationError, match="Unsupported"):
        validate_signature("video/mp4", b"not-a-video")


@pytest.mark.asyncio
async def test_presigned_urls_use_public_client_and_run_in_threads(
    clients: tuple[FakeS3Client, FakeS3Client], monkeypatch: pytest.MonkeyPatch
) -> None:
    internal, public = clients
    threaded: list[Callable[[], object]] = []

    async def fake_run_sync(function: Callable[[], object]) -> object:
        threaded.append(function)
        return function()

    monkeypatch.setattr("anyio.to_thread.run_sync", fake_run_sync)
    adapter = make_adapter()

    upload_url = await adapter.create_upload_url(
        object_key="uploads/file.pdf", content_type="application/pdf", expires_seconds=300
    )
    download_url = await adapter.create_download_url(
        object_key="uploads/file.pdf", expires_seconds=120
    )

    assert upload_url == "https://public.example/put_object"
    assert download_url == "https://public.example/get_object"
    assert internal.calls == []
    assert public.calls == [
        (
            "generate_presigned_url",
            {
                "operation": "put_object",
                "Params": {
                    "Bucket": "jepret-private",
                    "Key": "uploads/file.pdf",
                    "ContentType": "application/pdf",
                    "IfNoneMatch": "*",
                },
                "ExpiresIn": 300,
            },
        ),
        (
            "generate_presigned_url",
            {
                "operation": "get_object",
                "Params": {"Bucket": "jepret-private", "Key": "uploads/file.pdf"},
                "ExpiresIn": 120,
            },
        ),
    ]
    assert len(threaded) == 2


@pytest.mark.asyncio
async def test_inspect_and_delete_use_internal_client(
    clients: tuple[FakeS3Client, FakeS3Client], monkeypatch: pytest.MonkeyPatch
) -> None:
    internal, public = clients
    thread_call_count = 0

    async def fake_run_sync(function: Callable[[], object]) -> object:
        nonlocal thread_call_count
        thread_call_count += 1
        return function()

    monkeypatch.setattr("anyio.to_thread.run_sync", fake_run_sync)
    adapter = make_adapter()

    stored_object = await adapter.inspect_object(object_key="uploads/file.pdf")
    await adapter.delete_object(object_key="uploads/file.pdf")

    assert stored_object.size_bytes == 9
    assert stored_object.content_type == "application/pdf"
    assert stored_object.signature == b"%PDF-1.7\n"
    assert internal.calls == [
        ("head_object", {"Bucket": "jepret-private", "Key": "uploads/file.pdf"}),
        (
            "get_object",
            {
                "Bucket": "jepret-private",
                "Key": "uploads/file.pdf",
                "Range": "bytes=0-15",
                "IfMatch": '"etag-value"',
            },
        ),
        ("delete_object", {"Bucket": "jepret-private", "Key": "uploads/file.pdf"}),
    ]
    assert public.calls == []
    assert internal.body is not None and internal.body.was_closed
    assert internal.body.read_sizes == [16]
    assert thread_call_count == 4


@pytest.mark.asyncio
async def test_upload_url_binds_discoverable_create_only_header() -> None:
    adapter = make_adapter()

    upload_url = await adapter.create_upload_url(
        object_key="uploads/file.pdf",
        content_type="application/pdf",
        expires_seconds=300,
    )
    signed_headers = parse_qs(urlparse(upload_url).query)["X-Amz-SignedHeaders"][0].split(";")

    assert (storage.UPLOAD_IF_NONE_MATCH_HEADER, storage.UPLOAD_IF_NONE_MATCH_VALUE) == (
        "If-None-Match",
        "*",
    )
    assert "if-none-match" in signed_headers


@pytest.mark.parametrize("etag", [None, "", "etag-unquoted", '"bad\nvalue"'])
@pytest.mark.asyncio
async def test_inspect_fails_closed_for_missing_or_invalid_etag(
    etag: str | None,
    clients: tuple[FakeS3Client, FakeS3Client],
) -> None:
    internal, _ = clients

    def invalid_head_object(**kwargs: Any) -> dict[str, Any]:
        internal.calls.append(("head_object", kwargs))
        return {"ContentLength": 9, "ContentType": "application/pdf", "ETag": etag}

    internal.head_object = invalid_head_object  # type: ignore[method-assign]
    adapter = make_adapter()

    with pytest.raises(StorageValidationError, match="ETag"):
        await adapter.inspect_object(object_key="uploads/file.pdf")

    assert [call for call in internal.calls if call[0] == "get_object"] == []


@pytest.mark.asyncio
async def test_inspect_bounds_signature_when_body_ignores_requested_size(
    clients: tuple[FakeS3Client, FakeS3Client],
) -> None:
    internal, _ = clients

    class OversizedBody(FakeBody):
        def read(self, size: int = -1) -> bytes:
            self.read_sizes.append(size)
            return self.getvalue()

    oversized_body = OversizedBody(b"%PDF-1.7\n" + b"x" * 100)

    def oversized_get_object(**kwargs: Any) -> dict[str, Any]:
        internal.calls.append(("get_object", kwargs))
        internal.body = oversized_body
        return {"Body": oversized_body}

    internal.get_object = oversized_get_object  # type: ignore[method-assign]
    adapter = make_adapter()

    stored_object = await adapter.inspect_object(object_key="uploads/file.pdf")

    assert stored_object.signature == (b"%PDF-1.7\n" + b"x" * 7)
    assert oversized_body.read_sizes == [16]
    assert oversized_body.was_closed


@pytest.mark.asyncio
async def test_cancellation_during_signature_read_eventually_closes_body(
    clients: tuple[FakeS3Client, FakeS3Client],
) -> None:
    internal, _ = clients
    read_started = Event()
    release_read = Event()

    class BlockingBody(FakeBody):
        def read(self, size: int = -1) -> bytes:
            self.read_sizes.append(size)
            read_started.set()
            if not release_read.wait(timeout=5):
                raise TimeoutError("test did not release body read")
            return super(FakeBody, self).read(size)

    blocking_body = BlockingBody(b"%PDF-1.7\n")

    def blocking_get_object(**kwargs: Any) -> dict[str, Any]:
        internal.calls.append(("get_object", kwargs))
        internal.body = blocking_body
        return {"Body": blocking_body}

    internal.get_object = blocking_get_object  # type: ignore[method-assign]
    adapter = make_adapter()

    async def inspect_until_cancelled() -> None:
        with pytest.raises(anyio.get_cancelled_exc_class()):
            await adapter.inspect_object(object_key="uploads/file.pdf")

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(inspect_until_cancelled)
        assert await anyio.to_thread.run_sync(read_started.wait, 5)
        task_group.cancel_scope.cancel()
        release_read.set()

    assert blocking_body.was_closed


@pytest.mark.asyncio
async def test_inspect_closes_body_when_read_fails(
    clients: tuple[FakeS3Client, FakeS3Client], monkeypatch: pytest.MonkeyPatch
) -> None:
    internal, _ = clients

    class BrokenBody(FakeBody):
        def read(self, size: int = -1) -> bytes:
            raise OSError("read failed")

    broken_body = BrokenBody(b"")

    def broken_get_object(**kwargs: Any) -> dict[str, Any]:
        internal.calls.append(("get_object", kwargs))
        internal.body = broken_body
        return {"Body": broken_body}

    internal.get_object = broken_get_object  # type: ignore[method-assign]
    adapter = make_adapter()

    with pytest.raises(OSError, match="read failed"):
        await adapter.inspect_object(object_key="uploads/file.pdf")

    assert broken_body.was_closed
