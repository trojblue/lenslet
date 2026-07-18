"""Shared FastAPI bootstrap for Lenslet app entrypoints."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from ...storage.table.source_refresh import TableSourceChangedError
from ..auth import install_request_identity_middleware
from ..lifecycle import initialize_lifecycle_state, lenslet_lifespan


def create_api_app(*, description: str) -> FastAPI:
    app = FastAPI(
        title="Lenslet",
        description=description,
        lifespan=lenslet_lifespan,
    )
    initialize_lifecycle_state(app)

    @app.exception_handler(TableSourceChangedError)
    async def _table_source_changed(_request: Request, exc: TableSourceChangedError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"error": "table_source_changed", "message": str(exc)},
        )

    app.add_middleware(GZipMiddleware, minimum_size=1000)
    install_request_identity_middleware(app)
    return app
