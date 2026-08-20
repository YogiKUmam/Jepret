import asyncio
import base64
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.errors import DomainError
from app.db.models import Message, User
from app.main import create_app
from app.services import conversations as conversation_service
from app.services import uploads as upload_service
from app.services.conversations import decode_cursor
from tests.conftest import fresh_connection, make_admin, unique_email

pytestmark = pytest.mark.integration
PASSWORD = "sandi-aman-123"


def encoded_cursor(payload: object) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


INVALID_CURSOR_PAYLOADS = [
    pytest.param({"v": 1, "created_at": "2026-08-20T12:00:00.000000Z", "id": 123}, id="id-number"),
    pytest.param({"v": 1, "created_at": "2026-08-20T12:00:00.000000Z", "id": None}, id="id-null"),
    pytest.param({"v": 1, "created_at": "2026-08-20T12:00:00.000000Z", "id": {}}, id="id-object"),
    pytest.param({"v": 1, "created_at": "2026-08-20T12:00:00.000000Z", "id": []}, id="id-list"),
    pytest.param({"v": 1, "created_at": "2026-08-20T12:00:00.000000Z", "id": True}, id="id-bool"),
    pytest.param({"v": 1, "created_at": 123, "id": str(uuid.uuid4())}, id="timestamp-number"),
    pytest.param({"v": 1, "created_at": None, "id": str(uuid.uuid4())}, id="timestamp-null"),
    pytest.param(
        {"v": "1", "created_at": "2026-08-20T12:00:00.000000Z", "id": str(uuid.uuid4())},
        id="version-string",
    ),
    pytest.param(
        {"v": True, "created_at": "2026-08-20T12:00:00.000000Z", "id": str(uuid.uuid4())},
        id="version-bool",
    ),
    pytest.param(
        {"v": 2, "created_at": "2026-08-20T12:00:00.000000Z", "id": str(uuid.uuid4())},
        id="version-value",
    ),
    pytest.param([], id="root-list"),
    pytest.param(None, id="root-null"),
    pytest.param(
        {"v": 1, "created_at": "2026-08-20T12:00:00.000000Z", "id": str(uuid.uuid4()), "extra": 1},
        id="extra-field",
    ),
    pytest.param({"v": 1, "created_at": "2026-08-20T12:00:00.000000Z"}, id="missing-field"),
    pytest.param(
        {"v": 1, "created_at": "2026-08-20T12:00:00.000000Z", "id": "not-a-uuid"}, id="invalid-uuid"
    ),
    pytest.param(
        {"v": 1, "created_at": "not-a-timeZ", "id": str(uuid.uuid4())}, id="invalid-timestamp"
    ),
]


@pytest.mark.parametrize("payload", INVALID_CURSOR_PAYLOADS)
def test_decode_cursor_rejects_malformed_typed_fields(payload: object) -> None:
    with pytest.raises(DomainError) as caught:
        decode_cursor(encoded_cursor(payload))
    assert caught.value.status_code == 422
    assert caught.value.code == "INVALID_CURSOR"


@pytest.fixture(autouse=True)
async def conversation_cleanup(email_cleanup: list[str]):
    yield
    if email_cleanup:
        async with fresh_connection() as connection:
            await connection.execute(
                text(
                    "DELETE FROM messages WHERE sender_user_id IN "
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


def register(client: TestClient, cleanup: list[str], name: str) -> str:
    email = unique_email("chat")
    cleanup.append(email)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": name},
    )
    assert response.status_code == 201, response.text
    return email


def login(client: TestClient, email: str) -> None:
    assert (
        client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).status_code
        == 200
    )


