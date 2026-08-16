import asyncio
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Annotated, Literal

import pytest
from botocore.exceptions import (  # type: ignore[import-untyped]
    EndpointConnectionError,
    NoCredentialsError,
    ReadTimeoutError,
)
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.errors import DomainError
from app.db.models import Booking, UploadIntent, User
from app.integrations.storage import StorageAdapter, StoredObject
from app.main import create_app
from app.services import uploads as upload_service
from tests.conftest import fresh_connection, make_admin, unique_email

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("upload_cleanup")]

PASSWORD = "sandi-aman-123"
PDF_SIGNATURE = b"%PDF-1.7\r\n"
ZIP_SIGNATURE = b"PK\x03\x04\x14\x00\x00\x00\x08\x00"


class FakeStorage:
    def __init__(self) -> None:
        self.app: FastAPI | None = None
        self.objects: dict[str, StoredObject | Exception] = {}
        self.upload_keys: list[str] = []
        self.upload_expiries: list[int] = []
        self.inspect_calls = 0
        self.upload_error: Exception | None = None
        self.before_upload_sign: Callable[[], None] | None = None
        self.inspect_started: asyncio.Event | None = None
        self.release_inspect: asyncio.Event | None = None
        self.after_inspect: Callable[[], None] | None = None

    async def create_upload_url(
        self, *, object_key: str, content_type: str, expires_seconds: int
    ) -> str:
        if self.upload_error is not None:
            raise self.upload_error
        if self.before_upload_sign is not None:
            self.before_upload_sign()
        self.upload_keys.append(object_key)
        self.upload_expiries.append(expires_seconds)
        return f"https://storage.test/upload/{len(self.upload_keys)}"

    async def inspect_object(self, *, object_key: str) -> StoredObject:
        self.inspect_calls += 1
        if self.inspect_started is not None:
            self.inspect_started.set()
        if self.release_inspect is not None:
            await self.release_inspect.wait()
        if self.after_inspect is not None:
            self.after_inspect()
        value = self.objects.get(object_key, FileNotFoundError("missing provider object"))
        if isinstance(value, Exception):
            raise value
        return value

    async def create_download_url(self, *, object_key: str, expires_seconds: int) -> str:
        return "https://storage.test/download/signed"

    async def delete_object(self, *, object_key: str) -> None:
        self.objects.pop(object_key, None)


@pytest.fixture
def fake_storage() -> Iterator[FakeStorage]:
    storage = FakeStorage()
    app = create_app()
    app.dependency_overrides[upload_service.get_storage_adapter] = lambda: storage
    storage.app = app
    try:
        yield storage
    finally:
        app.dependency_overrides.pop(upload_service.get_storage_adapter, None)


def app_with_storage(storage: FakeStorage) -> FastAPI:
    assert storage.app is not None
    return storage.app


@pytest.fixture
async def upload_cleanup(email_cleanup: list[str]) -> AsyncIterator[None]:
    yield
    if email_cleanup:
        async with fresh_connection() as connection:
            await connection.execute(
                text(
                    "DELETE FROM upload_intents WHERE requested_by_user_id IN "
                    "(SELECT id FROM users WHERE email = ANY(:emails))"
                ),
                {"emails": email_cleanup},
            )


async def test_storage_dependency_overrides_are_isolated_between_app_instances() -> None:
    provider = upload_service.get_storage_adapter
    first_storage = FakeStorage()
    second_storage = FakeStorage()
    first_app = create_app()
    second_app = create_app()

    @first_app.get("/test/storage-identity")
    async def first_identity(
        storage: Annotated[StorageAdapter, Depends(provider)],
    ) -> int:
        return id(storage)

    @second_app.get("/test/storage-identity")
    async def second_identity(
        storage: Annotated[StorageAdapter, Depends(provider)],
    ) -> int:
        return id(storage)

    first_app.dependency_overrides[provider] = lambda: first_storage
    second_app.dependency_overrides[provider] = lambda: second_storage
    with TestClient(first_app) as first_client, TestClient(second_app) as second_client:
        first_response, second_response = await asyncio.gather(
            asyncio.to_thread(first_client.get, "/test/storage-identity"),
            asyncio.to_thread(second_client.get, "/test/storage-identity"),
        )

    assert first_response.json() == id(first_storage)
    assert second_response.json() == id(second_storage)


