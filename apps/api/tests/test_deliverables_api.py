import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api import deliverables as deliverable_api
from app.api.workspace_schemas import ExternalDeliverableRequest, PrivateDeliverableRequest
from app.core.config import get_settings
from app.core.errors import DomainError
from app.db.models import Deliverable, User
from app.main import create_app
from app.realtime import ConnectionHub
from app.services import deliverables as deliverable_service
from app.services import uploads as upload_service
from tests.conftest import fresh_connection, make_admin, unique_email

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("valid_startup_environment")]
PASSWORD = "sandi-aman-123"


class FakeStorage:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.delete_error: Exception | None = None

    async def create_upload_url(self, **_: object) -> str:
        raise AssertionError("deliverables must not create upload URLs")

    async def inspect_object(self, **_: object) -> object:
        raise AssertionError("deliverables must not inspect objects")

    async def create_download_url(self, **_: object) -> str:
        raise AssertionError("deliverables must not create download URLs")

    async def delete_object(self, *, object_key: str) -> None:
        self.deleted.append(object_key)
        if self.delete_error is not None:
            raise self.delete_error


class BlockingStorage(FakeStorage):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.completed = asyncio.Event()
        self.was_cancelled = False

    async def delete_object(self, *, object_key: str) -> None:
        self.deleted.append(object_key)
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.was_cancelled = True
            raise
        self.completed.set()


class RecordingHub(ConnectionHub):
    def __init__(self) -> None:
        self.events: list[tuple[uuid.UUID, dict[str, object]]] = []
        self.error: Exception | None = None

    async def broadcast(self, conversation_id: uuid.UUID, event: dict[str, object]) -> None:
        if self.error is not None:
            raise self.error
        self.events.append((conversation_id, event))

    async def close(self) -> None:
        return None


class BlockingBroadcastHub(ConnectionHub):
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.attempts = 0
        self.was_cancelled = False

    async def broadcast(self, conversation_id: uuid.UUID, event: dict[str, object]) -> None:
        del conversation_id, event
        self.attempts += 1
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.was_cancelled = True
            raise

    async def close(self) -> None:
        self.release.set()


class ConstraintViolation(Exception):
    def __init__(self, constraint_name: str) -> None:
        super().__init__("database detail must not escape")
        self.constraint_name = constraint_name


@pytest.fixture
async def deliverable_cleanup(email_cleanup: list[str]) -> AsyncIterator[None]:
    yield
    if email_cleanup:
        async with fresh_connection() as connection:
            await connection.execute(
                text(
                    "DELETE FROM deliverables WHERE uploaded_by_user_id IN "
                    "(SELECT id FROM users WHERE email = ANY(:emails))"
                ),
                {"emails": email_cleanup},
            )
            await connection.execute(
                text(
                    "DELETE FROM upload_intents WHERE requested_by_user_id IN "
                    "(SELECT id FROM users WHERE email = ANY(:emails))"
                ),
                {"emails": email_cleanup},
            )


@pytest.fixture
def app_bundle(deliverable_cleanup: None) -> tuple[FastAPI, FakeStorage, RecordingHub]:
    storage = FakeStorage()
    hub = RecordingHub()
    app = create_app()
    app.dependency_overrides[upload_service.get_storage_adapter] = lambda: storage
    app.state.connection_hub = hub
    return app, storage, hub


def register(client: TestClient, cleanup: list[str], name: str) -> str:
    email = unique_email("delivery")
    cleanup.append(email)
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


async def workspace(
    client: TestClient,
    cleanup: list[str],
    *,
    status: str = "in_progress",
    conversation: bool = True,
) -> tuple[str, str, str, str | None]:
    creator_email = register(client, cleanup, "Kreator Hasil")
    profile = client.put(
        "/api/v1/profiles/me/creator",
        json={
            "display_name": "Studio Hasil",
            "city": "Bandung",
            "bio": "Hasil privat.",
            "specialty": "wedding",
            "starting_price_idr": 1_500_000,
        },
    ).json()["data"]
    async with fresh_connection() as connection_db:
        await connection_db.execute(
            text("UPDATE creator_profiles SET status='approved' WHERE id=:id"),
            {"id": profile["id"]},
        )
    logout(client)
    client_email = register(client, cleanup, "Klien Hasil")
    booking = client.post(
        "/api/v1/bookings",
        json={
            "creator_id": profile["id"],
            "event_date": (datetime.now(UTC).date() + timedelta(days=90)).isoformat(),
            "event_city": "Bandung",
        },
    ).json()["data"]
    async with fresh_connection() as connection_db:
        await connection_db.execute(
            text("UPDATE bookings SET status=:status WHERE id=:id"),
            {"status": status, "id": booking["id"]},
        )
    conversation_id = None
    if conversation and status in {"confirmed", "in_progress", "delivered"}:
        conversation_id = client.get(f"/api/v1/bookings/{booking['id']}/conversation").json()[
            "data"
        ]["id"]
    return booking["id"], client_email, creator_email, conversation_id