async def workspace(
    client: TestClient, cleanup: list[str], status: str = "confirmed"
) -> tuple[str, str, str]:
    creator_email = register(client, cleanup, "Kreator Chat")
    profile = client.put(
        "/api/v1/profiles/me/creator",
        json={
            "display_name": "Studio Chat",
            "city": "Bandung",
            "bio": "Percakapan.",
            "specialty": "wedding",
            "starting_price_idr": 1_000_000,
        },
    ).json()["data"]
    async with fresh_connection() as connection:
        await connection.execute(
            text("UPDATE creator_profiles SET status='approved' WHERE id=:id"),
            {"id": profile["id"]},
        )
    client.post("/api/v1/auth/logout")
    client_email = register(client, cleanup, "Klien Chat")
    booking = client.post(
        "/api/v1/bookings",
        json={
            "creator_id": profile["id"],
            "event_date": (datetime.now(UTC).date() + timedelta(days=120)).isoformat(),
            "event_city": "Bandung",
        },
    ).json()["data"]
    async with fresh_connection() as connection:
        await connection.execute(
            text("UPDATE bookings SET status=:status WHERE id=:id"),
            {"status": status, "id": booking["id"]},
        )
    return booking["id"], client_email, creator_email


def test_conversation_routes_require_authentication() -> None:
    with TestClient(create_app()) as client:
        booking = client.get(f"/api/v1/bookings/{uuid.uuid4()}/conversation")
        unread = client.get("/api/v1/conversations/unread")
        messages = client.get(f"/api/v1/conversations/{uuid.uuid4()}/messages")
        create = client.post(
            f"/api/v1/conversations/{uuid.uuid4()}/messages",
            json={
                "client_message_id": str(uuid.uuid4()),
                "message_type": "text",
                "body": "Halo",
            },
        )
        read = client.post(f"/api/v1/conversations/{uuid.uuid4()}/read")

    assert [
        booking.status_code,
        unread.status_code,
        messages.status_code,
        create.status_code,
        read.status_code,
    ] == [401, 401, 401, 401, 401]


@pytest.mark.parametrize(
    ("booking_status", "created"),
    [("requested", False), ("cancelled", False), ("confirmed", True), ("completed", False)],
)
async def test_lazy_creation_obeys_booking_lifecycle(
    email_cleanup: list[str], booking_status: str, created: bool
) -> None:
    with TestClient(create_app()) as client:
        booking_id, _, _ = await workspace(client, email_cleanup, booking_status)
        response = client.get(f"/api/v1/bookings/{booking_id}/conversation")
    assert response.status_code == 200
    assert (response.json()["data"] is not None) is created


async def test_concurrent_gets_create_one_conversation(email_cleanup: list[str]) -> None:
    with TestClient(create_app()) as client:
        booking_id, _, _ = await workspace(client, email_cleanup)
        responses = await asyncio.gather(
            asyncio.to_thread(client.get, f"/api/v1/bookings/{booking_id}/conversation"),
            asyncio.to_thread(client.get, f"/api/v1/bookings/{booking_id}/conversation"),
        )
    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json()["data"]["id"] == responses[1].json()["data"]["id"]
    async with fresh_connection() as connection:
        count = await connection.scalar(
            text("SELECT count(*) FROM conversations WHERE booking_id=:id"), {"id": booking_id}
        )
    assert count == 1