def register(client: TestClient, email_cleanup: list[str], name: str) -> str:
    email = unique_email("up")
    email_cleanup.append(email)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": name},
    )
    assert response.status_code == 201, response.text
    return email


def login(client: TestClient, email: str) -> None:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text


def logout(client: TestClient) -> None:
    assert client.post("/api/v1/auth/logout").status_code == 200


async def make_creator(client: TestClient, email_cleanup: list[str], name: str) -> tuple[str, str]:
    email = register(client, email_cleanup, name)
    response = client.put(
        "/api/v1/profiles/me/creator",
        json={
            "display_name": name,
            "city": "Bandung",
            "bio": "Upload test.",
            "specialty": "wedding",
            "starting_price_idr": 1_500_000,
        },
    )
    profile_id = response.json()["data"]["id"]
    async with fresh_connection() as connection:
        await connection.execute(
            text("UPDATE creator_profiles SET status = 'approved' WHERE id = :id"),
            {"id": profile_id},
        )
    logout(client)
    return email, profile_id


async def workspace(
    client: TestClient, email_cleanup: list[str], *, status: str = "confirmed"
) -> tuple[str, str, str]:
    creator_email, profile_id = await make_creator(client, email_cleanup, "Studio Upload")
    client_email = register(client, email_cleanup, "Klien Upload")
    booking = client.post(
        "/api/v1/bookings",
        json={
            "creator_id": profile_id,
            "event_date": (datetime.now(UTC).date() + timedelta(days=100)).isoformat(),
            "event_city": "Bandung",
            "notes": "Private upload.",
        },
    ).json()["data"]
    async with fresh_connection() as connection:
        await connection.execute(
            text("UPDATE bookings SET status = :status WHERE id = :id"),
            {"status": status, "id": booking["id"]},
        )
    return booking["id"], client_email, creator_email


def upload_payload(
    *, purpose: str = "chat_attachment", content_type: str = "application/pdf", size: int = 10
) -> dict[str, object]:
    return {
        "purpose": purpose,
        "filename": "brief.pdf",
        "content_type": content_type,
        "size_bytes": size,
    }


async def intent_row(upload_id: str) -> UploadIntent:
    engine = create_async_engine(upload_service.get_settings().database_url, poolclass=None)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            intent = await session.get(UploadIntent, uuid.UUID(upload_id))
            assert intent is not None
            return intent
    finally:
        await engine.dispose()


def test_upload_routes_require_authentication() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            f"/api/v1/bookings/{uuid.uuid4()}/uploads",
            json={
                "purpose": "chat_attachment",
                "filename": "brief.pdf",
                "content_type": "application/pdf",
                "size_bytes": 1024,
            },
        )

    assert response.status_code == 401


async def test_client_and_creator_can_create_chat_upload_without_key_leak(
    email_cleanup: list[str], fake_storage: FakeStorage
) -> None:
    with TestClient(app_with_storage(fake_storage)) as client:
        booking_id, _, creator_email = await workspace(client, email_cleanup)
        client_created = client.post(
            f"/api/v1/bookings/{booking_id}/uploads", json=upload_payload()
        )
        logout(client)
        login(client, creator_email)
        creator_created = client.post(
            f"/api/v1/bookings/{booking_id}/uploads", json=upload_payload()
        )

    for response in (client_created, creator_created):
        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert data["upload_url"].startswith("https://storage.test/upload/")
        assert data["required_headers"] == {
            "Content-Type": "application/pdf",
            "If-None-Match": "*",
        }
        assert not ({"object_key", "credentials", "etag"} & data.keys())
        assert data["status"] == "pending"
    assert all(key.startswith(f"chat_attachment/{booking_id}/") for key in fake_storage.upload_keys)
    assert all("brief.pdf" not in key for key in fake_storage.upload_keys)


