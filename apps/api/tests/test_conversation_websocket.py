import asyncio
import logging
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect

from app.api import conversations as conversation_api
from app.api.conversations import conversation_websocket
from app.core.security import hash_session_token
from app.main import create_app
from app.realtime import ConnectionHub, get_connection_hub
from tests.conftest import fresh_connection, make_admin, unique_email

pytestmark = pytest.mark.integration
PASSWORD = "sandi-aman-123"
ORIGIN = "http://localhost:8080"


@pytest.fixture(autouse=True)
async def websocket_cleanup(email_cleanup: list[str]):
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


def register(client: TestClient, cleanup: list[str], name: str) -> str:
    email = unique_email("ws")
    cleanup.append(email)
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD, "full_name": name},
    )
    assert response.status_code == 201, response.text
    return email


def use_session(client: TestClient, token: str) -> None:
    client.cookies.clear()
    client.cookies.set("jepret_session", token, domain="testserver.local", path="/")


def websocket_headers(token: str, origin: str = ORIGIN) -> dict[str, str]:
    return {"origin": origin, "cookie": f"jepret_session={token}"}


def bounded_call(function: Callable[[], Any]) -> Any:
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(function)
    try:
        return future.result(timeout=2)
    except FutureTimeoutError:
        pytest.fail("Timed out waiting for WebSocket frame")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def receive_json(socket: Any) -> Any:
    return bounded_call(socket.receive_json)


def denied_disconnect(client: TestClient, url: str, headers: dict[str, str]) -> WebSocketDisconnect:
    with (
        client.websocket_connect(url, headers=headers) as socket,
        pytest.raises(WebSocketDisconnect) as caught,
    ):
        receive_json(socket)
    return caught.value


async def create_workspace(client: TestClient, cleanup: list[str]) -> tuple[str, str, str]:
    register(client, cleanup, "Kreator Realtime")
    creator_token = client.cookies["jepret_session"]
    profile = client.put(
        "/api/v1/profiles/me/creator",
        json={
            "display_name": "Studio Realtime",
            "city": "Bandung",
            "bio": "Uji realtime.",
            "specialty": "wedding",
            "starting_price_idr": 1_000_000,
        },
    ).json()["data"]
    async with fresh_connection() as connection:
        await connection.execute(
            text("UPDATE creator_profiles SET status='approved' WHERE id=:id"),
            {"id": profile["id"]},
        )

    register(client, cleanup, "Klien Realtime")
    client_token = client.cookies["jepret_session"]
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
            text("UPDATE bookings SET status='confirmed' WHERE id=:id"),
            {"id": booking["id"]},
        )
    conversation = client.get(f"/api/v1/bookings/{booking['id']}/conversation")
    assert conversation.status_code == 200, conversation.text
    return conversation.json()["data"]["id"], client_token, creator_token


async def test_participant_can_connect_and_ping(email_cleanup: list[str]) -> None:
    app = create_app()
    with TestClient(app) as client:
        conversation_id, client_token, creator_token = await create_workspace(client, email_cleanup)
        for booking_status in ("confirmed", "in_progress", "delivered", "completed", "cancelled"):
            async with fresh_connection() as connection:
                await connection.execute(
                    text(
                        "UPDATE bookings SET status=:status WHERE id=("
                        "SELECT booking_id FROM conversations WHERE id=:id)"
                    ),
                    {"status": booking_status, "id": conversation_id},
                )
            for token in (client_token, creator_token):
                with client.websocket_connect(
                    f"/ws/conversations/{conversation_id}",
                    headers=websocket_headers(token, ORIGIN + "/"),
                ) as socket:
                    socket.send_json({"type": "ping"})
                    assert receive_json(socket) == {"type": "pong"}
        assert client.portal is not None
        assert (
            client.portal.call(get_connection_hub(app).connection_count, uuid.UUID(conversation_id))
            == 0
        )


