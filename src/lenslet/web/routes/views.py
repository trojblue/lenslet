"""Views route registration for Lenslet."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..context import get_request_context
from ..models import ViewsPayload
from ..permissions import deny_if_mutation_forbidden
from ..responses import error_response, error_response_models

ViewsRouteResponse = ViewsPayload | JSONResponse


def register_views_routes(app: FastAPI) -> None:
    @app.get("/views", response_model=ViewsPayload, responses=error_response_models(500))
    def get_views(request: Request) -> ViewsPayload | JSONResponse:
        current = get_request_context(request).workspace
        result = current.load_views_result()
        if result.status not in {"missing", "ok"}:
            return error_response(500, "views_unreadable", "workspace views are unreadable")
        return ViewsPayload.model_validate(result.value)

    @app.put("/views", response_model=ViewsPayload, responses=error_response_models(403))
    def put_views(body: ViewsPayload, request: Request) -> ViewsRouteResponse:
        current = get_request_context(request).workspace
        if denied := deny_if_mutation_forbidden(request, writes_enabled=current.can_write):
            return denied
        payload = body.model_dump()
        current.write_views(payload)
        return ViewsPayload.model_validate(payload)
