from fastapi import APIRouter, Depends
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
