from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    error: ErrorBody


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorEnvelope(error=ErrorBody(code=code, message=message)).model_dump(),
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, __: RequestValidationError) -> JSONResponse:
        return error_response(422, "REQUEST_VALIDATION_FAILED", "Data permintaan tidak valid.")

    @app.exception_handler(404)
    async def not_found_handler(_: Request, __: Exception) -> JSONResponse:
        return error_response(404, "ROUTE_NOT_FOUND", "Endpoint tidak ditemukan.")
