import asyncio
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request, WebSocket

logger = logging.getLogger(__name__)

RealtimeEvent = dict[str, Any]
DEFAULT_QUEUE_SIZE = 64
DEFAULT_SEND_TIMEOUT_SECONDS = 5.0


@dataclass
class _Connection:
    conversation_id: uuid.UUID
    websocket: WebSocket
    queue: asyncio.Queue[RealtimeEvent]
    writer: asyncio.Task[None] | None = None
    closed: bool = False


class ConnectionHub:
    def __init__(
        self,
        *,
        queue_size: int = DEFAULT_QUEUE_SIZE,
        send_timeout_seconds: float = DEFAULT_SEND_TIMEOUT_SECONDS,
    ) -> None:
        if queue_size < 1:
            raise ValueError("queue_size must be positive")
        if send_timeout_seconds <= 0:
            raise ValueError("send_timeout_seconds must be positive")
        self._connections: dict[uuid.UUID, dict[WebSocket, _Connection]] = defaultdict(dict)
        self._writer_tasks: set[asyncio.Task[None]] = set()
        self._cleanup_tasks: set[asyncio.Task[None]] = set()
        self._termination_tasks: dict[WebSocket, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        self._queue_size = queue_size
        self._send_timeout_seconds = send_timeout_seconds
        self._closed = False
        self._shutdown_task: asyncio.Task[None] | None = None

    async def connect(self, conversation_id: uuid.UUID, websocket: WebSocket) -> None:
        if self._closed:
            raise RuntimeError("Connection hub is closed")
        state = _Connection(
            conversation_id=conversation_id,
            websocket=websocket,
            queue=asyncio.Queue(maxsize=self._queue_size),
        )
        accepted = False
        registered = False
        try:
            await websocket.accept()
            accepted = True
            async with self._lock:
                if not self._closed:
                    writer = asyncio.create_task(self._writer(state))
                    state.writer = writer
                    self._writer_tasks.add(writer)
                    self._connections[conversation_id][websocket] = state
                    registered = True
            if not registered:
                await self._close_socket(state, code=1001)
        except asyncio.CancelledError:
            if accepted and not registered:
                await self._close_socket(state, code=1011)
            raise
        except Exception:
            if accepted and not registered:
                await self._close_socket(state, code=1011)
            raise

    async def disconnect(self, conversation_id: uuid.UUID, websocket: WebSocket) -> None:
        state = await self._detach(conversation_id, websocket)
        if state is not None:
            await self._cancel_writer(state)

    async def disconnect_and_close(
        self,
        conversation_id: uuid.UUID,
        websocket: WebSocket,
        *,
        code: int,
    ) -> None:
        async with self._lock:
            cleanup = self._termination_tasks.get(websocket)
            if cleanup is None:
                sockets = self._connections.get(conversation_id)
                state = sockets.pop(websocket, None) if sockets is not None else None
                if sockets is not None and not sockets:
                    self._connections.pop(conversation_id, None)
                if state is not None:
                    cleanup = self._schedule_termination(state, close_code=code)
        if cleanup is not None:
            await asyncio.shield(cleanup)

    async def broadcast(self, conversation_id: uuid.UUID, event: RealtimeEvent) -> None:
        async with self._lock:
            sockets = self._connections.get(conversation_id)
            if sockets is None:
                return
            for websocket, state in tuple(sockets.items()):
                if not self._enqueue_locked(state, event):
                    sockets.pop(websocket, None)
                    self._schedule_termination(state, close_code=1013)
            if not sockets:
                self._connections.pop(conversation_id, None)

    async def send_to(
        self,
        conversation_id: uuid.UUID,
        websocket: WebSocket,
        event: RealtimeEvent,
    ) -> bool:
        async with self._lock:
            sockets = self._connections.get(conversation_id)
            if sockets is None:
                return False
            state = sockets.get(websocket)
            if state is None:
                return False
            if self._enqueue_locked(state, event):
                return True
            sockets.pop(websocket, None)
            if not sockets:
                self._connections.pop(conversation_id, None)
            self._schedule_termination(state, close_code=1013)
            return False

    async def connection_count(self, conversation_id: uuid.UUID) -> int:
        async with self._lock:
            return len(self._connections.get(conversation_id, ()))

    async def writer_count(self) -> int:
        async with self._lock:
            return len(self._writer_tasks)

    async def cleanup_count(self) -> int:
        async with self._lock:
            return len(self._termination_tasks)

    async def close(self) -> None:
        async with self._lock:
            if self._shutdown_task is None:
                self._closed = True
                states = tuple(
                    state for sockets in self._connections.values() for state in sockets.values()
                )
                self._connections.clear()
                for state in states:
                    self._schedule_termination(state, close_code=1001)
                self._shutdown_task = asyncio.create_task(self._shutdown())
            shutdown = self._shutdown_task
        await asyncio.shield(shutdown)

    async def _shutdown(self) -> None:
        async with self._lock:
            writers = tuple(self._writer_tasks)
            cleanup = tuple(self._cleanup_tasks)
        for writer in writers:
            writer.cancel()
        if writers:
            await asyncio.gather(*writers, return_exceptions=True)
        if cleanup:
            await asyncio.gather(*cleanup, return_exceptions=True)

    def _enqueue_locked(self, state: _Connection, event: RealtimeEvent) -> bool:
        try:
            state.queue.put_nowait(event)
        except asyncio.QueueFull:
            return False
        return True

    async def _writer(self, state: _Connection) -> None:
        try:
            while True:
                event = await state.queue.get()
                try:
                    async with asyncio.timeout(self._send_timeout_seconds):
                        await state.websocket.send_json(event)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    cleanup = await self._detach_and_schedule_close(state, code=1011)
                    if cleanup is not None:
                        await asyncio.shield(cleanup)
                    return
        except asyncio.CancelledError:
            raise
        finally:
            current = asyncio.current_task()
            if current is not None:
                async with self._lock:
                    self._writer_tasks.discard(current)

    async def _detach(self, conversation_id: uuid.UUID, websocket: WebSocket) -> _Connection | None:
        async with self._lock:
            sockets = self._connections.get(conversation_id)
            if sockets is None:
                return None
            state = sockets.pop(websocket, None)
            if not sockets:
                self._connections.pop(conversation_id, None)
            return state

    async def _detach_and_schedule_close(
        self, state: _Connection, *, code: int
    ) -> asyncio.Task[None] | None:
        async with self._lock:
            existing = self._termination_tasks.get(state.websocket)
            if existing is not None:
                return existing
            sockets = self._connections.get(state.conversation_id)
            if sockets is None or sockets.get(state.websocket) is not state:
                return None
            sockets.pop(state.websocket, None)
            if not sockets:
                self._connections.pop(state.conversation_id, None)
            return self._schedule_close(state, close_code=code)

    def _schedule_termination(self, state: _Connection, *, close_code: int) -> asyncio.Task[None]:
        existing = self._termination_tasks.get(state.websocket)
        if existing is not None:
            return existing
        task = asyncio.create_task(self._terminate_and_close(state, close_code=close_code))
        self._cleanup_tasks.add(task)
        self._termination_tasks[state.websocket] = task
        return task

    def _schedule_close(self, state: _Connection, *, close_code: int) -> asyncio.Task[None]:
        existing = self._termination_tasks.get(state.websocket)
        if existing is not None:
            return existing
        task = asyncio.create_task(self._close_owned(state, close_code=close_code))
        self._cleanup_tasks.add(task)
        self._termination_tasks[state.websocket] = task
        return task

    async def _close_owned(self, state: _Connection, *, close_code: int) -> None:
        try:
            await self._close_socket(state, code=close_code)
        finally:
            current = asyncio.current_task()
            if current is not None:
                async with self._lock:
                    self._cleanup_tasks.discard(current)
                    if self._termination_tasks.get(state.websocket) is current:
                        self._termination_tasks.pop(state.websocket, None)

    async def _terminate_and_close(self, state: _Connection, *, close_code: int) -> None:
        try:
            await self._cancel_writer(state)
            await self._close_socket(state, code=close_code)
        finally:
            current = asyncio.current_task()
            if current is not None:
                async with self._lock:
                    self._cleanup_tasks.discard(current)
                    if self._termination_tasks.get(state.websocket) is current:
                        self._termination_tasks.pop(state.websocket, None)

    async def _cancel_writer(self, state: _Connection) -> None:
        writer = state.writer
        current = asyncio.current_task()
        if writer is not None and writer is not current and not writer.done():
            writer.cancel()
            await asyncio.gather(writer, return_exceptions=True)

    async def _close_socket(self, state: _Connection, *, code: int) -> None:
        if state.closed:
            return
        state.closed = True
        try:
            async with asyncio.timeout(self._send_timeout_seconds):
                await state.websocket.close(code=code)
        except asyncio.CancelledError:
            state.closed = False
            raise
        except Exception:
            return


def get_connection_hub(connection: Request | WebSocket | FastAPI) -> ConnectionHub:
    app = connection if isinstance(connection, FastAPI) else connection.app
    hub = getattr(app.state, "connection_hub", None)
    if not isinstance(hub, ConnectionHub):
        raise RuntimeError("Connection hub is not initialized")
    return hub


async def safe_broadcast(
    connection: Request | WebSocket,
    conversation_id: uuid.UUID,
    event: RealtimeEvent,
) -> None:
    try:
        await get_connection_hub(connection).broadcast(conversation_id, event)
    except Exception:
        logger.warning("Realtime broadcast failed after committed mutation", exc_info=True)
