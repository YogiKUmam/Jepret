from fastapi import APIRouter, Depends, WebSocket
from fastapi.responses import JSONResponse

from app.core.errors import error_response
from app.db.session import database_ready

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, dict[str, str]]:
    return {"data": {"status": "ok"}}


@router.get("/ready", response_model=None)
async def ready(
    is_ready: bool = Depends(database_ready),
) -> dict[str, dict[str, str]] | JSONResponse:
    if not is_ready:
        return error_response(503, "DEPENDENCY_UNAVAILABLE", "Layanan belum siap.")
    return {"data": {"status": "ready"}}


@router.websocket("/ws/health")
async def websocket_health(websocket: WebSocket) -> None:
    """Development probe validating gateway WebSocket upgrade forwarding only.

    Authenticated business WebSockets are added during the chat phase.
    """
    await websocket.accept()
    await websocket.send_json({"status": "ok"})
    await websocket.close()