async def test_committed_message_and_read_broadcast_exact_public_payload(
    email_cleanup: list[str],
) -> None:
    app = create_app()
    with TestClient(app) as client:
        conversation_id, client_token, creator_token = await create_workspace(client, email_cleanup)
        with (
            client.websocket_connect(
                f"/ws/conversations/{conversation_id}",
                headers=websocket_headers(creator_token),
            ) as creator_socket,
            client.websocket_connect(
                f"/ws/conversations/{conversation_id}",
                headers=websocket_headers(client_token),
            ) as client_socket,
        ):
            use_session(client, client_token)
            sent = client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "client_message_id": str(uuid.uuid4()),
                    "message_type": "text",
                    "body": "Siap",
                },
            )
            assert sent.status_code == 201, sent.text
            message_event = {"type": "message.created", "data": sent.json()["data"]}
            assert receive_json(creator_socket) == message_event
            assert receive_json(client_socket) == message_event

            use_session(client, creator_token)
            receipt = client.post(f"/api/v1/conversations/{conversation_id}/read")
            assert receipt.status_code == 200, receipt.text
            read_event = {"type": "message.read", "data": receipt.json()["data"]}
            assert receive_json(creator_socket) == read_event
            assert receive_json(client_socket) == read_event


async def test_websocket_rejects_non_exact_origin(
    email_cleanup: list[str],
) -> None:
    app = create_app()
    with TestClient(app) as client:
        conversation_id, _, creator_token = await create_workspace(client, email_cleanup)
        use_session(client, creator_token)
        invalid_origins = (
            None,
            "null",
            "https://localhost:8080",
            "http://localhost:8080.evil.test",
            "http://evil.test/http://localhost:8080",
            "http://localhost:8080/path",
            "http://localhost:8080?next=evil",
            "http://user@localhost:8080",
        )
        for origin in invalid_origins:
            headers = {"cookie": f"jepret_session={creator_token}"}
            if origin is not None:
                headers["origin"] = origin
            caught = denied_disconnect(client, f"/ws/conversations/{conversation_id}", headers)
            assert caught.code == 4403


async def test_websocket_rejects_missing_invalid_and_revoked_session(
    email_cleanup: list[str],
) -> None:
    with TestClient(create_app()) as client:
        register(client, email_cleanup, "Sesi Dicabut")
        revoked_token = client.cookies["jepret_session"]
        assert client.post("/api/v1/auth/logout").status_code == 200
        for token in (None, "invalid-token", revoked_token):
            client.cookies.clear()
            if token is not None:
                use_session(client, token)
            headers = {"origin": ORIGIN}
            if token is not None:
                headers["cookie"] = f"jepret_session={token}"
            caught = denied_disconnect(client, f"/ws/conversations/{uuid.uuid4()}", headers)
            assert caught.code == 4401


async def test_websocket_hides_unknown_outsider_and_admin_denials(
    email_cleanup: list[str],
) -> None:
    app = create_app()
    with TestClient(app) as client:
        conversation_id, _, creator_token = await create_workspace(client, email_cleanup)
        outsider_email = register(client, email_cleanup, "Orang Luar")
        outsider_token = client.cookies["jepret_session"]

        for target, token in (
            (conversation_id, outsider_token),
            (str(uuid.uuid4()), creator_token),
        ):
            use_session(client, token)
            caught = denied_disconnect(
                client,
                f"/ws/conversations/{target}",
                websocket_headers(token),
            )
            assert caught.code == 4403
            assert caught.reason == ""

        await make_admin(outsider_email)
        use_session(client, outsider_token)
        caught = denied_disconnect(
            client,
            f"/ws/conversations/{conversation_id}",
            websocket_headers(outsider_token),
        )
        assert caught.code == 4403

        async with fresh_connection() as connection:
            await connection.execute(
                text(
                    "UPDATE users SET is_admin=true WHERE id=("
                    "SELECT user_id FROM sessions WHERE token_hash=:token_hash)"
                ),
                {"token_hash": hash_session_token(creator_token)},
            )
        participant_admin = denied_disconnect(
            client,
            f"/ws/conversations/{conversation_id}",
            websocket_headers(creator_token),
        )
        assert participant_admin.code == 4403