async def completed_upload(
    booking_id: str,
    creator_email: str,
    *,
    purpose: str = "deliverable",
    status: str = "completed",
    object_key: str | None = None,
) -> tuple[str, str]:
    upload_id = uuid.uuid4()
    key = object_key or f"deliverable/{booking_id}/{uuid.uuid4().hex}"
    async with fresh_connection() as connection:
        await connection.execute(
            text(
                """
                INSERT INTO upload_intents (
                    id, booking_id, requested_by_user_id, purpose, object_key,
                    filename, content_type, size_bytes, status, expires_at, completed_at
                )
                SELECT :id, :booking_id, id, :purpose, :object_key,
                       'final.pdf', 'application/pdf', 1234, CAST(:status AS varchar),
                       now() + interval '1 hour',
                       CASE WHEN CAST(:status AS varchar) = 'completed' THEN now() ELSE NULL END
                FROM users WHERE email=:email
                """
            ),
            {
                "id": upload_id,
                "booking_id": booking_id,
                "purpose": purpose,
                "object_key": key,
                "status": status,
                "email": creator_email,
            },
        )
    return str(upload_id), key


def external_payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_type": "external_link",
        "title": "Galeri final",
        "description": "Unduh dalam 30 hari",
        "external_url": "https://Gallery.Example/final",
    }
    payload.update(changes)
    return payload


async def wait_for_pg_blocker(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    waiting_pid: int,
    expected_blocker_pid: int,
) -> None:
    async with asyncio.timeout(5):
        while True:
            async with session_factory() as monitor:
                blockers = list(
                    await monitor.scalar(
                        text("SELECT pg_blocking_pids(:pid)"), {"pid": waiting_pid}
                    )
                    or []
                )
            if expected_blocker_pid in blockers:
                return


def test_routes_require_authentication() -> None:
    with TestClient(create_app()) as client:
        responses = [
            client.get(f"/api/v1/bookings/{uuid.uuid4()}/deliverables"),
            client.post(f"/api/v1/bookings/{uuid.uuid4()}/deliverables", json=external_payload()),
            client.delete(f"/api/v1/deliverables/{uuid.uuid4()}"),
        ]
    assert [response.status_code for response in responses] == [401, 401, 401]


async def test_creator_creates_https_link_and_both_participants_list_safely(
    email_cleanup: list[str], app_bundle: tuple[FastAPI, FakeStorage, RecordingHub]
) -> None:
    app, storage, hub = app_bundle
    with TestClient(app) as client:
        booking_id, client_email, creator_email, conversation_id = await workspace(
            client, email_cleanup
        )
        logout(client)
        login(client, creator_email)
        created = client.post(
            f"/api/v1/bookings/{booking_id}/deliverables",
            json=external_payload(title="  Galeri final  "),
        )
        creator_list = client.get(f"/api/v1/bookings/{booking_id}/deliverables")
        logout(client)
        login(client, client_email)
        client_list = client.get(f"/api/v1/bookings/{booking_id}/deliverables")

    assert created.status_code == 201, created.text
    data = created.json()["data"]
    assert data["title"] == "Galeri final"
    assert data["external_url"] == "https://gallery.example/final"
    assert data["external_host"] == "gallery.example"
    assert data["downloadable"] is False
    assert not ({"object_key", "etag", "signed_url"} & data.keys())
    assert creator_list.json()["data"] == [data]
    assert client_list.json()["data"] == [data]
    assert storage.deleted == []
    assert hub.events == [
        (
            uuid.UUID(str(conversation_id)),
            {"type": "deliverable.updated", "data": data},
        )
    ]


