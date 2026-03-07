"""Mutable per-app runtime context for refresh-sensitive routes."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from fastapi import FastAPI, Request

from .browse_cache import RecursiveBrowseCache
from .indexing_status import IndexingLifecycle
from .og_cache import OgImageCache
from .server_runtime import AppRuntime
from .workspace import Workspace

_APP_CONTEXT_ATTR = "lenslet_app_context"
_REQUEST_CONTEXT_ATTR = "lenslet_app_context"


@dataclass
class AppContext:
    storage: Any
    workspace: Workspace
    runtime: AppRuntime
    recursive_browse_cache: RecursiveBrowseCache | None
    og_cache: OgImageCache | None
    storage_mode: str
    storage_origin: str | None
    indexing: IndexingLifecycle


def set_app_context(app: FastAPI, context: AppContext) -> AppContext:
    setattr(app.state, _APP_CONTEXT_ATTR, context)
    # Keep these mirrors while the rest of the app finishes moving to app context.
    app.state.storage = context.storage
    app.state.workspace = context.workspace
    app.state.runtime = context.runtime
    app.state.recursive_browse_cache = context.recursive_browse_cache
    app.state.storage_mode = context.storage_mode
    app.state.storage_origin = context.storage_origin
    return context


def get_app_context(app: FastAPI) -> AppContext:
    context = getattr(app.state, _APP_CONTEXT_ATTR, None)
    if context is None:
        raise RuntimeError("lenslet app context is not initialized")
    return context


def replace_app_context(app: FastAPI, **changes: Any) -> AppContext:
    current = get_app_context(app)
    updated = replace(current, **changes)
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