async def test_websocket_rejects_every_non_ping_frame(
    email_cleanup: list[str],
) -> None:
    app = create_app()
    with TestClient(app) as client:
        conversation_id, _, creator_token = await create_workspace(client, email_cleanup)
        use_session(client, creator_token)
        frames: list[tuple[str, object]] = [
            ("json", {"type": "message"}),
            ("json", {"type": "ping", "data": {}}),
            ("json", ["ping"]),
            ("json", "ping"),
            ("json", 1),
            ("json", None),
            ("text", "not-json"),
            ("text", "{"),
            ("bytes", b"ping"),
        ]
        for send, value in frames:
            with client.websocket_connect(
                f"/ws/conversations/{conversation_id}",
                headers=websocket_headers(creator_token),
            ) as socket:
                getattr(socket, f"send_{send}")(value)
                with pytest.raises(WebSocketDisconnect) as caught:
                    receive_json(socket)
                assert caught.value.code == 1003


async def test_terminal_conversation_remains_connected_but_write_emits_nothing(
    email_cleanup: list[str],
) -> None:
    app = create_app()
    with TestClient(app) as client:
        conversation_id, client_token, creator_token = await create_workspace(client, email_cleanup)
        async with fresh_connection() as connection:
            await connection.execute(
                text(
                    "UPDATE bookings SET status='completed' WHERE id=("
                    "SELECT booking_id FROM conversations WHERE id=:id)"
                ),
                {"id": conversation_id},
            )
        use_session(client, creator_token)
        with client.websocket_connect(
            f"/ws/conversations/{conversation_id}", headers=websocket_headers(creator_token)
        ) as socket:
            use_session(client, client_token)
            denied = client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "client_message_id": str(uuid.uuid4()),
                    "message_type": "text",
                    "body": "Terlambat",
                },
            )
            assert denied.status_code == 409
            socket.send_json({"type": "ping"})
            assert receive_json(socket) == {"type": "pong"}


async def test_existing_conversation_receives_booking_update(
    email_cleanup: list[str],
) -> None:
    app = create_app()
    with TestClient(app) as client:
        conversation_id, _client_token, creator_token = await create_workspace(
            client, email_cleanup
        )
        use_session(client, creator_token)
        with client.websocket_connect(
            f"/ws/conversations/{conversation_id}", headers=websocket_headers(creator_token)
        ) as socket:
            async with fresh_connection() as connection:
                resolved = await connection.scalar(
                    text("SELECT booking_id FROM conversations WHERE id=:id"),
                    {"id": conversation_id},
                )
                await connection.execute(
                    text("UPDATE bookings SET status='requested' WHERE id=:id"),
                    {"id": resolved},
                )
            use_session(client, creator_token)
            updated = client.post(f"/api/v1/bookings/{resolved}/accept")
            assert updated.status_code == 200, updated.text
            assert receive_json(socket) == {
                "type": "booking.updated",
                "data": updated.json()["data"],
            }


class StubSocket:
    def __init__(self, *, fails: bool = False, expected_events: int = 1) -> None:
        self.fails = fails
        self.accept_count = 0
        self.events: list[dict[str, object]] = []
        self.expected_events = expected_events
        self.accepted = asyncio.Event()
        self.received = asyncio.Event()
        self.delivery_events = [asyncio.Event() for _ in range(expected_events)]
        self.send_attempted = asyncio.Event()
        self.closed = asyncio.Event()
        self.close_codes: list[int] = []

    async def accept(self) -> None:
        self.accept_count += 1
        self.accepted.set()

    async def send_json(self, event: dict[str, object]) -> None:
        self.send_attempted.set()
        if self.fails:
            raise RuntimeError("send failed")
        self.events.append(event)
        self.delivery_events[len(self.events) - 1].set()
        if len(self.events) >= self.expected_events:
            self.received.set()

    async def close(self, code: int = 1000) -> None:
        self.close_codes.append(code)
        self.closed.set()


