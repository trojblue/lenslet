"""Views route registration for Lenslet."""

from __future__ import annotations

from fastapi import FastAPI, Request

from .server_context import get_request_context
from .server_models import ViewsPayload


def register_views_routes(app: FastAPI) -> None:
    @app.get("/views", response_model=ViewsPayload)
    def get_views(request: Request):
        current = get_request_context(request).workspace
        return current.load_views()

    @app.put("/views", response_model=ViewsPayload)
    def put_views(body: ViewsPayload, request: Request):
        payload = body.model_dump()
        current = get_request_context(request).workspace
        current.save_views(payload)
        return body
