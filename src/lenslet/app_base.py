"""Shared FastAPI bootstrap for Lenslet app entrypoints."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from .server_auth import install_request_identity_middleware


def create_api_app(*, description: str) -> FastAPI:
    app = FastAPI(
        title="Lenslet",
        description=description,
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    install_request_identity_middleware(app)
    return app