async def test_message_idempotency_pagination_read_and_unread(email_cleanup: list[str]) -> None:
    with TestClient(create_app()) as client:
        booking_id, _, creator_email = await workspace(client, email_cleanup)
        conversation = client.get(f"/api/v1/bookings/{booking_id}/conversation").json()["data"]
        client_message_id = str(uuid.uuid4())
        payload = {
            "client_message_id": client_message_id,
            "message_type": "text",
            "body": "  Ｈａｌｏ  ",
        }
        first = client.post(f"/api/v1/conversations/{conversation['id']}/messages", json=payload)
        replay = client.post(f"/api/v1/conversations/{conversation['id']}/messages", json=payload)
        conflict = client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={**payload, "body": "Berbeda"},
        )
        second = client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={
                "client_message_id": str(uuid.uuid4()),
                "message_type": "text",
                "body": "Kedua",
            },
        )
        async with fresh_connection() as connection:
            await connection.execute(
                text("UPDATE messages SET created_at=:at WHERE id = ANY(:ids)"),
                {
                    "at": datetime(2026, 8, 20, 12, tzinfo=UTC),
                    "ids": [first.json()["data"]["id"], second.json()["data"]["id"]],
                },
            )
        assert first.json()["data"]["body"] == "Halo"
        client.post("/api/v1/auth/logout")
        login(client, creator_email)
        unread = client.get("/api/v1/conversations/unread")
        page_one = client.get(
            f"/api/v1/conversations/{conversation['id']}/messages", params={"limit": 1}
        )
        cursor = page_one.json()["data"]["next_cursor"]
        page_two = client.get(
            f"/api/v1/conversations/{conversation['id']}/messages",
            params={"limit": 1, "cursor": cursor},
        )
        invalid = client.get(
            f"/api/v1/conversations/{conversation['id']}/messages", params={"cursor": cursor + "x"}
        )
        read = client.post(f"/api/v1/conversations/{conversation['id']}/read")
        repeated = client.post(f"/api/v1/conversations/{conversation['id']}/read")

    assert first.status_code == replay.status_code == second.status_code == 201
    assert first.json()["data"]["id"] == replay.json()["data"]["id"]
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert unread.json()["data"] == [{"booking_id": booking_id, "count": 2}]
    ids = [page_one.json()["data"]["items"][0]["id"], page_two.json()["data"]["items"][0]["id"]]
    assert set(ids) == {first.json()["data"]["id"], second.json()["data"]["id"]}
    assert ids == sorted(ids, key=uuid.UUID)
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_CURSOR"
    assert read.json()["data"]["count"] == 2
    assert repeated.json()["data"]["count"] == 0


@pytest.mark.parametrize("requested_body", ["Pemenang", "Berbeda"])
async def test_message_insert_unique_collision_recovers_winning_row(
    email_cleanup: list[str], monkeypatch: pytest.MonkeyPatch, requested_body: str
) -> None:
    with TestClient(create_app()) as client:
        booking_id, client_email, _ = await workspace(client, email_cleanup)
        conversation_id = uuid.UUID(
            client.get(f"/api/v1/bookings/{booking_id}/conversation").json()["data"]["id"]
        )
    client_message_id = uuid.uuid4()
    winner_id = uuid.uuid4()
    engine = create_async_engine(upload_service.get_settings().database_url, poolclass=None)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as seed:
            user = await seed.scalar(select(User).where(User.email == client_email))
            assert user is not None
            user_id = user.id
            seed.add(
                Message(
                    id=winner_id,
                    conversation_id=conversation_id,
                    sender_user_id=user_id,
                    client_message_id=client_message_id,
                    message_type="text",
                    body="Pemenang",
                )
            )
            await seed.commit()

        async with factory() as session:
            user = await session.scalar(select(User).where(User.id == user_id))
            assert user is not None
            original_scalar = session.scalar
            skipped_precheck = False

            async def scalar_once_none(statement: object, *args: object, **kwargs: object):
                nonlocal skipped_precheck
                if not skipped_precheck and "messages.client_message_id" in str(statement):
                    skipped_precheck = True
                    return None
                return await original_scalar(statement, *args, **kwargs)

            monkeypatch.setattr(session, "scalar", scalar_once_none)
            if requested_body == "Pemenang":
                result, created = await conversation_service.create_message(
                    session,
                    conversation_id=conversation_id,
                    user=user,
                    client_message_id=client_message_id,
                    message_type="text",
                    body=requested_body,
                    upload_id=None,
                )
            else:
                with pytest.raises(DomainError) as caught:
                    await conversation_service.create_message(
                        session,
                        conversation_id=conversation_id,
                        user=user,
                        client_message_id=client_message_id,
                        message_type="text",
                        body=requested_body,
                        upload_id=None,
                    )
    finally:
        await engine.dispose()
    assert skipped_precheck
    if requested_body == "Pemenang":
        assert not created
        assert result.id == winner_id
    else:
        assert caught.value.code == "IDEMPOTENCY_CONFLICT"


