from __future__ import annotations

from fastapi.responses import JSONResponse

from .models import ErrorResponse


def error_response(status: int, error: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": error, "message": message})


def error_response_models(*statuses: int) -> dict[int, dict[str, type[ErrorResponse]]]:
    return {status: {"model": ErrorResponse} for status in statuses}
