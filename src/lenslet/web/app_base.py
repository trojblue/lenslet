"""Shared FastAPI bootstrap for Lenslet app entrypoints."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from .auth import install_request_identity_middleware

LifecycleHandler = Callable[[], Any]

_STARTUP_HANDLERS = "lenslet_startup_handlers"
_SHUTDOWN_HANDLERS = "lenslet_shutdown_handlers"


async def _run_lifecycle_handler(handler: LifecycleHandler) -> None:
    result = handler()
    if inspect.isawaitable(result):
        await result


@asynccontextmanager
async def _lenslet_lifespan(app: FastAPI):
    for handler in list(getattr(app.state, _STARTUP_HANDLERS, [])):
        await _run_lifecycle_handler(handler)
    try:
        yield
    finally:
        for handler in reversed(list(getattr(app.state, _SHUTDOWN_HANDLERS, []))):
            await _run_lifecycle_handler(handler)


def register_lifecycle_handlers(
    app: FastAPI,
    *,
    startup: LifecycleHandler | None = None,
    shutdown: LifecycleHandler | None = None,
) -> None:
    if startup is not None:
        getattr(app.state, _STARTUP_HANDLERS).append(startup)
    if shutdown is not None:
        getattr(app.state, _SHUTDOWN_HANDLERS).append(shutdown)


def create_api_app(*, description: str) -> FastAPI:
    app = FastAPI(
        title="Lenslet",
        description=description,
        lifespan=_lenslet_lifespan,
    )
    setattr(app.state, _STARTUP_HANDLERS, [])
    setattr(app.state, _SHUTDOWN_HANDLERS, [])
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    install_request_identity_middleware(app)
    return app