class SlowSocket(StubSocket):
    def __init__(self) -> None:
        super().__init__()
        self.release = asyncio.Event()

    async def send_json(self, event: dict[str, object]) -> None:
        self.send_attempted.set()
        await self.release.wait()
        await super().send_json(event)


class BlockingCloseSocket(SlowSocket):
    def __init__(self, *, fails: bool = False) -> None:
        super().__init__()
        self.fails = fails
        self.close_started = asyncio.Event()
        self.release_close = asyncio.Event()

    async def send_json(self, event: dict[str, object]) -> None:
        self.send_attempted.set()
        if self.fails:
            raise RuntimeError("send failed")
        await super().send_json(event)

    async def close(self, code: int = 1000) -> None:
        self.close_started.set()
        await self.release_close.wait()
        await super().close(code)


class LockInspectingHub(ConnectionHub):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.cleanup_registered_under_lock = False

    def _schedule_termination(self, state: object, *, close_code: int) -> asyncio.Task[None]:
        self.cleanup_registered_under_lock = self._lock.locked()
        return super()._schedule_termination(  # type: ignore[arg-type]
            state, close_code=close_code
        )


class RouteSocket:
    def __init__(self, app: FastAPI, *, frame: dict[str, object]) -> None:
        self.app = app
        self.frame = frame
        self.accepted = asyncio.Event()
        self.allow_receive = asyncio.Event()
        self.frame_received = asyncio.Event()
        self.domain_send_started = asyncio.Event()
        self.release_domain_send = asyncio.Event()
        self.all_sent = asyncio.Event()
        self.closed = asyncio.Event()
        self.send_active = False
        self.close_after_writer_quiesced: bool | None = None
        self.sent: list[dict[str, object]] = []
        self._received_once = False

    async def accept(self) -> None:
        self.accepted.set()

    async def receive(self) -> dict[str, object]:
        if not self._received_once:
            await self.allow_receive.wait()
            self._received_once = True
            self.frame_received.set()
            return self.frame
        await self.all_sent.wait()
        return {"type": "websocket.disconnect"}

    async def send_json(self, event: dict[str, object]) -> None:
        if event["type"] == "domain.event":
            self.send_active = True
            self.domain_send_started.set()
            try:
                await self.release_domain_send.wait()
            finally:
                self.send_active = False
        self.sent.append(event)
        if len(self.sent) >= 2:
            self.all_sent.set()

    async def close(self, code: int = 1000) -> None:
        self.close_after_writer_quiesced = not self.send_active
        self.sent.append({"type": "close", "code": code})
        self.all_sent.set()
        self.closed.set()


class OwnershipRouteSocket(RouteSocket):
    def __init__(
        self,
        app: FastAPI,
        *,
        frame: dict[str, object],
        fail_send: bool = False,
    ) -> None:
        super().__init__(app, frame=frame)
        self.fail_send = fail_send
        self.close_started = asyncio.Event()
        self.release_close = asyncio.Event()
        self.close_attempts: list[int] = []

    async def send_json(self, event: dict[str, object]) -> None:
        if self.fail_send:
            self.domain_send_started.set()
            raise RuntimeError("send failed")
        await super().send_json(event)

    async def close(self, code: int = 1000) -> None:
        self.close_attempts.append(code)
        self.close_started.set()
        await self.release_close.wait()
        await super().close(code)


class DeniedSocket:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.cookies: dict[str, str] = {}
        self.messages: list[tuple[str, int | None]] = []

    async def accept(self) -> None:
        self.messages.append(("accept", None))

    async def close(self, code: int = 1000) -> None:
        self.messages.append(("close", code))


class ExplodingHub(ConnectionHub):
    async def broadcast(self, conversation_id: uuid.UUID, event: dict[str, object]) -> None:
        raise RuntimeError("hub failed")


