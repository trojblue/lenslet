"""Shared FastAPI bootstrap for Lenslet app entrypoints."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from ..auth import install_request_identity_middleware
from ..lifecycle import initialize_lifecycle_state, lenslet_lifespan


def create_api_app(*, description: str) -> FastAPI:
    app = FastAPI(
        title="Lenslet",
        description=description,
        lifespan=lenslet_lifespan,
    )
    initialize_lifecycle_state(app)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    install_request_identity_middleware(app)
    return app