@pytest.mark.parametrize(
    "url",
    [
        "http://gallery.example/final",
        "/relative",
        "ftp://gallery.example/final",
        "https://user:secret@gallery.example/final",
        "not a url",
    ],
)
async def test_external_url_rejects_unsafe_forms_without_fetch(
    email_cleanup: list[str], app_bundle: tuple[FastAPI, FakeStorage, RecordingHub], url: str
) -> None:
    app, _, _ = app_bundle
    with TestClient(app) as client:
        booking_id, _, creator_email, _ = await workspace(client, email_cleanup)
        logout(client)
        login(client, creator_email)
        response = client.post(
            f"/api/v1/bookings/{booking_id}/deliverables",
            json=external_payload(external_url=url),
        )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {**external_payload(), "upload_id": str(uuid.uuid4())},
        {"source_type": "private_file", "title": "Final"},
        {
            "source_type": "private_file",
            "title": "Final",
            "upload_id": str(uuid.uuid4()),
            "external_url": "https://example.test",
        },
        external_payload(extra="forbidden"),
        external_payload(title="\x00bad"),
        external_payload(description="bad\ud800"),
    ],
)
async def test_discriminated_source_and_plain_text_validation(
    email_cleanup: list[str], app_bundle: tuple[FastAPI, FakeStorage, RecordingHub], payload: object
) -> None:
    app, _, _ = app_bundle
    with TestClient(app) as client:
        booking_id, _, creator_email, _ = await workspace(client, email_cleanup)
        logout(client)
        login(client, creator_email)
        response = client.post(
            f"/api/v1/bookings/{booking_id}/deliverables",
            content=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 422


async def test_private_file_copies_safe_metadata_and_is_single_use(
    email_cleanup: list[str], app_bundle: tuple[FastAPI, FakeStorage, RecordingHub]
) -> None:
    app, _, _ = app_bundle
    with TestClient(app) as client:
        booking_id, _, creator_email, _ = await workspace(client, email_cleanup)
        upload_id, _ = await completed_upload(booking_id, creator_email)
        logout(client)
        login(client, creator_email)
        first = client.post(
            f"/api/v1/bookings/{booking_id}/deliverables",
            json={"source_type": "private_file", "title": "Final", "upload_id": upload_id},
        )
        reused = client.post(
            f"/api/v1/bookings/{booking_id}/deliverables",
            json={"source_type": "private_file", "title": "Copy", "upload_id": upload_id},
        )
    assert first.status_code == 201, first.text
    assert {
        "source_type": "private_file",
        "upload_id": upload_id,
        "filename": "final.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1234,
        "downloadable": True,
    }.items() <= first.json()["data"].items()
    assert "object_key" not in first.text
    assert reused.status_code == 409
    assert reused.json()["error"]["code"] == "UPLOAD_ALREADY_USED"


async def test_create_never_refreshes_after_commit(
    email_cleanup: list[str],
    app_bundle: tuple[FastAPI, FakeStorage, RecordingHub],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _, _ = app_bundle
    with TestClient(app) as client:
        booking_id, _, creator_email, _ = await workspace(client, email_cleanup)
        logout(client)
        login(client, creator_email)
        original_commit = AsyncSession.commit
        original_refresh = AsyncSession.refresh
        committed_sessions: set[int] = set()
        post_commit_refreshes: list[uuid.UUID] = []

        async def tracked_commit(session: AsyncSession) -> None:
            await original_commit(session)
            committed_sessions.add(id(session))

        async def tracked_refresh(
            session: AsyncSession, instance: object, *args: object, **kwargs: object
        ) -> None:
            if isinstance(instance, Deliverable) and id(session) in committed_sessions:
                post_commit_refreshes.append(instance.id)
            await original_refresh(session, instance, *args, **kwargs)

        monkeypatch.setattr(AsyncSession, "commit", tracked_commit)
        monkeypatch.setattr(AsyncSession, "refresh", tracked_refresh)
        response = client.post(
            f"/api/v1/bookings/{booking_id}/deliverables", json=external_payload()
        )
    assert response.status_code == 201, response.text
    assert post_commit_refreshes == []


async def test_precommit_refresh_failure_leaves_no_deliverable(
    email_cleanup: list[str],
    app_bundle: tuple[FastAPI, FakeStorage, RecordingHub],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _, _ = app_bundle
    with TestClient(app) as client:
        booking_id, _, creator_email, _ = await workspace(client, email_cleanup)
        logout(client)
        login(client, creator_email)
        original_refresh = AsyncSession.refresh

        async def fail_deliverable_refresh(
            session: AsyncSession, instance: object, *args: object, **kwargs: object
        ) -> None:
            if isinstance(instance, Deliverable):
                raise RuntimeError("deterministic pre-commit refresh fault")
            await original_refresh(session, instance, *args, **kwargs)

        monkeypatch.setattr(AsyncSession, "refresh", fail_deliverable_refresh)
        with pytest.raises(RuntimeError, match="pre-commit refresh fault"):
            client.post(f"/api/v1/bookings/{booking_id}/deliverables", json=external_payload())
    async with fresh_connection() as connection:
        count = await connection.scalar(
            text("SELECT count(*) FROM deliverables WHERE booking_id=:booking_id"),
            {"booking_id": booking_id},
        )
    assert count == 0


@pytest.mark.parametrize(
    ("constraint_name", "expected_code"),
    [
        ("deliverables_upload_id_key", "UPLOAD_ALREADY_USED"),
        ("unrelated_database_constraint", None),
    ],
)
async def test_create_maps_only_the_upload_unique_constraint(
    email_cleanup: list[str],
    app_bundle: tuple[FastAPI, FakeStorage, RecordingHub],
    monkeypatch: pytest.MonkeyPatch,
    constraint_name: str,
    expected_code: str | None,
) -> None:
    app, _, _ = app_bundle
    with TestClient(app) as client:
        booking_id, _, creator_email, _ = await workspace(client, email_cleanup)
        upload_id, _ = await completed_upload(booking_id, creator_email)
        logout(client)
        login(client, creator_email)
        original_flush = AsyncSession.flush

        async def fail_deliverable_flush(
            session: AsyncSession, objects: object | None = None
        ) -> None:
            if any(isinstance(value, Deliverable) for value in session.new):
                raise IntegrityError(
                    "INSERT INTO deliverables", {}, ConstraintViolation(constraint_name)
                )
            await original_flush(session, objects)

        monkeypatch.setattr(AsyncSession, "flush", fail_deliverable_flush)
        if expected_code is None:
            with pytest.raises(IntegrityError):
                client.post(
                    f"/api/v1/bookings/{booking_id}/deliverables",
                    json={"source_type": "private_file", "title": "Final", "upload_id": upload_id},
                )
        else:
            response = client.post(
                f"/api/v1/bookings/{booking_id}/deliverables",
                json={"source_type": "private_file", "title": "Final", "upload_id": upload_id},
            )
            assert response.status_code == 409
            assert response.json()["error"]["code"] == expected_code
    async with fresh_connection() as connection:
        count = await connection.scalar(
            text("SELECT count(*) FROM deliverables WHERE booking_id=:booking_id"),
            {"booking_id": booking_id},
        )
    assert count == 0


async def test_concurrent_creates_consume_private_upload_once(
    email_cleanup: list[str],
    app_bundle: tuple[FastAPI, FakeStorage, RecordingHub],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _, _ = app_bundle
    with TestClient(app) as client:
        booking_id, _, creator_email, _ = await workspace(client, email_cleanup)
        upload_id, _ = await completed_upload(booking_id, creator_email)

    engine = create_async_engine(get_settings().database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    payload = PrivateDeliverableRequest(
        source_type="private_file", title="Final bersamaan", upload_id=uuid.UUID(upload_id)
    )
    original_access = deliverable_service.require_booking_participant
    holder_locked = asyncio.Event()
    release_holder = asyncio.Event()
    worker_started = {"holder": asyncio.Event(), "waiter": asyncio.Event()}
    worker_pids: dict[str, int] = {}
    holder_task: asyncio.Task[object] | None = None

    async def hold_first_booking_lock(*args: object, **kwargs: object) -> object:
        access = await original_access(*args, **kwargs)  # type: ignore[arg-type]
        if asyncio.current_task() is holder_task:
            holder_locked.set()
            await release_holder.wait()
        return access

    monkeypatch.setattr(deliverable_service, "require_booking_participant", hold_first_booking_lock)

    async def create_once(label: str) -> object:
        async with session_factory() as session:
            creator = await session.scalar(select(User).where(User.email == creator_email))
            assert creator is not None
            pid = await session.scalar(text("SELECT pg_backend_pid()"))
            assert pid is not None
            worker_pids[label] = pid
            worker_started[label].set()
            return await deliverable_service.create_deliverable(
                session, booking_id=uuid.UUID(booking_id), user=creator, payload=payload
            )

    waiter_task: asyncio.Task[object] | None = None
    try:
        holder_task = asyncio.create_task(create_once("holder"))
        await asyncio.wait_for(holder_locked.wait(), timeout=5)
        waiter_task = asyncio.create_task(create_once("waiter"))
        await asyncio.wait_for(worker_started["waiter"].wait(), timeout=5)
        await wait_for_pg_blocker(
            session_factory,
            waiting_pid=worker_pids["waiter"],
            expected_blocker_pid=worker_pids["holder"],
        )
        assert waiter_task.done() is False
        release_holder.set()
        results = await asyncio.wait_for(
            asyncio.gather(holder_task, waiter_task, return_exceptions=True), timeout=10
        )
    finally:
        release_holder.set()
        pending = [
            task for task in (holder_task, waiter_task) if task is not None and not task.done()
        ]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        await engine.dispose()

    successes = [
        result for result in results if isinstance(result, deliverable_service.DeliverableMutation)
    ]
    failures = [result for result in results if isinstance(result, DomainError)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert failures[0].code == "UPLOAD_ALREADY_USED"
    assert not any(isinstance(result, IntegrityError) for result in results)
    async with fresh_connection() as connection:
        count = await connection.scalar(
            text("SELECT count(*) FROM deliverables WHERE upload_id=:upload_id"),
            {"upload_id": upload_id},
        )
    assert count == 1


async def test_replacement_create_racing_original_delete_keeps_chain_valid(
    email_cleanup: list[str],
    app_bundle: tuple[FastAPI, FakeStorage, RecordingHub],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _, _ = app_bundle
    with TestClient(app) as client:
        booking_id, _, creator_email, _ = await workspace(client, email_cleanup)
        logout(client)
        login(client, creator_email)
        original_id = client.post(
            f"/api/v1/bookings/{booking_id}/deliverables", json=external_payload()
        ).json()["data"]["id"]

    engine = create_async_engine(get_settings().database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    original_access = deliverable_service.require_booking_participant
    holder_locked = asyncio.Event()
    release_holder = asyncio.Event()
    waiter_started = asyncio.Event()
    worker_pids: dict[str, int] = {}
    holder_task: asyncio.Task[object] | None = None

    async def hold_replacement_booking_lock(*args: object, **kwargs: object) -> object:
        access = await original_access(*args, **kwargs)  # type: ignore[arg-type]
        if asyncio.current_task() is holder_task:
            holder_locked.set()
            await release_holder.wait()
        return access

    monkeypatch.setattr(
        deliverable_service, "require_booking_participant", hold_replacement_booking_lock
    )

    async def create_replacement() -> object:
        async with session_factory() as session:
            creator = await session.scalar(select(User).where(User.email == creator_email))
            assert creator is not None
            pid = await session.scalar(text("SELECT pg_backend_pid()"))
            assert pid is not None
            worker_pids["holder"] = pid
            return await deliverable_service.create_deliverable(
                session,
                booking_id=uuid.UUID(booking_id),
                user=creator,
                payload=ExternalDeliverableRequest(
                    source_type="external_link",
                    title="Revisi bersamaan",
                    external_url="https://gallery.example/revision",
                    replaces_deliverable_id=uuid.UUID(original_id),
                ),
            )

    async def delete_original() -> object:
        async with session_factory() as session:
            creator = await session.scalar(select(User).where(User.email == creator_email))
            assert creator is not None
            pid = await session.scalar(text("SELECT pg_backend_pid()"))
            assert pid is not None
            worker_pids["waiter"] = pid
            waiter_started.set()
            return await deliverable_service.delete_deliverable(
                session, deliverable_id=uuid.UUID(original_id), user=creator
            )

    waiter_task: asyncio.Task[object] | None = None
    try:
        holder_task = asyncio.create_task(create_replacement())
        await asyncio.wait_for(holder_locked.wait(), timeout=5)
        waiter_task = asyncio.create_task(delete_original())
        await asyncio.wait_for(waiter_started.wait(), timeout=5)
        await wait_for_pg_blocker(
            session_factory,
            waiting_pid=worker_pids["waiter"],
            expected_blocker_pid=worker_pids["holder"],
        )
        assert waiter_task.done() is False
        release_holder.set()
        results = await asyncio.wait_for(
            asyncio.gather(holder_task, waiter_task, return_exceptions=True), timeout=10
        )
    finally:
        release_holder.set()
        pending = [
            task for task in (holder_task, waiter_task) if task is not None and not task.done()
        ]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        await engine.dispose()

    assert not any(isinstance(result, IntegrityError) for result in results)
    failures = [result for result in results if isinstance(result, DomainError)]
    assert len(failures) == 1
    assert failures[0].code == "DELIVERABLE_HAS_REVISIONS"
    assert (
        sum(
            isinstance(
                result,
                (deliverable_service.DeliverableMutation, deliverable_service.DeliverableDeletion),
            )
            for result in results
        )
        == 1
    )
    async with fresh_connection() as connection:
        dangling = await connection.scalar(
            text(
                "SELECT count(*) FROM deliverables child "
                "LEFT JOIN deliverables parent ON parent.id=child.replaces_deliverable_id "
                "WHERE child.booking_id=:booking_id "
                "AND child.replaces_deliverable_id IS NOT NULL AND parent.id IS NULL"
            ),
            {"booking_id": booking_id},
        )
    assert dangling == 0


@pytest.mark.parametrize(
    ("purpose", "upload_status"),
    [("chat_attachment", "completed"), ("deliverable", "pending"), ("deliverable", "rejected")],
)
async def test_private_file_rejects_invalid_intent_with_sanitized_error(
    email_cleanup: list[str],
    app_bundle: tuple[FastAPI, FakeStorage, RecordingHub],
    purpose: str,
    upload_status: str,
) -> None:
    app, _, _ = app_bundle
    with TestClient(app) as client:
        booking_id, _, creator_email, _ = await workspace(client, email_cleanup)
        upload_id, key = await completed_upload(
            booking_id, creator_email, purpose=purpose, status=upload_status
        )
        logout(client)
        login(client, creator_email)
        response = client.post(
            f"/api/v1/bookings/{booking_id}/deliverables",
            json={"source_type": "private_file", "title": "Final", "upload_id": upload_id},
        )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "UPLOAD_NOT_FOUND"
    assert key not in response.text


async def test_private_file_rejects_other_owner_and_other_booking_uploads(
    email_cleanup: list[str], app_bundle: tuple[FastAPI, FakeStorage, RecordingHub]
) -> None:
    app, _, _ = app_bundle
    with TestClient(app) as client:
        booking_id, client_email, creator_email, _ = await workspace(client, email_cleanup)
        other_owner_upload, other_owner_key = await completed_upload(booking_id, client_email)
        async with fresh_connection() as connection:
            creator_profile_id = await connection.scalar(
                text(
                    "SELECT cp.id FROM creator_profiles cp "
                    "JOIN users u ON u.id=cp.user_id WHERE u.email=:email"
                ),
                {"email": creator_email},
            )
        logout(client)
        register(client, email_cleanup, "Klien Booking Lain")
        other_booking = client.post(
            "/api/v1/bookings",
            json={
                "creator_id": str(creator_profile_id),
                "event_date": (datetime.now(UTC).date() + timedelta(days=120)).isoformat(),
                "event_city": "Jakarta",
            },
        ).json()["data"]
        async with fresh_connection() as connection:
            await connection.execute(
                text("UPDATE bookings SET status='in_progress' WHERE id=:id"),
                {"id": other_booking["id"]},
            )
        other_booking_upload, other_booking_key = await completed_upload(
            other_booking["id"], creator_email
        )
        logout(client)
        login(client, creator_email)
        wrong_owner = client.post(
            f"/api/v1/bookings/{booking_id}/deliverables",
            json={
                "source_type": "private_file",
                "title": "Milik pengguna lain",
                "upload_id": other_owner_upload,
            },
        )
        wrong_booking = client.post(
            f"/api/v1/bookings/{booking_id}/deliverables",
            json={
                "source_type": "private_file",
                "title": "Milik booking lain",
                "upload_id": other_booking_upload,
            },
        )
        listing = client.get(f"/api/v1/bookings/{booking_id}/deliverables")
    assert wrong_owner.status_code == wrong_booking.status_code == 404
    assert wrong_owner.json()["error"]["code"] == "UPLOAD_NOT_FOUND"
    assert wrong_booking.json()["error"]["code"] == "UPLOAD_NOT_FOUND"
    assert other_owner_key not in wrong_owner.text
    assert other_booking_key not in wrong_booking.text
    assert listing.json()["data"] == []


async def test_write_role_lifecycle_and_anti_enumeration(
    email_cleanup: list[str], app_bundle: tuple[FastAPI, FakeStorage, RecordingHub]
) -> None:
    app, _, _ = app_bundle
    with TestClient(app) as client:
        booking_id, client_email, creator_email, _ = await workspace(client, email_cleanup)
        client_write = client.post(
            f"/api/v1/bookings/{booking_id}/deliverables", json=external_payload()
        )
        logout(client)
        login(client, creator_email)
        created = client.post(
            f"/api/v1/bookings/{booking_id}/deliverables", json=external_payload()
        ).json()["data"]
        logout(client)
        login(client, client_email)
        client_delete = client.delete(f"/api/v1/deliverables/{created['id']}")
        logout(client)
        outsider_email = register(client, email_cleanup, "Orang Luar")
        outsider_write = client.post(
            f"/api/v1/bookings/{booking_id}/deliverables", json=external_payload()
        )
        outsider_list = client.get(f"/api/v1/bookings/{booking_id}/deliverables")
        outsider_delete = client.delete(f"/api/v1/deliverables/{created['id']}")
        await make_admin(outsider_email)
        admin_write = client.post(
            f"/api/v1/bookings/{booking_id}/deliverables", json=external_payload()
        )
        admin_list = client.get(f"/api/v1/bookings/{booking_id}/deliverables")
        admin_delete = client.delete(f"/api/v1/deliverables/{created['id']}")
        logout(client)
        login(client, creator_email)
        async with fresh_connection() as connection:
            await connection.execute(
                text("UPDATE bookings SET status='delivered' WHERE id=:id"), {"id": booking_id}
            )
        wrong_lifecycle = client.post(
            f"/api/v1/bookings/{booking_id}/deliverables", json=external_payload()
        )
    assert created["title"] == "Galeri final"
    assert client_write.status_code == client_delete.status_code == 404
    assert outsider_write.status_code == outsider_list.status_code == 404
    assert outsider_delete.status_code == 404
    assert admin_write.status_code == admin_list.status_code == 404
    assert admin_delete.status_code == 404
    assert wrong_lifecycle.status_code == 409
    assert client_email != creator_email


async def test_revisions_are_append_only_and_cross_booking_is_rejected(
    email_cleanup: list[str], app_bundle: tuple[FastAPI, FakeStorage, RecordingHub]
) -> None:
    app, _, _ = app_bundle
    with TestClient(app) as client:
        first_booking, _, creator_email, _ = await workspace(client, email_cleanup)
        logout(client)
        login(client, creator_email)
        original = client.post(
            f"/api/v1/bookings/{first_booking}/deliverables", json=external_payload()
        ).json()["data"]
        logout(client)
        second_booking, _, second_creator, _ = await workspace(client, email_cleanup)
        logout(client)
        login(client, second_creator)
        cross = client.post(
            f"/api/v1/bookings/{second_booking}/deliverables",
            json=external_payload(replaces_deliverable_id=original["id"]),
        )
        own = client.post(
            f"/api/v1/bookings/{second_booking}/deliverables", json=external_payload()
        ).json()["data"]
        revision = client.post(
            f"/api/v1/bookings/{second_booking}/deliverables",
            json=external_payload(title="Revisi", replaces_deliverable_id=own["id"]),
        )
        listing = client.get(f"/api/v1/bookings/{second_booking}/deliverables").json()["data"]
        delete_replaced = client.delete(f"/api/v1/deliverables/{own['id']}")
    assert cross.status_code == 404
    assert revision.status_code == 201
    assert revision.json()["data"]["replaces_deliverable_id"] == own["id"]
    assert [item["title"] for item in listing] == ["Galeri final", "Revisi"]
    assert delete_replaced.status_code == 409
    assert delete_replaced.json()["error"]["code"] == "DELIVERABLE_HAS_REVISIONS"


async def test_delete_private_commits_rejection_then_cleans_storage_and_prevents_reuse(
    email_cleanup: list[str], app_bundle: tuple[FastAPI, FakeStorage, RecordingHub]
) -> None:
    app, storage, hub = app_bundle
    with TestClient(app) as client:
        booking_id, _, creator_email, conversation_id = await workspace(client, email_cleanup)
        upload_id, key = await completed_upload(booking_id, creator_email)
        logout(client)
        login(client, creator_email)
        created = client.post(
            f"/api/v1/bookings/{booking_id}/deliverables",
            json={"source_type": "private_file", "title": "Final", "upload_id": upload_id},
        ).json()["data"]
        deleted = client.delete(f"/api/v1/deliverables/{created['id']}")
        reuse = client.post(
            f"/api/v1/bookings/{booking_id}/deliverables",
            json={"source_type": "private_file", "title": "Again", "upload_id": upload_id},
        )
    async with fresh_connection() as connection:
        intent_status = await connection.scalar(
            text("SELECT status FROM upload_intents WHERE id=:id"), {"id": upload_id}
        )
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert storage.deleted == [key]
    assert intent_status == "rejected"
    assert reuse.status_code == 404
    assert hub.events[-1] == (
        uuid.UUID(str(conversation_id)),
        {
            "type": "deliverable.updated",
            "data": {
                "action": "deleted",
                "booking_id": booking_id,
                "deliverable_id": created["id"],
            },
        },
    )


async def test_cleanup_failure_logs_and_keeps_committed_deletion_event(
    email_cleanup: list[str],
    app_bundle: tuple[FastAPI, FakeStorage, RecordingHub],
    caplog: pytest.LogCaptureFixture,
) -> None:
    app, storage, hub = app_bundle
    with TestClient(app) as client:
        booking_id, _, creator_email, conversation_id = await workspace(client, email_cleanup)
        upload_id, key = await completed_upload(booking_id, creator_email)
        storage.delete_error = OSError(
            f"provider failed for secret-key at https://storage.internal/{key}"
        )
        logout(client)
        login(client, creator_email)
        created = client.post(
            f"/api/v1/bookings/{booking_id}/deliverables",
            json={"source_type": "private_file", "title": "Final", "upload_id": upload_id},
        ).json()["data"]
        with caplog.at_level(logging.WARNING, logger="app.services.deliverables"):
            deleted = client.delete(f"/api/v1/deliverables/{created['id']}")
        listing = client.get(f"/api/v1/bookings/{booking_id}/deliverables")
    assert deleted.status_code == 204
    assert listing.json()["data"] == []
    assert hub.events[-1] == (
        uuid.UUID(str(conversation_id)),
        {
            "type": "deliverable.updated",
            "data": {
                "action": "deleted",
                "booking_id": booking_id,
                "deliverable_id": created["id"],
            },
        },
    )
    assert "requires maintenance" in caplog.text
    assert created["id"] in caplog.text
    assert upload_id in caplog.text
    assert "OSError" in caplog.text
    assert key not in caplog.text
    assert "provider failed" not in caplog.text
    assert "storage.internal" not in caplog.text


async def test_delete_cancellation_preserves_event_and_shields_cleanup(
    email_cleanup: list[str], app_bundle: tuple[FastAPI, FakeStorage, RecordingHub]
) -> None:
    app, _, hub = app_bundle
    blocking_storage = BlockingStorage()
    with TestClient(app) as client:
        booking_id, _, creator_email, conversation_id = await workspace(client, email_cleanup)
        upload_id, key = await completed_upload(booking_id, creator_email)
        logout(client)
        login(client, creator_email)
        created = client.post(
            f"/api/v1/bookings/{booking_id}/deliverables",
            json={"source_type": "private_file", "title": "Final", "upload_id": upload_id},
        ).json()["data"]

        engine = create_async_engine(get_settings().database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                creator = await session.scalar(select(User).where(User.email == creator_email))
                assert creator is not None
                request = Request({"type": "http", "app": app})
                task = asyncio.create_task(
                    deliverable_api.delete_deliverable(
                        uuid.UUID(created["id"]), creator, session, blocking_storage, request
                    )
                )
                await blocking_storage.started.wait()
                task.cancel()
                blocking_storage.release.set()
                with pytest.raises(asyncio.CancelledError):
                    await task
        finally:
            await engine.dispose()

    assert blocking_storage.completed.is_set()
    assert blocking_storage.was_cancelled is False
    assert blocking_storage.deleted == [key]
    assert hub.events[-1] == (
        uuid.UUID(str(conversation_id)),
        {
            "type": "deliverable.updated",
            "data": {
                "action": "deleted",
                "booking_id": booking_id,
                "deliverable_id": created["id"],
            },
        },
    )
    async with fresh_connection() as connection:
        row = await connection.scalar(
            text("SELECT count(*) FROM deliverables WHERE id=:id"), {"id": created["id"]}
        )
        upload_status = await connection.scalar(
            text("SELECT status FROM upload_intents WHERE id=:id"), {"id": upload_id}
        )
    assert row == 0
    assert upload_status == "rejected"


async def test_broadcast_cancellation_still_owns_private_cleanup_once(
    email_cleanup: list[str],
    app_bundle: tuple[FastAPI, FakeStorage, RecordingHub],
    caplog: pytest.LogCaptureFixture,
) -> None:
    app, storage, _ = app_bundle
    with TestClient(app) as client:
        booking_id, _, creator_email, _ = await workspace(client, email_cleanup)
        upload_id, key = await completed_upload(booking_id, creator_email)
        logout(client)
        login(client, creator_email)
        created = client.post(
            f"/api/v1/bookings/{booking_id}/deliverables",
            json={"source_type": "private_file", "title": "Final", "upload_id": upload_id},
        ).json()["data"]

        blocking_hub = BlockingBroadcastHub()
        app.state.connection_hub = blocking_hub
        engine = create_async_engine(get_settings().database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as session:
                creator = await session.scalar(select(User).where(User.email == creator_email))
                assert creator is not None
                request = Request({"type": "http", "app": app})
                task = asyncio.create_task(
                    deliverable_api.delete_deliverable(
                        uuid.UUID(created["id"]), creator, session, storage, request
                    )
                )
                await asyncio.wait_for(blocking_hub.started.wait(), timeout=5)
                async with fresh_connection() as connection:
                    committed = await connection.scalar(
                        text("SELECT count(*) FROM deliverables WHERE id=:id"),
                        {"id": created["id"]},
                    )
                assert committed == 0
                with caplog.at_level(logging.WARNING):
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await asyncio.wait_for(task, timeout=5)
        finally:
            blocking_hub.release.set()
            await engine.dispose()

    assert blocking_hub.attempts == 1
    assert blocking_hub.was_cancelled is True
    assert storage.deleted == [key]
    assert key not in caplog.text
    async with fresh_connection() as connection:
        upload_status = await connection.scalar(
            text("SELECT status FROM upload_intents WHERE id=:id"), {"id": upload_id}
        )
    assert upload_status == "rejected"


async def test_broadcast_failure_does_not_change_committed_delete(
    email_cleanup: list[str], app_bundle: tuple[FastAPI, FakeStorage, RecordingHub]
) -> None:
    app, _, hub = app_bundle
    with TestClient(app) as client:
        booking_id, _, creator_email, _ = await workspace(client, email_cleanup)
        logout(client)
        login(client, creator_email)
        created = client.post(
            f"/api/v1/bookings/{booking_id}/deliverables", json=external_payload()
        ).json()["data"]
        hub.error = RuntimeError("hub unavailable")
        deleted = client.delete(f"/api/v1/deliverables/{created['id']}")
        listing = client.get(f"/api/v1/bookings/{booking_id}/deliverables")
    assert deleted.status_code == 204
    assert listing.json()["data"] == []


@pytest.mark.parametrize("status", ["delivered", "completed", "cancelled"])
async def test_published_or_terminal_deliverable_is_listable_but_immutable(
    email_cleanup: list[str],
    app_bundle: tuple[FastAPI, FakeStorage, RecordingHub],
    status: str,
) -> None:
    app, storage, _ = app_bundle
    with TestClient(app) as client:
        booking_id, _, creator_email, _ = await workspace(client, email_cleanup)
        logout(client)
        login(client, creator_email)
        created = client.post(
            f"/api/v1/bookings/{booking_id}/deliverables", json=external_payload()
        ).json()["data"]
        async with fresh_connection() as connection:
            await connection.execute(
                text("UPDATE bookings SET status=:status WHERE id=:id"),
                {"status": status, "id": booking_id},
            )
        listing = client.get(f"/api/v1/bookings/{booking_id}/deliverables")
        deleted = client.delete(f"/api/v1/deliverables/{created['id']}")
    assert listing.status_code == 200
    assert listing.json()["data"] == [created]
    assert deleted.status_code == 409
    assert storage.deleted == []