async def test_concurrent_same_and_conflicting_client_message_ids_are_deterministic(
    email_cleanup: list[str],
) -> None:
    with TestClient(create_app()) as client:
        booking_id, _, _ = await workspace(client, email_cleanup)
        conversation_id = client.get(f"/api/v1/bookings/{booking_id}/conversation").json()["data"][
            "id"
        ]
        same_payload = {
            "client_message_id": str(uuid.uuid4()),
            "message_type": "text",
            "body": "Sama",
        }
        same = await asyncio.gather(
            *(
                asyncio.to_thread(
                    client.post,
                    f"/api/v1/conversations/{conversation_id}/messages",
                    json=same_payload,
                )
                for _ in range(2)
            )
        )
        conflict_id = str(uuid.uuid4())
        conflicting = await asyncio.gather(
            asyncio.to_thread(
                client.post,
                f"/api/v1/conversations/{conversation_id}/messages",
                json={**same_payload, "client_message_id": conflict_id, "body": "Satu"},
            ),
            asyncio.to_thread(
                client.post,
                f"/api/v1/conversations/{conversation_id}/messages",
                json={**same_payload, "client_message_id": conflict_id, "body": "Dua"},
            ),
        )
    assert [response.status_code for response in same] == [201, 201]
    assert same[0].json()["data"]["id"] == same[1].json()["data"]["id"]
    assert sorted(response.status_code for response in conflicting) == [201, 409]
    rejected = next(response for response in conflicting if response.status_code == 409)
    assert rejected.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


async def test_messages_api_sanitizes_every_malformed_typed_cursor(
    email_cleanup: list[str],
) -> None:
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        booking_id, _, _ = await workspace(client, email_cleanup)
        conversation_id = client.get(f"/api/v1/bookings/{booking_id}/conversation").json()["data"][
            "id"
        ]
        for parameter in INVALID_CURSOR_PAYLOADS:
            payload = parameter.values[0]
            raw_cursor = encoded_cursor(payload)
            response = client.get(
                f"/api/v1/conversations/{conversation_id}/messages",
                params={"cursor": raw_cursor},
            )
            assert response.status_code == 422, parameter.id
            assert response.json()["error"]["code"] == "INVALID_CURSOR", parameter.id
            assert raw_cursor not in response.text


async def test_text_rejects_postgresql_unsafe_nul_and_unpaired_surrogates(
    email_cleanup: list[str],
) -> None:
    unsafe_bodies = [b"unsafe\\u0000body", b"unsafe\\ud800body", b"unsafe\\udc00body"]
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        booking_id, _, _ = await workspace(client, email_cleanup)
        conversation_id = client.get(f"/api/v1/bookings/{booking_id}/conversation").json()["data"][
            "id"
        ]
        responses = []
        for body in unsafe_bodies:
            raw = (
                b'{"client_message_id":"'
                + str(uuid.uuid4()).encode()
                + b'","message_type":"text","body":"'
                + body
                + b'"}'
            )
            response = client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                content=raw,
                headers={"content-type": "application/json"},
            )
            responses.append((response, raw))
    for response, raw in responses:
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "MESSAGE_VALIDATION_FAILED"
        assert raw.decode() not in response.text
    async with fresh_connection() as connection:
        count = await connection.scalar(
            text("SELECT count(*) FROM messages WHERE conversation_id=:id"),
            {"id": conversation_id},
        )
    assert count == 0


async def test_terminal_existing_conversation_is_read_only(email_cleanup: list[str]) -> None:
    with TestClient(create_app()) as client:
        booking_id, _, _ = await workspace(client, email_cleanup)
        conversation_id = client.get(f"/api/v1/bookings/{booking_id}/conversation").json()["data"][
            "id"
        ]
        async with fresh_connection() as connection:
            await connection.execute(
                text("UPDATE bookings SET status='completed' WHERE id=:id"), {"id": booking_id}
            )
        readable = client.get(f"/api/v1/conversations/{conversation_id}/messages")
        blocked = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={
                "client_message_id": str(uuid.uuid4()),
                "message_type": "text",
                "body": "Tidak boleh",
            },
        )
    assert readable.status_code == 200
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "CONVERSATION_READ_ONLY"


