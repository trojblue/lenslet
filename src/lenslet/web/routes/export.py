from __future__ import annotations

from fastapi import FastAPI, Request, Response
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..browse import storage_from_request
from ..export.response import export_comparison_response
from ..models import ErrorResponse, ExportComparisonRequest
from ..responses import error_response


def _error_response(status: int, error: str, message: str) -> JSONResponse:
    return error_response(status, error, message)


def _request_validation_error_detail(exc: RequestValidationError) -> str:
    first = exc.errors()[0] if exc.errors() else {"msg": "invalid request payload", "loc": ()}
    loc = [str(part) for part in first.get("loc", ()) if part != "body"]
    msg = str(first.get("msg", "invalid request payload"))
    return f"{'.'.join(loc)}: {msg}" if loc else msg


async def _export_request_validation_error_handler(
    request: Request,
    exc: RequestValidationError,
) -> Response:
    if request.url.path != "/export-comparison":
        return await request_validation_exception_handler(request, exc)
    first = exc.errors()[0] if exc.errors() else {}
    if first.get("type") == "json_invalid":
        return _error_response(400, "invalid_json", "request body must be valid JSON")
    return _error_response(400, "invalid_request", _request_validation_error_detail(exc))


def register_export_routes(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _export_request_validation_error_handler)

    export_error_responses = {
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    }

    @app.post(
        "/export-comparison",
        responses={
            200: {
                "description": "Rendered comparison image.",
                "content": {
                    "image/png": {"schema": {"type": "string", "format": "binary"}},
                    "image/gif": {"schema": {"type": "string", "format": "binary"}},
                },
            },
            **export_error_responses,
        },
        response_class=Response,
    )
    def export_comparison(body: ExportComparisonRequest, request: Request) -> Response:
        storage = storage_from_request(request)
        return export_comparison_response(storage, body)