async def test_unexpected_hub_failure_never_changes_committed_rest_success(
    email_cleanup: list[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app()
    with TestClient(app) as client:
        conversation_id, client_token, _creator_token = await create_workspace(
            client, email_cleanup
        )
        app.state.connection_hub = ExplodingHub()
        use_session(client, client_token)
        with caplog.at_level(logging.WARNING, logger="app.realtime"):
            sent = client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "client_message_id": str(uuid.uuid4()),
                    "message_type": "text",
                    "body": "Tetap tersimpan",
                },
            )
    assert sent.status_code == 201, sent.text
    record = next(record for record in caplog.records if record.name == "app.realtime")
    assert record.exc_info is not None
    assert "Tetap tersimpan" not in record.getMessage()


async def test_denial_accepts_before_closing_with_exact_policy_code() -> None:
    socket = DeniedSocket()

    await conversation_websocket(socket, uuid.uuid4())  # type: ignore[arg-type]

    assert socket.messages == [("accept", None), ("close", 4403)]


async def test_connect_cancellation_after_accept_closes_without_registration() -> None:
    hub = ConnectionHub()
    conversation_id = uuid.uuid4()
    socket = StubSocket()

    async with hub._lock:
        connect_task = asyncio.create_task(
            hub.connect(conversation_id, socket)  # type: ignore[arg-type]
        )
        await asyncio.wait_for(socket.accepted.wait(), timeout=2)
        connect_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await connect_task
    assert socket.close_codes == [1011]
    assert await hub.connection_count(conversation_id) == 0
    assert await hub.writer_count() == 0
    await hub.close()


async def test_hub_broadcast_is_nonblocking_fifo_and_evicts_full_slow_socket() -> None:
    hub = ConnectionHub(queue_size=2, send_timeout_seconds=30)
    conversation_id = uuid.uuid4()
    fast = StubSocket(expected_events=4)
    slow = SlowSocket()
    await hub.connect(conversation_id, fast)  # type: ignore[arg-type]
    await hub.connect(conversation_id, slow)  # type: ignore[arg-type]
    assert fast.accept_count == slow.accept_count == 1

    events = [{"type": "event", "data": {"sequence": value}} for value in range(4)]
    await asyncio.wait_for(hub.broadcast(conversation_id, events[0]), timeout=2)
    await asyncio.wait_for(slow.send_attempted.wait(), timeout=2)
    await asyncio.wait_for(fast.delivery_events[0].wait(), timeout=2)
    for index, event in enumerate(events[1:], start=1):
        await asyncio.wait_for(hub.broadcast(conversation_id, event), timeout=2)
        await asyncio.wait_for(fast.delivery_events[index].wait(), timeout=2)

    await asyncio.wait_for(fast.received.wait(), timeout=2)
    await asyncio.wait_for(slow.closed.wait(), timeout=2)
    assert fast.events == events
    assert slow.close_codes == [1013]
    assert await hub.connection_count(conversation_id) == 1
    await hub.close()


async def test_hub_isolates_immediate_send_failure_and_concurrent_broadcasts() -> None:
    event_count = 10
    hub = ConnectionHub()
    conversation_id = uuid.uuid4()
    good = StubSocket(expected_events=event_count)
    failed = StubSocket(fails=True)
    await hub.connect(conversation_id, good)  # type: ignore[arg-type]
    await hub.connect(conversation_id, failed)  # type: ignore[arg-type]

    events = [{"type": "event", "data": {"sequence": value}} for value in range(event_count)]
    await asyncio.gather(*(hub.broadcast(conversation_id, event) for event in events))

    await asyncio.wait_for(good.received.wait(), timeout=2)
    await asyncio.wait_for(failed.closed.wait(), timeout=2)
    assert good.events == events
    assert failed.close_codes == [1011]
    assert await hub.connection_count(conversation_id) == 1
    await hub.close()


async def test_hub_send_timeout_removes_and_closes_socket() -> None:
    hub = ConnectionHub(send_timeout_seconds=0.01)
    conversation_id = uuid.uuid4()
    slow = SlowSocket()
    await hub.connect(conversation_id, slow)  # type: ignore[arg-type]

    await hub.broadcast(conversation_id, {"type": "event", "data": {}})

    await asyncio.wait_for(slow.send_attempted.wait(), timeout=2)
    await asyncio.wait_for(slow.closed.wait(), timeout=2)
    assert slow.close_codes == [1011]
    assert await hub.connection_count(conversation_id) == 0
    await hub.close()