async def test_message_write_serializes_with_booking_terminal_transition(
    email_cleanup: list[str],
) -> None:
    with TestClient(create_app()) as client:
        booking_id, client_email, _ = await workspace(client, email_cleanup)
        conversation_id = uuid.UUID(
            client.get(f"/api/v1/bookings/{booking_id}/conversation").json()["data"]["id"]
        )
    engine = create_async_engine(upload_service.get_settings().database_url, poolclass=None)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    worker_started = asyncio.Event()
    worker_pid: int | None = None

    async def write_message() -> str:
        nonlocal worker_pid
        async with factory() as session:
            user = await session.scalar(select(User).where(User.email == client_email))
            assert user is not None
            worker_pid = await session.scalar(text("SELECT pg_backend_pid()"))
            assert worker_pid is not None
            worker_started.set()
            try:
                await conversation_service.create_message(
                    session,
                    conversation_id=conversation_id,
                    user=user,
                    client_message_id=uuid.uuid4(),
                    message_type="text",
                    body="Tidak boleh melewati transisi",
                    upload_id=None,
                )
            except DomainError as error:
                return error.code
            return "created"

    try:
        async with factory() as transition:
            booking = await transition.scalar(
                text("SELECT id FROM bookings WHERE id=:id FOR UPDATE"), {"id": booking_id}
            )
            assert booking is not None
            pending = asyncio.create_task(write_message())
            await asyncio.wait_for(worker_started.wait(), timeout=5)
            blockers: list[int] = []
            for _ in range(100):
                async with factory() as monitor:
                    blockers = list(
                        await monitor.scalar(
                            text("SELECT pg_blocking_pids(:pid)"), {"pid": worker_pid}
                        )
                        or []
                    )
                if blockers:
                    break
                await asyncio.sleep(0.02)
            assert blockers
            assert not pending.done()
            await transition.execute(
                text("UPDATE bookings SET status='completed' WHERE id=:id"), {"id": booking_id}
            )
            await transition.commit()
        result = await asyncio.wait_for(pending, timeout=10)
    finally:
        await engine.dispose()
    assert result == "CONVERSATION_READ_ONLY"


async def test_attachment_consumes_owned_completed_chat_upload_once_without_key_leak(
    email_cleanup: list[str],
) -> None:
    with TestClient(create_app()) as client:
        booking_id, client_email, _ = await workspace(client, email_cleanup)
        conversation_id = client.get(f"/api/v1/bookings/{booking_id}/conversation").json()["data"][
            "id"
        ]
        upload_id = uuid.uuid4()
        wrong_purpose_id = uuid.uuid4()
        wrong_owner_id = uuid.uuid4()
        cross_booking_id = uuid.uuid4()
        other_booking_id = uuid.uuid4()
        async with fresh_connection() as connection:
            user_id = await connection.scalar(
                text("SELECT id FROM users WHERE email=:email"), {"email": client_email}
            )
            creator_user_id = await connection.scalar(
                text(
                    "SELECT creator_profiles.user_id FROM bookings "
                    "JOIN creator_profiles ON creator_profiles.id=bookings.creator_profile_id "
                    "WHERE bookings.id=:id"
                ),
                {"id": booking_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO bookings "
                    "(id, client_id, creator_profile_id, event_date, event_city, notes, status, "
                    "quoted_price_idr) SELECT :new_id, client_id, creator_profile_id, "
                    "event_date + 1, event_city, notes, 'confirmed', quoted_price_idr "
                    "FROM bookings WHERE id=:id"
                ),
                {"new_id": other_booking_id, "id": booking_id},
            )
            for identifier, upload_booking, requester, purpose in (
                (upload_id, booking_id, user_id, "chat_attachment"),
                (wrong_purpose_id, booking_id, user_id, "deliverable"),
                (wrong_owner_id, booking_id, creator_user_id, "chat_attachment"),
                (cross_booking_id, other_booking_id, user_id, "chat_attachment"),
            ):
                await connection.execute(
                    text(
                        "INSERT INTO upload_intents "
                        "(id, booking_id, requested_by_user_id, purpose, object_key, filename, "
                        "content_type, size_bytes, status, expires_at, completed_at) VALUES "
                        "(:id, :booking, :user, :purpose, :key, 'brief.pdf', "
                        "'application/pdf', 42, 'completed', now() + interval '10 minutes', now())"
                    ),
                    {
                        "id": identifier,
                        "booking": upload_booking,
                        "user": requester,
                        "purpose": purpose,
                        "key": f"private/secret/{identifier}",
                    },
                )
        client_message_id = str(uuid.uuid4())
        payload = {
            "client_message_id": client_message_id,
            "message_type": "attachment",
            "body": None,
            "upload_id": str(upload_id),
        }
        created = client.post(f"/api/v1/conversations/{conversation_id}/messages", json=payload)
        replay = client.post(f"/api/v1/conversations/{conversation_id}/messages", json=payload)
        consumed = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={**payload, "client_message_id": str(uuid.uuid4())},
        )
        wrong_purpose = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={
                **payload,
                "client_message_id": str(uuid.uuid4()),
                "upload_id": str(wrong_purpose_id),
            },
        )
        wrong_owner = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={
                **payload,
                "client_message_id": str(uuid.uuid4()),
                "upload_id": str(wrong_owner_id),
            },
        )
        cross_booking = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={
                **payload,
                "client_message_id": str(uuid.uuid4()),
                "upload_id": str(cross_booking_id),
            },
        )
    assert created.status_code == replay.status_code == 201
    assert created.json()["data"]["id"] == replay.json()["data"]["id"]
    assert created.json()["data"]["attachment"] == {
        "id": str(upload_id),
        "filename": "brief.pdf",
        "content_type": "application/pdf",
        "size_bytes": 42,
    }
    assert "object_key" not in created.text
    assert "private/secret" not in created.text
    assert consumed.status_code == 409
    assert wrong_purpose.status_code == wrong_owner.status_code == cross_booking.status_code == 404
    assert all(
        response.json()["error"]["code"] == "UPLOAD_NOT_FOUND"
        for response in (wrong_purpose, wrong_owner, cross_booking)
    )


