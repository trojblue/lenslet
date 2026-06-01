"""Mutable per-app runtime context for refresh-sensitive routes."""

from __future__ import annotations

from dataclasses import dataclass, replace

from fastapi import FastAPI, Request
from starlette.types import ASGIApp, Receive, Scope, Send

from .cache.browse import RecursiveBrowseCache
from ..indexing_status import IndexingLifecycle
from .app.options import StorageMode
from .cache.og import OgImageCache
from ..storage.base import BrowseAppStorage
from ..workspace import Workspace
from .runtime import AppRuntime

_APP_CONTEXT_ATTR = "lenslet_app_context"
_REQUEST_CONTEXT_ATTR = "lenslet_app_context"


@dataclass
class AppContext:
    storage: BrowseAppStorage
    workspace: Workspace
    runtime: AppRuntime
    recursive_browse_cache: RecursiveBrowseCache | None
    og_cache: OgImageCache | None
    storage_mode: StorageMode
    storage_origin: str | None
    indexing: IndexingLifecycle


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            bind_request_context(Request(scope, receive=receive))
        await self.app(scope, receive, send)


def set_app_context(app: FastAPI, context: AppContext) -> AppContext:
    setattr(app.state, _APP_CONTEXT_ATTR, context)
    return context


def get_app_context(app: FastAPI) -> AppContext:
    context = getattr(app.state, _APP_CONTEXT_ATTR, None)
    if context is None:
        raise RuntimeError("lenslet app context is not initialized")
    return context


def get_app_runtime(app: FastAPI) -> AppRuntime:
    return get_app_context(app).runtime


def replace_app_runtime(app: FastAPI, runtime: AppRuntime) -> AppContext:
    current = get_app_context(app)
    updated = replace(current, runtime=runtime)
    return set_app_context(app, updated)


def bind_request_context(request: Request) -> AppContext:
    context = get_app_context(request.app)
    setattr(request.state, _REQUEST_CONTEXT_ATTR, context)
    return context


def get_request_context(request: Request) -> AppContext:
    context = getattr(request.state, _REQUEST_CONTEXT_ATTR, None)
    if context is not None:
        return context
    return get_app_context(request.app)