async def test_queue_full_cleanup_is_owned_atomically_and_awaited_by_close() -> None:
    hub = LockInspectingHub(queue_size=1, send_timeout_seconds=30)
    conversation_id = uuid.uuid4()
    socket = BlockingCloseSocket()
    await hub.connect(conversation_id, socket)  # type: ignore[arg-type]
    await hub.broadcast(conversation_id, {"type": "event", "data": {"sequence": 0}})
    await asyncio.wait_for(socket.send_attempted.wait(), timeout=2)
    await hub.broadcast(conversation_id, {"type": "event", "data": {"sequence": 1}})
    await hub.broadcast(conversation_id, {"type": "event", "data": {"sequence": 2}})
    await asyncio.wait_for(socket.close_started.wait(), timeout=2)

    close_task = asyncio.create_task(hub.close())
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(close_task), timeout=1)
        assert hub.cleanup_registered_under_lock is True
    finally:
        socket.release_close.set()
        await close_task
    assert await hub.writer_count() == 0
    assert await hub.cleanup_count() == 0


async def test_writer_failure_close_remains_owned_during_concurrent_hub_close() -> None:
    hub = ConnectionHub(send_timeout_seconds=30)
    conversation_id = uuid.uuid4()
    socket = BlockingCloseSocket(fails=True)
    await hub.connect(conversation_id, socket)  # type: ignore[arg-type]
    await hub.broadcast(conversation_id, {"type": "event", "data": {}})
    await asyncio.wait_for(socket.close_started.wait(), timeout=2)

    close_task = asyncio.create_task(hub.close())
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(close_task), timeout=1)
    finally:
        socket.release_close.set()
        await close_task
    assert socket.close_codes == [1011]
    assert await hub.writer_count() == 0
    assert await hub.cleanup_count() == 0


async def test_cancelled_close_cannot_cancel_hub_owned_shutdown() -> None:
    hub = ConnectionHub(send_timeout_seconds=30)
    conversation_id = uuid.uuid4()
    socket = BlockingCloseSocket()
    await hub.connect(conversation_id, socket)  # type: ignore[arg-type]

    owner = asyncio.create_task(hub.close())
    await asyncio.wait_for(socket.close_started.wait(), timeout=2)
    owner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await owner

    second = asyncio.create_task(hub.close())
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(asyncio.shield(second), timeout=1)
    assert socket.close_codes == []

    socket.release_close.set()
    await asyncio.wait_for(second, timeout=2)
    assert socket.close_codes == [1001]
    assert await hub.writer_count() == 0
    assert await hub.cleanup_count() == 0


@pytest.mark.parametrize(
    ("failure_mode", "prior_code"),
    [("queue_full", 1013), ("writer_failure", 1011)],
)
async def test_prior_close_owner_wins_invalid_frame_race(
    monkeypatch: pytest.MonkeyPatch,
    failure_mode: str,
    prior_code: int,
) -> None:
    async def authorize(_: object, __: uuid.UUID) -> bool:
        return True

    monkeypatch.setattr(conversation_api, "_authorize_websocket", authorize)
    app = create_app()
    hub = ConnectionHub(queue_size=1, send_timeout_seconds=30)
    app.state.connection_hub = hub
    conversation_id = uuid.uuid4()
    socket = OwnershipRouteSocket(
        app,
        frame={"type": "websocket.receive", "text": "{}"},
        fail_send=failure_mode == "writer_failure",
    )
    route_task = asyncio.create_task(
        conversation_websocket(socket, conversation_id)  # type: ignore[arg-type]
    )
    await asyncio.wait_for(socket.accepted.wait(), timeout=2)
    await hub.broadcast(conversation_id, {"type": "domain.event", "data": {"sequence": 0}})
    await asyncio.wait_for(socket.domain_send_started.wait(), timeout=2)
    if failure_mode == "queue_full":
        await hub.broadcast(conversation_id, {"type": "domain.event", "data": {"sequence": 1}})
        await hub.broadcast(conversation_id, {"type": "domain.event", "data": {"sequence": 2}})
    await asyncio.wait_for(socket.close_started.wait(), timeout=2)

    socket.allow_receive.set()
    await asyncio.wait_for(socket.frame_received.wait(), timeout=2)
    assert not route_task.done()
    socket.release_close.set()
    await asyncio.wait_for(route_task, timeout=2)

    assert socket.close_attempts == [prior_code]
    assert socket.sent[-1] == {"type": "close", "code": prior_code}
    assert await hub.writer_count() == 0
    assert await hub.cleanup_count() == 0
    await hub.close()