async def test_outsider_unknown_and_admin_are_indistinguishable(email_cleanup: list[str]) -> None:
    with TestClient(create_app()) as client:
        booking_id, _, _ = await workspace(client, email_cleanup)
        conversation_id = client.get(f"/api/v1/bookings/{booking_id}/conversation").json()["data"][
            "id"
        ]
        client.post("/api/v1/auth/logout")
        outsider = register(client, email_cleanup, "Orang Luar")
        denied = client.get(f"/api/v1/conversations/{conversation_id}/messages")
        unknown = client.get(f"/api/v1/conversations/{uuid.uuid4()}/messages")
        await make_admin(outsider)
        admin = client.get(f"/api/v1/conversations/{conversation_id}/messages")
        unread = client.get("/api/v1/conversations/unread")
    assert [denied.status_code, unknown.status_code, admin.status_code, unread.status_code] == [
        404,
        404,
        404,
        404,
    ]


async def test_message_write_rate_limit_is_per_user_and_conversation(
    email_cleanup: list[str],
) -> None:
    with TestClient(create_app()) as client:
        booking_id, _, _ = await workspace(client, email_cleanup)
        conversation_id = client.get(f"/api/v1/bookings/{booking_id}/conversation").json()["data"][
            "id"
        ]
        responses = [
            client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "client_message_id": str(uuid.uuid4()),
                    "message_type": "text",
                    "body": f"Pesan {index}",
                },
            )
            for index in range(31)
        ]
    assert all(response.status_code == 201 for response in responses[:30])
    assert responses[30].status_code == 429
    assert responses[30].json() == {
        "error": {"code": "RATE_LIMITED", "message": "Terlalu banyak permintaan.", "details": {}}
    }
    async with fresh_connection() as connection:
        count = await connection.scalar(
            text("SELECT count(*) FROM messages WHERE conversation_id=:id"),
            {"id": conversation_id},
        )
    assert count == 30