async def test_upload_presign_uses_configured_ttl_while_intent_ttl_is_ten_minutes(
    email_cleanup: list[str],
    fake_storage: FakeStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before_presign = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    signed_at = before_presign + timedelta(minutes=2)

    class ControlledDateTime:
        current = before_presign

        @classmethod
        def now(cls, timezone: object) -> datetime:
            assert timezone is UTC
            return cls.current

    monkeypatch.setattr(
        upload_service,
        "get_settings",
        lambda: SimpleNamespace(
            database_url=get_settings().database_url,
            storage_signed_url_ttl_seconds=3600,
        ),
    )
    with TestClient(app_with_storage(fake_storage)) as client:
        booking_id, _, _ = await workspace(client, email_cleanup)
        fake_storage.before_upload_sign = lambda: setattr(ControlledDateTime, "current", signed_at)
        monkeypatch.setattr(upload_service, "datetime", ControlledDateTime)
        response = client.post(f"/api/v1/bookings/{booking_id}/uploads", json=upload_payload())

    intent = await intent_row(response.json()["data"]["id"])
    assert response.status_code == 201
    assert fake_storage.upload_expiries == [600]
    assert intent.expires_at == signed_at + upload_service.UPLOAD_TTL
    assert signed_at + timedelta(seconds=fake_storage.upload_expiries[0]) <= intent.expires_at


async def test_upload_presign_failure_does_not_commit_intent(
    email_cleanup: list[str], fake_storage: FakeStorage
) -> None:
    fake_storage.upload_error = EndpointConnectionError(endpoint_url="http://private-storage")
    with TestClient(app_with_storage(fake_storage)) as client:
        booking_id, _, _ = await workspace(client, email_cleanup)
        response = client.post(f"/api/v1/bookings/{booking_id}/uploads", json=upload_payload())
    async with fresh_connection() as connection:
        count = await connection.scalar(
            text("SELECT count(*) FROM upload_intents WHERE booking_id = :booking_id"),
            {"booking_id": booking_id},
        )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert count == 0


@pytest.mark.parametrize("role", ["client", "creator"])
async def test_admin_participant_is_denied_create_complete_and_download(
    email_cleanup: list[str], fake_storage: FakeStorage, role: Literal["client", "creator"]
) -> None:
    with TestClient(app_with_storage(fake_storage)) as client:
        booking_id, client_email, creator_email = await workspace(client, email_cleanup)
        participant_email = client_email if role == "client" else creator_email
        if role == "creator":
            logout(client)
            login(client, creator_email)
        pending = await create_stored_intent(client, booking_id, fake_storage)
        completed = await create_stored_intent(client, booking_id, fake_storage)
        assert client.post(f"/api/v1/uploads/{completed['id']}/complete").status_code == 200
        await make_admin(participant_email)
        created = client.post(f"/api/v1/bookings/{booking_id}/uploads", json=upload_payload())
        completion = client.post(f"/api/v1/uploads/{pending['id']}/complete")
        download = client.post(f"/api/v1/uploads/{completed['id']}/download")

    assert all(response.status_code == 404 for response in (created, completion, download))
    assert created.json()["error"]["code"] == "BOOKING_NOT_FOUND"
    assert completion.json()["error"]["code"] == "UPLOAD_NOT_FOUND"
    assert download.json()["error"]["code"] == "UPLOAD_NOT_FOUND"


@pytest.mark.parametrize(
    "size",
    ["10", 10.0, True, 100 * 1024 * 1024 + 1],
)
def test_upload_schema_rejects_non_strict_or_globally_oversized_size(size: object) -> None:
    with pytest.raises(ValidationError):
        upload_service.CreateUploadRequest.model_validate({**upload_payload(), "size_bytes": size})


@pytest.mark.parametrize(
    "filename",
    ["brief\u200b.pdf", "brief\u202e.pdf", "brief\ue000.pdf", "folder\uff0fbrief.pdf"],
)
def test_upload_schema_rejects_deceptive_unicode_filename(filename: str) -> None:
    with pytest.raises(ValidationError):
        upload_service.CreateUploadRequest.model_validate(
            {**upload_payload(), "filename": filename}
        )


def test_upload_schema_normalizes_safe_unicode_filename() -> None:
    payload = upload_service.CreateUploadRequest.model_validate(
        {**upload_payload(), "filename": "Ｆｏｏ.pdf"}
    )
    assert payload.filename == "Foo.pdf"


async def test_outsider_admin_and_unknown_booking_are_indistinguishable_not_found(
    email_cleanup: list[str], fake_storage: FakeStorage
) -> None:
    with TestClient(app_with_storage(fake_storage)) as client:
        booking_id, _, _ = await workspace(client, email_cleanup)
        logout(client)
        outsider_email = register(client, email_cleanup, "Outsider")
        outsider = client.post(f"/api/v1/bookings/{booking_id}/uploads", json=upload_payload())
        unknown = client.post(f"/api/v1/bookings/{uuid.uuid4()}/uploads", json=upload_payload())
        await make_admin(outsider_email)
        admin = client.post(f"/api/v1/bookings/{booking_id}/uploads", json=upload_payload())

    assert [response.status_code for response in (outsider, unknown, admin)] == [404, 404, 404]
    assert all(
        response.json()["error"]["code"] == "BOOKING_NOT_FOUND"
        for response in (outsider, unknown, admin)
    )
    assert fake_storage.upload_keys == []


@pytest.mark.parametrize(
    ("status", "purpose", "actor", "expected"),
    [
        ("accepted", "chat_attachment", "client", 409),
        ("completed", "chat_attachment", "creator", 409),
        ("confirmed", "deliverable", "creator", 409),
        ("in_progress", "deliverable", "client", 404),
        ("in_progress", "deliverable", "creator", 201),
        ("delivered", "deliverable", "creator", 409),
    ],
)
async def test_create_enforces_purpose_role_and_booking_lifecycle(
    email_cleanup: list[str],
    fake_storage: FakeStorage,
    status: str,
    purpose: str,
    actor: Literal["client", "creator"],
    expected: int,
) -> None:
    with TestClient(app_with_storage(fake_storage)) as client:
        booking_id, _, creator_email = await workspace(client, email_cleanup, status=status)
        if actor == "creator":
            logout(client)
            login(client, creator_email)
        response = client.post(
            f"/api/v1/bookings/{booking_id}/uploads",
            json=upload_payload(purpose=purpose),
        )
    assert response.status_code == expected, response.text


@pytest.mark.parametrize(
    "payload",
    [
        upload_payload(content_type="image/jpg"),
        upload_payload(content_type="IMAGE/JPEG"),
        upload_payload(content_type="application/zip"),
        upload_payload(size=0),
        upload_payload(size=-1),
        upload_payload(size=10 * 1024 * 1024 + 1),
        {**upload_payload(), "filename": "../brief.pdf"},
        {**upload_payload(), "filename": "folder/brief.pdf"},
        {**upload_payload(), "filename": "folder\\brief.pdf"},
        {**upload_payload(), "filename": "brief\x00.pdf"},
        {**upload_payload(), "filename": "brief\x7f.pdf"},
    ],
)
async def test_create_rejects_invalid_metadata(
    email_cleanup: list[str], fake_storage: FakeStorage, payload: dict[str, object]
) -> None:
    with TestClient(app_with_storage(fake_storage)) as client:
        booking_id, _, _ = await workspace(client, email_cleanup)
        response = client.post(f"/api/v1/bookings/{booking_id}/uploads", json=payload)
    assert response.status_code == 422
    assert fake_storage.upload_keys == []


async def test_creator_deliverable_accepts_zip_at_exact_limit(
    email_cleanup: list[str], fake_storage: FakeStorage
) -> None:
    with TestClient(app_with_storage(fake_storage)) as client:
        booking_id, _, creator_email = await workspace(client, email_cleanup, status="in_progress")
        logout(client)
        login(client, creator_email)
        response = client.post(
            f"/api/v1/bookings/{booking_id}/uploads",
            json=upload_payload(
                purpose="deliverable", content_type="application/zip", size=100 * 1024 * 1024
            ),
        )
        fake_storage.objects[fake_storage.upload_keys[-1]] = StoredObject(
            size_bytes=100 * 1024 * 1024,
            content_type="application/zip",
            signature=ZIP_SIGNATURE,
        )
        completed = client.post(f"/api/v1/uploads/{response.json()['data']['id']}/complete")
    assert response.status_code == 201, response.text
    assert completed.status_code == 200, completed.text
    assert completed.json()["data"]["status"] == "completed"


async def test_client_chat_create_and_complete_across_writable_statuses(
    email_cleanup: list[str], fake_storage: FakeStorage
) -> None:
    with TestClient(app_with_storage(fake_storage)) as client:
        booking_id, _, _ = await workspace(client, email_cleanup)
        for status in ("confirmed", "in_progress", "delivered"):
            async with fresh_connection() as connection:
                await connection.execute(
                    text("UPDATE bookings SET status = :status WHERE id = :id"),
                    {"status": status, "id": booking_id},
                )
            upload = await create_stored_intent(client, booking_id, fake_storage)
            completed = client.post(f"/api/v1/uploads/{upload['id']}/complete")
            assert completed.status_code == 200, completed.text


async def create_stored_intent(
    client: TestClient,
    booking_id: str,
    fake_storage: FakeStorage,
    *,
    stored: StoredObject | Exception | None = None,
) -> dict[str, object]:
    response = client.post(f"/api/v1/bookings/{booking_id}/uploads", json=upload_payload())
    assert response.status_code == 201, response.text
    upload = response.json()["data"]
    fake_storage.objects[fake_storage.upload_keys[-1]] = stored or StoredObject(
        size_bytes=10, content_type="application/pdf", signature=PDF_SIGNATURE
    )
    return upload


async def test_completion_is_owner_only_one_time_and_download_is_participant_authorized(
    email_cleanup: list[str], fake_storage: FakeStorage
) -> None:
    with TestClient(app_with_storage(fake_storage)) as client:
        booking_id, client_email, creator_email = await workspace(client, email_cleanup)
        upload = await create_stored_intent(client, booking_id, fake_storage)
        logout(client)
        login(client, creator_email)
        creator_cannot_complete = client.post(f"/api/v1/uploads/{upload['id']}/complete")
        logout(client)
        login(client, client_email)
        completed = client.post(f"/api/v1/uploads/{upload['id']}/complete")
        replay = client.post(f"/api/v1/uploads/{upload['id']}/complete")
        own_download = client.post(f"/api/v1/uploads/{upload['id']}/download")
        logout(client)
        login(client, creator_email)
        creator_download = client.post(f"/api/v1/uploads/{upload['id']}/download")
        logout(client)
        register(client, email_cleanup, "Outsider download")
        outsider_complete = client.post(f"/api/v1/uploads/{upload['id']}/complete")
        outsider_download = client.post(f"/api/v1/uploads/{upload['id']}/download")
        unknown_complete = client.post(f"/api/v1/uploads/{uuid.uuid4()}/complete")
        unknown_download = client.post(f"/api/v1/uploads/{uuid.uuid4()}/download")
        outsider_email = email_cleanup[-1]
        await make_admin(outsider_email)
        admin_complete = client.post(f"/api/v1/uploads/{upload['id']}/complete")
        admin_download = client.post(f"/api/v1/uploads/{upload['id']}/download")

    assert creator_cannot_complete.status_code == 404
    assert completed.status_code == 200
    assert completed.json()["data"]["status"] == "completed"
    assert replay.status_code == 409
    assert replay.json()["error"]["code"] == "UPLOAD_ALREADY_COMPLETED"
    assert own_download.status_code == creator_download.status_code == 200
    assert own_download.json()["data"] == {"url": "https://storage.test/download/signed"}
    hidden = (
        outsider_complete,
        outsider_download,
        unknown_complete,
        unknown_download,
        admin_complete,
        admin_download,
    )
    assert all(response.status_code == 404 for response in hidden)
    assert all(response.json()["error"]["code"] == "UPLOAD_NOT_FOUND" for response in hidden)
    assert fake_storage.inspect_calls == 1


async def test_client_cannot_complete_deliverable_purpose_even_if_row_is_malformed(
    email_cleanup: list[str], fake_storage: FakeStorage
) -> None:
    with TestClient(app_with_storage(fake_storage)) as client:
        booking_id, _, _ = await workspace(client, email_cleanup)
        upload = await create_stored_intent(client, booking_id, fake_storage)
        async with fresh_connection() as connection:
            await connection.execute(
                text("UPDATE bookings SET status = 'in_progress' WHERE id = :id"),
                {"id": booking_id},
            )
            await connection.execute(
                text("UPDATE upload_intents SET purpose = 'deliverable' WHERE id = :id"),
                {"id": upload["id"]},
            )
        response = client.post(f"/api/v1/uploads/{upload['id']}/complete")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "UPLOAD_NOT_FOUND"
    assert (await intent_row(str(upload["id"]))).status == "pending"
    assert fake_storage.inspect_calls == 0


@pytest.mark.parametrize(
    ("stored", "expected_code"),
    [
        (StoredObject(11, "application/pdf", PDF_SIGNATURE), "UPLOAD_VALIDATION_FAILED"),
        (StoredObject(10, "image/png", b"\x89PNG\r\n\x1a\n"), "UPLOAD_VALIDATION_FAILED"),
        (StoredObject(10, "application/pdf", b"not-a-pdf"), "UPLOAD_VALIDATION_FAILED"),
        (FileNotFoundError("secret key"), "UPLOAD_VALIDATION_FAILED"),
        (OSError("provider internal hostname"), "STORAGE_UNAVAILABLE"),
    ],
)
async def test_completion_maps_storage_and_metadata_failures_without_details(
    email_cleanup: list[str],
    fake_storage: FakeStorage,
    stored: StoredObject | Exception,
    expected_code: str,
) -> None:
    with TestClient(app_with_storage(fake_storage)) as client:
        booking_id, _, _ = await workspace(client, email_cleanup)
        upload = await create_stored_intent(client, booking_id, fake_storage, stored=stored)
        response = client.post(f"/api/v1/uploads/{upload['id']}/complete")
    assert response.status_code == (503 if expected_code == "STORAGE_UNAVAILABLE" else 422)
    assert response.json()["error"]["code"] == expected_code
    assert "secret key" not in response.text
    assert "provider internal hostname" not in response.text
    assert (await intent_row(str(upload["id"]))).status == "pending"


@pytest.mark.parametrize(
    "storage_error",
    [
        EndpointConnectionError(endpoint_url="http://provider-secret"),
        ReadTimeoutError(endpoint_url="http://provider-secret", error="read-secret"),
        NoCredentialsError(),
    ],
)
async def test_completion_maps_real_botocore_failures_to_sanitized_unavailable(
    email_cleanup: list[str], fake_storage: FakeStorage, storage_error: Exception
) -> None:
    with TestClient(app_with_storage(fake_storage), raise_server_exceptions=False) as client:
        booking_id, _, _ = await workspace(client, email_cleanup)
        upload = await create_stored_intent(client, booking_id, fake_storage, stored=storage_error)
        response = client.post(f"/api/v1/uploads/{upload['id']}/complete")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert "provider-secret" not in response.text
    assert "read-secret" not in response.text
    assert (await intent_row(str(upload["id"]))).status == "pending"


async def test_expired_completion_is_durably_marked_and_not_downloadable(
    email_cleanup: list[str], fake_storage: FakeStorage
) -> None:
    with TestClient(app_with_storage(fake_storage)) as client:
        booking_id, _, _ = await workspace(client, email_cleanup)
        upload = await create_stored_intent(client, booking_id, fake_storage)
        async with fresh_connection() as connection:
            await connection.execute(
                text(
                    "UPDATE upload_intents "
                    "SET expires_at = now() - interval '1 minute' WHERE id = :id"
                ),
                {"id": upload["id"]},
            )
        completed = client.post(f"/api/v1/uploads/{upload['id']}/complete")
        downloaded = client.post(f"/api/v1/uploads/{upload['id']}/download")
    assert completed.status_code == downloaded.status_code == 410
    assert (
        completed.json()["error"]["code"] == downloaded.json()["error"]["code"] == "UPLOAD_EXPIRED"
    )
    assert (await intent_row(str(upload["id"]))).status == "expired"
    assert fake_storage.inspect_calls == 0


async def test_completion_expiring_during_storage_inspection_is_durably_expired(
    email_cleanup: list[str], fake_storage: FakeStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    before_expiry = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    expires_at = before_expiry + timedelta(seconds=1)
    after_expiry = expires_at + timedelta(seconds=1)

    class ControlledDateTime:
        current = before_expiry

        @classmethod
        def now(cls, timezone: object) -> datetime:
            assert timezone is UTC
            return cls.current

    with TestClient(app_with_storage(fake_storage)) as client:
        booking_id, _, _ = await workspace(client, email_cleanup)
        upload = await create_stored_intent(client, booking_id, fake_storage)
        async with fresh_connection() as connection:
            await connection.execute(
                text("UPDATE upload_intents SET expires_at = :expires_at WHERE id = :id"),
                {"expires_at": expires_at, "id": upload["id"]},
            )
        fake_storage.after_inspect = lambda: setattr(ControlledDateTime, "current", after_expiry)
        monkeypatch.setattr(upload_service, "datetime", ControlledDateTime)
        response = client.post(f"/api/v1/uploads/{upload['id']}/complete")

    intent = await intent_row(str(upload["id"]))
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "UPLOAD_EXPIRED"
    assert intent.status == "expired"
    assert intent.completed_at is None


async def test_clock_expired_pending_download_is_durably_marked_expired(
    email_cleanup: list[str], fake_storage: FakeStorage
) -> None:
    with TestClient(app_with_storage(fake_storage)) as client:
        booking_id, _, _ = await workspace(client, email_cleanup)
        upload = await create_stored_intent(client, booking_id, fake_storage)
        async with fresh_connection() as connection:
            await connection.execute(
                text(
                    "UPDATE upload_intents "
                    "SET expires_at = now() - interval '1 minute' WHERE id = :id"
                ),
                {"id": upload["id"]},
            )
        response = client.post(f"/api/v1/uploads/{upload['id']}/download")

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "UPLOAD_EXPIRED"
    assert (await intent_row(str(upload["id"]))).status == "expired"


async def test_pending_rejected_and_terminal_booking_state_errors(
    email_cleanup: list[str], fake_storage: FakeStorage
) -> None:
    with TestClient(app_with_storage(fake_storage)) as client:
        booking_id, _, _ = await workspace(client, email_cleanup)
        upload = await create_stored_intent(client, booking_id, fake_storage)
        pending_download = client.post(f"/api/v1/uploads/{upload['id']}/download")
        async with fresh_connection() as connection:
            await connection.execute(
                text("UPDATE upload_intents SET status = 'rejected' WHERE id = :id"),
                {"id": upload["id"]},
            )
        rejected_complete = client.post(f"/api/v1/uploads/{upload['id']}/complete")
        rejected_download = client.post(f"/api/v1/uploads/{upload['id']}/download")
        async with fresh_connection() as connection:
            await connection.execute(
                text("UPDATE upload_intents SET status = 'pending' WHERE id = :id"),
                {"id": upload["id"]},
            )
            await connection.execute(
                text("UPDATE bookings SET status = 'completed' WHERE id = :id"),
                {"id": booking_id},
            )
        terminal_complete = client.post(f"/api/v1/uploads/{upload['id']}/complete")

    assert pending_download.status_code == 409
    assert pending_download.json()["error"]["code"] == "UPLOAD_NOT_READY"
    assert rejected_complete.status_code == rejected_download.status_code == 409
    assert rejected_complete.json()["error"]["code"] == "UPLOAD_REJECTED"
    assert terminal_complete.status_code == 409
    assert terminal_complete.json()["error"]["code"] == "UPLOAD_BOOKING_NOT_WRITABLE"
    assert (await intent_row(str(upload["id"]))).status == "pending"


async def test_completed_download_remains_available_after_terminal_booking(
    email_cleanup: list[str], fake_storage: FakeStorage
) -> None:
    with TestClient(app_with_storage(fake_storage)) as client:
        booking_id, client_email, creator_email = await workspace(client, email_cleanup)
        upload = await create_stored_intent(client, booking_id, fake_storage)
        assert client.post(f"/api/v1/uploads/{upload['id']}/complete").status_code == 200
        responses = []
        for status in ("completed", "cancelled"):
            async with fresh_connection() as connection:
                await connection.execute(
                    text("UPDATE bookings SET status = :status WHERE id = :id"),
                    {"status": status, "id": booking_id},
                )
            login(client, client_email)
            responses.append(client.post(f"/api/v1/uploads/{upload['id']}/download"))
            logout(client)
            login(client, creator_email)
            responses.append(client.post(f"/api/v1/uploads/{upload['id']}/download"))
            logout(client)
    assert all(response.status_code == 200 for response in responses)


async def test_concurrent_completion_has_exactly_one_success(
    email_cleanup: list[str], fake_storage: FakeStorage
) -> None:
    with TestClient(app_with_storage(fake_storage)) as client:
        booking_id, client_email, _ = await workspace(client, email_cleanup)
        upload = await create_stored_intent(client, booking_id, fake_storage)

    engine = create_async_engine(upload_service.get_settings().database_url, poolclass=None)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    fake_storage.inspect_started = asyncio.Event()
    fake_storage.release_inspect = asyncio.Event()
    transition_attempting = asyncio.Event()
    transition_acquired = asyncio.Event()
    transition_pid: int | None = None

    async def worker() -> str:
        async with factory() as session:
            user = await session.scalar(select(User).where(User.email == client_email))
            assert user is not None
            try:
                result = await upload_service.complete_intent(
                    session,
                    upload_id=uuid.UUID(str(upload["id"])),
                    user=user,
                    storage=fake_storage,
                )
                return result.status
            except DomainError as error:
                await session.rollback()
                return error.code

    async def transition_booking() -> str:
        nonlocal transition_pid
        async with factory() as session:
            transition_pid = await session.scalar(text("SELECT pg_backend_pid()"))
            assert transition_pid is not None
            transition_attempting.set()
            booking = await session.scalar(
                select(Booking).where(Booking.id == uuid.UUID(booking_id)).with_for_update()
            )
            assert booking is not None
            transition_acquired.set()
            booking.status = "completed"
            await session.commit()
            return booking.status

    try:
        first = asyncio.create_task(worker())
        await asyncio.wait_for(fake_storage.inspect_started.wait(), timeout=5)
        second = asyncio.create_task(worker())
        transition = asyncio.create_task(transition_booking())
        await asyncio.wait_for(transition_attempting.wait(), timeout=5)
        blockers: list[int] = []
        for _ in range(100):
            async with factory() as monitor:
                blockers = list(
                    await monitor.scalar(
                        text("SELECT pg_blocking_pids(:pid)"), {"pid": transition_pid}
                    )
                    or []
                )
            if blockers or transition_acquired.is_set():
                break
            await asyncio.sleep(0.02)
        assert blockers
        assert not transition_acquired.is_set()
        assert not second.done()
        fake_storage.release_inspect.set()
        results = await asyncio.wait_for(asyncio.gather(first, second), timeout=10)
        transition_result = await asyncio.wait_for(transition, timeout=10)
    finally:
        fake_storage.release_inspect.set()
        await engine.dispose()

    assert sorted(results) == ["UPLOAD_ALREADY_COMPLETED", "completed"]
    assert transition_result == "completed"
    assert fake_storage.inspect_calls == 1
