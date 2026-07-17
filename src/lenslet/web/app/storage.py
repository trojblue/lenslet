"""Generic storage-backed browse app mode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from ...indexing_status import IndexingLifecycle
from ...storage.base import BrowseAppStorage, SidecarStateStorage
from ...storage.dataset.storage import DatasetStorage
from ...storage.memory.storage import MemoryStorage
from ...storage.table.storage import TableStorage
from ...workspace import Workspace
from ..browse import build_item_payload, categoricals_for_cached_item
from ..context import get_app_context, get_request_context
from ..models import ErrorResponse, HealthResponse, LaunchSessionPayload, RefreshResponse
from ..permissions import deny_if_mutation_forbidden
from ..paths import canonical_path
from .base import create_api_app
from .builder import BrowseAppAdapters, BrowseAppAssembly, BrowseAppContextInputs, finalize_browse_app
from .health import (
    REFRESH_NOTE_DATASET_STATIC,
    REFRESH_NOTE_TABLE_STATIC,
    _base_health_payload,
    _indexing_health_payload,
    _workspace_id_for_browse_storage,
)
from .options import StorageAppOptions, StorageMode, StorageRefreshMode
from .shared import (
    build_embedding_manager,
    build_record_update,
    embedding_cache_from_workspace,
    initialize_runtime,
    mutation_policy_for_workspace,
    register_static_refresh_route,
    resolve_embedding_detection,
)
from ..auth import set_mutation_policy
from ..record_update import RecordUpdateFn


@dataclass(frozen=True, slots=True)
class StorageAppIdentity:
    mode: StorageMode
    origin: str | None
    refresh: StorageRefreshMode
    static_refresh_note: str | None


def create_storage_app(
    storage: BrowseAppStorage,
    *,
    options: StorageAppOptions | None = None,
) -> FastAPI:
    """Create a browse app around an already-built storage backend."""
    options = options or StorageAppOptions()
    browse_options = options.browse
    embedding_options = options.embedding
    app = create_api_app(description="Lightweight image gallery server (browse mode)")

    workspace = options.workspace
    if workspace is None:
        workspace = Workspace.for_dataset(None, can_write=False)
    set_mutation_policy(
        app,
        mutation_policy_for_workspace(
            workspace,
            trusted_write_origins=options.trusted_write_origins,
        ),
    )
    runtime = initialize_runtime(
        app,
        storage=storage,
        workspace=workspace,
        thumb_cache=browse_options.thumb_cache,
        presence_view_ttl=browse_options.presence_view_ttl,
        presence_edit_ttl=browse_options.presence_edit_ttl,
        presence_prune_interval=browse_options.presence_prune_interval,
    )
    indexing = IndexingLifecycle.ready(scope="/")
    if browse_options.indexing_listener is not None:
        indexing.subscribe(browse_options.indexing_listener, emit_current=True)
    identity = resolve_storage_app_identity(storage, options)
    embedding_manager = None
    if options.embedding_table_path and isinstance(storage, TableStorage):
        detection = resolve_embedding_detection(options.embedding_table_path, embedding_options.config)
        embed_cache = embedding_cache_from_workspace(
            workspace,
            enabled=embedding_options.cache,
            cache_dir=embedding_options.cache_dir,
        )
        embedding_manager = build_embedding_manager(
            options.embedding_table_path,
            storage,
            detection,
            cache=embed_cache,
            preload=embedding_options.preload,
        )
    adapters = build_storage_browse_adapters(
        app,
        show_source=options.show_source,
        launch_session=options.launch_session,
        record_update=build_record_update(app),
        register_refresh_routes=storage_refresh_registrar(identity),
        refresh_mode=identity.refresh,
        static_refresh_note=identity.static_refresh_note,
    )

    return finalize_browse_app(
        app,
        BrowseAppAssembly(
            context=BrowseAppContextInputs(
                storage=storage,
                workspace=workspace,
                runtime=runtime,
                indexing=indexing,
                storage_mode=identity.mode,
                storage_origin=identity.origin,
                og_preview=options.og_preview,
            ),
            adapters=adapters,
            embedding_manager=embedding_manager,
        ),
    )


def infer_storage_mode(storage: BrowseAppStorage) -> StorageMode:
    if isinstance(storage, TableStorage):
        return "table"
    if isinstance(storage, MemoryStorage):
        return "memory"
    if isinstance(storage, DatasetStorage):
        return "dataset"
    return "storage"


def static_refresh_note_for_mode(mode: StorageMode) -> str:
    if mode == "dataset":
        return REFRESH_NOTE_DATASET_STATIC
    if mode == "table":
        return REFRESH_NOTE_TABLE_STATIC
    return "storage mode is static"


def storage_refresh_mode(
    storage: BrowseAppStorage,
    mode: StorageMode,
    configured: StorageRefreshMode | None,
) -> StorageRefreshMode:
    supports_subtree_refresh = callable(getattr(storage, "refresh_subtree", None))
    if configured == "subtree" and not supports_subtree_refresh:
        raise ValueError("storage refresh='subtree' requires refresh_subtree support")
    if configured is not None:
        return configured
    if mode == "memory" and supports_subtree_refresh:
        return "subtree"
    return "static"


def resolve_storage_app_identity(
    storage: BrowseAppStorage,
    options: StorageAppOptions,
) -> StorageAppIdentity:
    mode = options.storage_mode or infer_storage_mode(storage)
    refresh = storage_refresh_mode(storage, mode, options.refresh)
    return StorageAppIdentity(
        mode=mode,
        origin=options.storage_origin if options.storage_origin is not None else mode,
        refresh=refresh,
        static_refresh_note=static_refresh_note_for_mode(mode) if refresh == "static" else None,
    )


def register_subtree_refresh_route(app: FastAPI) -> None:
    @app.post(
        "/refresh",
        response_model=RefreshResponse,
        response_model_exclude_none=True,
        responses={403: {"model": ErrorResponse}},
    )
    def refresh(request: Request, path: str = "/") -> RefreshResponse | JSONResponse:
        context = get_request_context(request)
        if denied := deny_if_mutation_forbidden(request, writes_enabled=context.workspace.can_write):
            return denied
        refresh_subtree = getattr(context.storage, "refresh_subtree", None)
        if not callable(refresh_subtree):
            raise HTTPException(500, "storage does not support subtree refresh")

        path = canonical_path(path)
        try:
            refresh_subtree(path, preserve_sidecars=True)
        except ValueError as exc:
            raise HTTPException(400, "invalid path") from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, "folder not found") from exc
        if context.recursive_browse_cache is not None:
            context.recursive_browse_cache.invalidate_path(path)
        return RefreshResponse(ok=True)


def storage_refresh_registrar(identity: StorageAppIdentity):
    if identity.refresh == "subtree":
        return register_subtree_refresh_route
    note = identity.static_refresh_note or "storage mode is static"
    return lambda target_app: register_static_refresh_route(target_app, note=note)


def build_storage_browse_adapters(
    app: FastAPI,
    *,
    show_source: bool,
    launch_session: LaunchSessionPayload | None,
    record_update: RecordUpdateFn,
    register_refresh_routes,
    refresh_mode: StorageRefreshMode | Literal["default"] = "default",
    static_refresh_note: str | None = None,
) -> BrowseAppAdapters:
    def _to_item(storage: SidecarStateStorage, cached: Any) -> Any:
        sidecar_state = storage.get_sidecar_readonly(cached.path)
        source = getattr(cached, "source", None) if show_source else None
        return build_item_payload(
            cached,
            sidecar_state,
            source=source,
            categoricals=categoricals_for_cached_item(storage, cached),
        )

    def _health_payload(request: Request) -> HealthResponse:
        context = get_app_context(app)
        return _base_health_payload(
            request=request,
            mode=context.storage_mode,
            workspace_id=_workspace_id_for_browse_storage(context.storage, context.workspace),
            storage_origin=context.storage_origin,
            storage=context.storage,
            workspace=context.workspace,
            runtime=context.runtime,
            recursive_browse_cache=context.recursive_browse_cache,
            launch_session=launch_session,
            refresh_mode=refresh_mode,
            static_refresh_note=static_refresh_note,
        ).model_copy(
            update={
                "total_images": context.storage.total_items(),
                "indexing": _indexing_health_payload(context.indexing, context.storage),
            }
        )

    return BrowseAppAdapters(
        include_index_routes=True,
        to_item=_to_item,
        record_update=record_update,
        health_payload=_health_payload,
        register_refresh_routes=register_refresh_routes,
    )