async def test_message_rate_limiter_admits_only_after_resource_authorization(
    email_cleanup: list[str],
) -> None:
    app = create_app()
    with TestClient(app) as client:
        booking_id, client_email, _ = await workspace(client, email_cleanup)
        conversation_id = client.get(f"/api/v1/bookings/{booking_id}/conversation").json()["data"][
            "id"
        ]

        def repeated(target: str) -> list[int]:
            return [
                client.post(
                    f"/api/v1/conversations/{target}/messages",
                    json={
                        "client_message_id": str(uuid.uuid4()),
                        "message_type": "text",
                        "body": "Tidak berwenang",
                    },
                ).status_code
                for _ in range(35)
            ]

        unknown_statuses = repeated(str(uuid.uuid4()))
        await make_admin(client_email)
        admin_participant_statuses = repeated(conversation_id)
        client.post("/api/v1/auth/logout")
        register(client, email_cleanup, "Outsider Limiter")
        outsider_statuses = repeated(conversation_id)

    assert unknown_statuses == [404] * 35
    assert admin_participant_statuses == [404] * 35
    assert outsider_statuses == [404] * 35
    assert app.state.message_rate_limiter._entries == {}


class UploadStorage:
    async def create_upload_url(
        self, *, object_key: str, content_type: str, expires_seconds: int
    ) -> str:
        return "https://storage.test/upload"

    async def inspect_object(self, *, object_key: str):
        raise AssertionError("not used")

    async def create_download_url(self, *, object_key: str, expires_seconds: int) -> str:
        raise AssertionError("not used")

    async def delete_object(self, *, object_key: str) -> None:
        raise AssertionError("not used")


async def test_upload_intent_rate_limit_is_app_scoped_and_does_not_mutate_on_rejection(
    email_cleanup: list[str],
) -> None:
    storage = UploadStorage()
    first_app = create_app()
    first_app.dependency_overrides[upload_service.get_storage_adapter] = lambda: storage
    with TestClient(first_app) as client:
        booking_id, client_email, _ = await workspace(client, email_cleanup)
        payload = {
            "purpose": "chat_attachment",
            "filename": "brief.pdf",
            "content_type": "application/pdf",
            "size_bytes": 10,
        }
        responses = [
            client.post(f"/api/v1/bookings/{booking_id}/uploads", json=payload) for _ in range(11)
        ]
    assert all(response.status_code == 201 for response in responses[:10])
    assert responses[10].status_code == 429
    assert "booking_id" not in responses[10].text
    async with fresh_connection() as connection:
        count = await connection.scalar(
            text("SELECT count(*) FROM upload_intents WHERE booking_id=:id"), {"id": booking_id}
        )
    assert count == 10

    second_app = create_app()
    second_app.dependency_overrides[upload_service.get_storage_adapter] = lambda: storage
    with TestClient(second_app) as second_client:
        login(second_client, client_email)
        isolated = second_client.post(f"/api/v1/bookings/{booking_id}/uploads", json=payload)
    assert isolated.status_code == 201


async def test_upload_rate_limiter_admits_only_after_resource_authorization(
    email_cleanup: list[str],
) -> None:
    app = create_app()
    app.dependency_overrides[upload_service.get_storage_adapter] = lambda: UploadStorage()
    payload = {
        "purpose": "chat_attachment",
        "filename": "brief.pdf",
        "content_type": "application/pdf",
        "size_bytes": 10,
    }
    with TestClient(app) as client:
        booking_id, client_email, _ = await workspace(client, email_cleanup)

        def repeated(target: str) -> list[int]:
            return [
                client.post(f"/api/v1/bookings/{target}/uploads", json=payload).status_code
                for _ in range(15)
            ]

        unknown_statuses = repeated(str(uuid.uuid4()))
        await make_admin(client_email)
        admin_participant_statuses = repeated(booking_id)
        client.post("/api/v1/auth/logout")
        register(client, email_cleanup, "Outsider Upload Limiter")
        outsider_statuses = repeated(booking_id)

    assert unknown_statuses == [404] * 15
    assert admin_participant_statuses == [404] * 15
    assert outsider_statuses == [404] * 15
    assert app.state.upload_rate_limiter._entries == {}