async def test_ping_is_queued_after_existing_domain_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def authorize(_: object, __: uuid.UUID) -> bool:
        return True

    monkeypatch.setattr(conversation_api, "_authorize_websocket", authorize)
    app = create_app()
    hub = get_connection_hub(app)
    conversation_id = uuid.uuid4()
    socket = RouteSocket(
        app,
        frame={"type": "websocket.receive", "text": '{"type":"ping"}'},
    )
    route_task = asyncio.create_task(
        conversation_websocket(socket, conversation_id)  # type: ignore[arg-type]
    )
    await asyncio.wait_for(socket.accepted.wait(), timeout=2)
    domain_event = {"type": "domain.event", "data": {"sequence": 1}}
    await hub.broadcast(conversation_id, domain_event)
    await asyncio.wait_for(socket.domain_send_started.wait(), timeout=2)

    socket.allow_receive.set()
    await asyncio.wait_for(socket.frame_received.wait(), timeout=2)
    socket.release_domain_send.set()
    await asyncio.wait_for(socket.all_sent.wait(), timeout=2)
    await asyncio.wait_for(route_task, timeout=2)

    assert socket.sent == [domain_event, {"type": "pong"}]
    await hub.close()


async def test_invalid_frame_quiesces_writer_before_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def authorize(_: object, __: uuid.UUID) -> bool:
        return True

    monkeypatch.setattr(conversation_api, "_authorize_websocket", authorize)
    app = create_app()
    hub = get_connection_hub(app)
    conversation_id = uuid.uuid4()
    socket = RouteSocket(
        app,
        frame={"type": "websocket.receive", "text": "{}"},
    )
    route_task = asyncio.create_task(
        conversation_websocket(socket, conversation_id)  # type: ignore[arg-type]
    )
    await asyncio.wait_for(socket.accepted.wait(), timeout=2)
    await hub.broadcast(conversation_id, {"type": "domain.event", "data": {"sequence": 1}})
    await asyncio.wait_for(socket.domain_send_started.wait(), timeout=2)

    socket.allow_receive.set()
    await asyncio.wait_for(socket.closed.wait(), timeout=2)
    await asyncio.wait_for(route_task, timeout=2)

    assert socket.sent[-1] == {"type": "close", "code": 1003}
    assert socket.close_after_writer_quiesced is True
    await hub.close()


def test_app_shutdown_closes_sockets_and_cancels_writers() -> None:
    app = create_app()
    hub = get_connection_hub(app)
    conversation_id = uuid.uuid4()
    slow = SlowSocket()
    with TestClient(app) as client:
        assert client.portal is not None
        client.portal.call(hub.connect, conversation_id, slow)  # type: ignore[arg-type]
        client.portal.call(hub.broadcast, conversation_id, {"type": "event", "data": {}})

    assert slow.close_codes == [1001]
    assert asyncio.run(hub.writer_count()) == 0
    assert asyncio.run(hub.cleanup_count()) == 0


def test_connection_hubs_are_app_scoped() -> None:
    first = create_app()
    second = create_app()
    assert get_connection_hub(first) is not get_connection_hub(second)
