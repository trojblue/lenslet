"""Views route registration for Lenslet."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .server_context import get_request_context
from .server_models import ViewsPayload
from .server_permissions import deny_if_mutation_forbidden

ViewsRouteResponse = ViewsPayload | JSONResponse


def register_views_routes(app: FastAPI) -> None:
    @app.get("/views", response_model=ViewsPayload)
    def get_views(request: Request) -> ViewsPayload:
        current = get_request_context(request).workspace
        result = current.load_views_result()
        if result.status not in {"missing", "ok"}:
            raise HTTPException(500, "workspace views are unreadable")
        return ViewsPayload.model_validate(result.value)

    @app.put("/views", response_model=ViewsPayload)
    def put_views(body: ViewsPayload, request: Request) -> ViewsRouteResponse:
        current = get_request_context(request).workspace
        if denied := deny_if_mutation_forbidden(request, writes_enabled=current.can_write):
            return denied
        payload = body.model_dump()
        current.save_views(payload)
        return ViewsPayload.model_validate(payload)
