from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

LifecycleHandler = Callable[[], Any]

_STARTUP_HANDLERS = "lenslet_startup_handlers"
_SHUTDOWN_HANDLERS = "lenslet_shutdown_handlers"


async def _run_lifecycle_handler(handler: LifecycleHandler) -> None:
    result = handler()
    if inspect.isawaitable(result):
        await result


@asynccontextmanager
async def lenslet_lifespan(app: FastAPI) -> AsyncIterator[None]:
    for handler in list(getattr(app.state, _STARTUP_HANDLERS, [])):
        await _run_lifecycle_handler(handler)
    try:
        yield
    finally:
        for handler in reversed(list(getattr(app.state, _SHUTDOWN_HANDLERS, []))):
            await _run_lifecycle_handler(handler)


def initialize_lifecycle_state(app: FastAPI) -> None:
    setattr(app.state, _STARTUP_HANDLERS, [])
    setattr(app.state, _SHUTDOWN_HANDLERS, [])


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
