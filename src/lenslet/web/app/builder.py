"""Shared browse-app assembly for Lenslet server modes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import FastAPI, Request

from ..browse import ToItemFn
from ..cache.browse import RecursiveBrowseCache
from ..context import AppContext, RequestContextMiddleware, get_app_runtime, set_app_context
from ..frontend import mount_frontend
from ..hotpath import install_hotpath_timing_middleware
from ..record_update import RecordUpdateFn
from ..runtime import AppRuntime
from ...embeddings.index import EmbeddingManager
from ...indexing_status import IndexingLifecycle
from .options import StorageMode
from ..presence_runtime import install_presence_prune_loop
from ..routes.common import register_common_api_routes
from ..routes.embeddings import register_embedding_routes
from ..routes.index import register_index_routes
from ..routes.og import og_cache_from_workspace, register_og_routes
from ..routes.presence import register_presence_routes
from ..routes.views import register_views_routes
from ...storage.base import BrowseAppStorage
from ...workspace import Workspace
from ..models import HealthResponse

HealthPayloadFn = Callable[[Request], HealthResponse]
RegisterRefreshRoutesFn = Callable[[FastAPI], None]


@dataclass(frozen=True, slots=True)
class BrowseAppContextInputs:
    storage: BrowseAppStorage
    workspace: Workspace
    runtime: AppRuntime
    indexing: IndexingLifecycle
    storage_mode: StorageMode
    storage_origin: str | None
    og_preview: bool


@dataclass(frozen=True, slots=True)
class BrowseAppAdapters:
    include_index_routes: bool
    to_item: ToItemFn
    record_update: RecordUpdateFn
    health_payload: HealthPayloadFn
    register_refresh_routes: RegisterRefreshRoutesFn


@dataclass(frozen=True, slots=True)
class BrowseAppAssembly:
    context: BrowseAppContextInputs
    adapters: BrowseAppAdapters
    embedding_manager: EmbeddingManager | None


def finalize_browse_app(
    app: FastAPI,
    assembly: BrowseAppAssembly,
) -> FastAPI:
    context = assembly.context
    adapters = assembly.adapters
    set_runtime_context(app, context)
    install_presence_prune_loop(
        app,
        context.runtime.presence_prune_interval,
        lambda: get_app_runtime(app),
    )
    _attach_request_context(app)
    install_hotpath_timing_middleware(app, context.runtime.hotpath_metrics)

    @app.get("/health", response_model=HealthResponse, response_model_exclude_none=True)
    def health(request: Request) -> HealthResponse:
        return adapters.health_payload(request)

    adapters.register_refresh_routes(app)

    register_common_api_routes(
        app,
        adapters.to_item,
        record_update=adapters.record_update,
    )
    register_presence_routes(app)
    register_embedding_routes(app, assembly.embedding_manager)
    if adapters.include_index_routes:
        register_og_routes(app, enabled=context.og_preview)
        register_index_routes(app, og_preview=context.og_preview)
    register_views_routes(app)
    mount_frontend(app)
    return app


def set_runtime_context(
    app: FastAPI,
    context: BrowseAppContextInputs,
) -> AppContext:
    return set_app_context(app, build_runtime_context(context))


def build_runtime_context(context: BrowseAppContextInputs) -> AppContext:
    return AppContext(
        storage=context.storage,
        workspace=context.workspace,
        runtime=context.runtime,
        recursive_browse_cache=RecursiveBrowseCache(cache_dir=context.workspace.browse_cache_dir()),
        og_cache=og_cache_from_workspace(context.workspace, enabled=context.og_preview),
        storage_mode=context.storage_mode,
        storage_origin=context.storage_origin,
        indexing=context.indexing,
    )


def _attach_request_context(app: FastAPI) -> None:
    app.add_middleware(RequestContextMiddleware)
