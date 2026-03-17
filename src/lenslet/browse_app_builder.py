"""Shared browse-app assembly for Lenslet server modes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request

from .browse_cache import RecursiveBrowseCache
from .frontend_serving import mount_frontend
from .indexing_status import IndexingLifecycle
from .server_context import AppContext, bind_request_context, set_app_context
from .server_routes_common import RecordUpdateFn, register_common_api_routes
from .server_routes_embeddings import register_embedding_routes
from .server_routes_index import register_index_routes
from .server_routes_og import _og_cache_from_workspace, register_og_routes
from .server_routes_views import register_views_routes
from .server_runtime import AppRuntime
from .storage.base import BrowseStorage
from .workspace import Workspace

ToItemFn = Callable[[BrowseStorage, Any], Any]
HealthPayloadFn = Callable[[Request], dict[str, Any]]
RegisterRefreshRoutesFn = Callable[[FastAPI], None]


def finalize_browse_app(
    app: FastAPI,
    *,
    storage: BrowseStorage,
    workspace: Workspace,
    runtime: AppRuntime,
    indexing: IndexingLifecycle,
    storage_mode: str,
    storage_origin: str | None,
    og_preview: bool,
    include_index_routes: bool,
    to_item: ToItemFn,
    record_update: RecordUpdateFn,
    health_payload: HealthPayloadFn,
    register_refresh_routes: RegisterRefreshRoutesFn,
    embedding_manager: Any,
) -> FastAPI:
    set_runtime_context(
        app,
        storage=storage,
        workspace=workspace,
        runtime=runtime,
        storage_mode=storage_mode,
        storage_origin=storage_origin,
        indexing=indexing,
        og_preview=og_preview,
    )
    _attach_request_context(app)

    @app.get("/health")
    def health(request: Request):
        return health_payload(request)

    register_refresh_routes(app)

    register_common_api_routes(
        app,
        to_item,
        meta_lock=runtime.meta_lock,
        presence=runtime.presence,
        broker=runtime.broker,
        presence_metrics=runtime.presence_metrics,
        idempotency_cache=runtime.idempotency_cache,
        record_update=record_update,
    )
    register_embedding_routes(app, storage, embedding_manager)
    if include_index_routes:
        register_og_routes(app, enabled=og_preview)
        register_index_routes(app, og_preview=og_preview)
    register_views_routes(app)
    mount_frontend(app)
    return app


def set_runtime_context(
    app: FastAPI,
    *,
    storage: BrowseStorage,
    workspace: Workspace,
    runtime: AppRuntime,
    storage_mode: str,
    storage_origin: str | None,
    indexing: IndexingLifecycle,
    og_preview: bool,
) -> AppContext:
    return set_app_context(
        app,
        AppContext(
            storage=storage,
            workspace=workspace,
            runtime=runtime,
            recursive_browse_cache=RecursiveBrowseCache(cache_dir=workspace.browse_cache_dir()),
            og_cache=_og_cache_from_workspace(workspace, enabled=og_preview),
            storage_mode=storage_mode,
            storage_origin=storage_origin,
            indexing=indexing,
        ),
    )


def _attach_request_context(app: FastAPI) -> None:
    @app.middleware("http")
    async def attach_request_context(request: Request, call_next):
        bind_request_context(request)
        return await call_next(request)
