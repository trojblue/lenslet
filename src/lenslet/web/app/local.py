"""Local browse app adapter and indexing wiring."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pyarrow.lib import ArrowException

from ...degraded import report_degraded_feature
from ...embeddings.config import EmbeddingConfig
from ...embeddings.detect import EmbeddingDetection
from ...embeddings.index import EmbeddingManager
from ...indexing_status import IndexingLifecycle
from ...storage.local.preindex import (
    PREINDEX_PATH_COLUMN,
    PREINDEX_SOURCE_COLUMN,
    compute_signature,
    ensure_local_preindex,
    load_preindex_meta,
    load_preindex_table,
    preindex_paths,
    scan_local_images,
)
from ...storage.base import BrowseAppStorage, SidecarStateStorage
from ...storage.memory.storage import MemoryStorage
from ...storage.table.storage import TableStorage, TableStorageOptions
from ...storage.table.launch import TableLaunchRequest, TableLaunchResult, prepare_table_launch
from ...workspace import Workspace
from ..auth import set_mutation_policy
from ..browse import build_item_payload, categoricals_for_cached_item
from ..context import AppContext, get_app_context, get_request_context
from ..lifecycle import register_lifecycle_handlers
from ..models import ErrorResponse, HealthResponse, RefreshResponse
from ..permissions import deny_if_mutation_forbidden
from ..record_update import RecordUpdateFn
from ..paths import canonical_path
from .base import create_api_app
from .builder import (
    BrowseAppAdapters,
    BrowseAppAssembly,
    BrowseAppContextInputs,
    finalize_browse_app,
    set_runtime_context,
)
from .health import (
    REFRESH_NOTE_TABLE_STATIC,
    _base_health_payload,
    _indexing_health_payload,
    _workspace_id_for_root_path,
)
from .options import BrowseAppOptions, EmbeddingAppOptions, LocalAppOptions, StorageMode
from .shared import (
    build_embedding_manager,
    build_record_update,
    embedding_cache_from_workspace,
    initialize_runtime,
    mutation_policy_for_workspace,
    runtime_for_workspace,
)

IndexWarmupErrors = tuple[type[Exception], ...]
LocalPreindexRefreshFn = Callable[..., dict[str, bool]]
_PREINDEX_SIGNATURE_ERRORS = (OSError, RuntimeError, ValueError)
_PREINDEX_BUILD_ERRORS = (ArrowException, ImportError, OSError, RuntimeError, TypeError, ValueError)
_TABLE_STORAGE_ERRORS = (ArrowException, ImportError, OSError, TypeError, ValueError)
_INDEX_WARMUP_ERRORS = (OSError, RuntimeError, TypeError, ValueError)


class PreindexStartupError(RuntimeError):
    """Raised when a preindex-backed startup path fails unexpectedly."""


@dataclass(frozen=True, slots=True)
class LocalStartupState:
    storage: BrowseAppStorage
    workspace: Workspace
    storage_mode: StorageMode
    storage_origin: str
    embedding_detection: EmbeddingDetection
    table_parquet_path: str | None = None
    preindex_signature: str | None = None


def resolve_local_workspace(root_path: str, options: LocalAppOptions) -> Workspace:
    workspace = options.workspace
    if workspace is None:
        if options.no_write:
            workspace = Workspace.for_temp_dataset(root_path)
        else:
            workspace = Workspace.for_dataset(root_path, can_write=True)
    try:
        workspace.ensure()
    except OSError as exc:
        raise RuntimeError(f"failed to initialize workspace: {exc}") from exc
    return workspace


def resolve_local_storage_startup(
    root_path: str,
    workspace: Workspace,
    *,
    options: LocalAppOptions,
    browse_options: BrowseAppOptions,
    embedding_options: EmbeddingAppOptions,
    table_launch: TableLaunchResult | None = None,
) -> LocalStartupState:
    items_path = Path(root_path) / "items.parquet"
    if table_launch is not None or items_path.is_file():
        if table_launch is None:
            table_launch = _prepare_items_table_launch(
                root_path,
                items_path,
                workspace=workspace,
                options=options,
                browse_options=browse_options,
                embedding_options=embedding_options,
            )
        return LocalStartupState(
            storage=table_launch.storage,
            workspace=workspace,
            storage_mode="table",
            storage_origin="parquet",
            embedding_detection=table_launch.embedding_detection or EmbeddingDetection.empty(),
            table_parquet_path=str(items_path) if items_path.is_file() else None,
            preindex_signature=options.preindex_signature,
        )

    preindex_storage, workspace, preindex_signature = ensure_preindex_storage(
        root_path,
        workspace,
        thumb_size=browse_options.thumb_size,
        thumb_quality=browse_options.thumb_quality,
        skip_dimension_probe=options.skip_dimension_probe,
        preindex_signature=options.preindex_signature,
    )
    if preindex_storage is not None:
        return LocalStartupState(
            storage=preindex_storage,
            workspace=workspace,
            storage_mode="table",
            storage_origin="preindex",
            embedding_detection=EmbeddingDetection.empty(),
            preindex_signature=preindex_signature,
        )

    return LocalStartupState(
        storage=MemoryStorage(
            root=root_path,
            thumb_size=browse_options.thumb_size,
            thumb_quality=browse_options.thumb_quality,
        ),
        workspace=workspace,
        storage_mode="memory",
        storage_origin="memory",
        embedding_detection=EmbeddingDetection.empty(),
        preindex_signature=preindex_signature,
    )


def _prepare_items_table_launch(
    root_path: str,
    items_path: Path,
    *,
    workspace: Workspace,
    options: LocalAppOptions,
    browse_options: BrowseAppOptions,
    embedding_options: EmbeddingAppOptions,
) -> TableLaunchResult:
    try:
        return prepare_table_launch(
            TableLaunchRequest(
                parquet_path=items_path,
                base_dir=root_path,
                source_column=options.source_column,
                path_column=options.path_column,
                cache_dimensions=False,
                dimension_cache_dir=workspace.dimension_cache_dir(),
                skip_dimension_probe=options.skip_dimension_probe,
                embedding_config=embedding_options.config or EmbeddingConfig(),
                thumb_size=browse_options.thumb_size,
                thumb_quality=browse_options.thumb_quality,
            )
        )
    except _TABLE_STORAGE_ERRORS as exc:
        raise RuntimeError(f"failed to initialize table dataset '{items_path}': {exc}") from exc


def load_preindex_storage(
    root_path: str,
    workspace: Workspace,
    *,
    thumb_size: int,
    thumb_quality: int,
    skip_dimension_probe: bool,
    preindex_signature: str | None = None,
) -> TableStorage | None:
    """Load a reusable preindex table.

    Returns `None` only when no compatible preindex payload is available.
    Unexpected validation/load/initialization failures raise instead of
    silently downgrading startup into a different storage mode.
    """
    paths = preindex_paths(workspace)
    if paths is None:
        return None
    meta = load_preindex_meta(paths.meta_path)
    if meta is None:
        return None
    expected_root = str(Path(root_path).resolve())
    meta_root = str(meta.get("root", "")).strip()
    if meta_root and meta_root != expected_root:
        print("[lenslet] Warning: preindex root mismatch; rebuilding.")
        return None
    signature = str(meta.get("signature", "")).strip()
    if preindex_signature:
        if signature != preindex_signature:
            print("[lenslet] Warning: preindex signature mismatch; rebuilding.")
            return None
    elif signature:
        try:
            entries = scan_local_images(Path(root_path))
            entries.sort(key=lambda entry: entry.rel_path)
            current = compute_signature(Path(root_path), entries)
        except _PREINDEX_SIGNATURE_ERRORS as exc:
            raise PreindexStartupError(f"failed to validate preindex signature: {exc}") from exc
        if current != signature:
            print("[lenslet] Warning: preindex signature mismatch; rebuilding.")
            return None
    try:
        table, _ = load_preindex_table(paths)
    except FileNotFoundError:
        return None
    except _PREINDEX_BUILD_ERRORS as exc:
        raise PreindexStartupError(f"failed to load preindex data: {exc}") from exc

    try:
        return TableStorage(
            table=table,
            options=TableStorageOptions(
                root=root_path,
                thumb_size=thumb_size,
                thumb_quality=thumb_quality,
                source_column=PREINDEX_SOURCE_COLUMN,
                path_column=PREINDEX_PATH_COLUMN,
                skip_dimension_probe=skip_dimension_probe,
            ),
        )
    except _TABLE_STORAGE_ERRORS as exc:
        raise PreindexStartupError(f"failed to initialize preindex storage: {exc}") from exc


def ensure_preindex_storage(
    root_path: str,
    workspace: Workspace,
    *,
    thumb_size: int,
    thumb_quality: int,
    skip_dimension_probe: bool,
    preindex_signature: str | None = None,
) -> tuple[TableStorage | None, Workspace, str | None]:
    """Return preindex storage when available.

    `storage is None` is reserved for the intentional "no local images" path.
    Any unexpected preindex bootstrap failure raises.
    """
    if preindex_signature:
        storage = load_preindex_storage(
            root_path,
            workspace,
            thumb_size=thumb_size,
            thumb_quality=thumb_quality,
            skip_dimension_probe=skip_dimension_probe,
            preindex_signature=preindex_signature,
        )
        if storage is not None:
            return storage, workspace, preindex_signature

    try:
        preindex_result = ensure_local_preindex(Path(root_path), workspace)
    except _PREINDEX_BUILD_ERRORS as exc:
        raise PreindexStartupError(f"preindex build failed: {exc}") from exc

    if preindex_result is None:
        return None, workspace, preindex_signature

    if preindex_result.workspace.root != workspace.root:
        workspace = preindex_result.workspace

    storage = load_preindex_storage(
        root_path,
        workspace,
        thumb_size=thumb_size,
        thumb_quality=thumb_quality,
        skip_dimension_probe=skip_dimension_probe,
        preindex_signature=preindex_result.signature,
    )
    if storage is None:
        raise PreindexStartupError("preindex build completed but produced no readable storage")
    return storage, workspace, preindex_result.signature


def refresh_preindex_storage(
    app: FastAPI,
    context: AppContext,
    *,
    path: str,
    root_path: str,
    browse_options: BrowseAppOptions,
    options: LocalAppOptions,
) -> dict[str, bool]:
    current_storage = context.storage
    try:
        preindex_storage, updated_workspace, _signature = ensure_preindex_storage(
            root_path,
            context.workspace,
            thumb_size=browse_options.thumb_size,
            thumb_quality=browse_options.thumb_quality,
            skip_dimension_probe=options.skip_dimension_probe,
        )
    except PreindexStartupError as exc:
        raise HTTPException(500, str(exc)) from exc
    if preindex_storage is None:
        raise HTTPException(500, "failed to rebuild preindex table")

    if isinstance(current_storage, TableStorage) and isinstance(preindex_storage, TableStorage):
        preindex_storage.replace_sidecars(
            current_storage.sidecar_snapshot_for_paths(preindex_storage.row_index_map().values())
        )
    if context.recursive_browse_cache is not None:
        context.recursive_browse_cache.invalidate_path(path)

    updated_runtime = context.runtime
    if (
        updated_workspace.root != context.workspace.root
        or updated_workspace.views_override != context.workspace.views_override
        or updated_workspace.can_write != context.workspace.can_write
    ):
        updated_runtime = runtime_for_workspace(
            context.runtime,
            updated_workspace,
            thumb_cache_enabled=browse_options.thumb_cache,
        )

    updated_context = set_runtime_context(
        app,
        BrowseAppContextInputs(
            storage=preindex_storage,
            workspace=updated_workspace,
            runtime=updated_runtime,
            storage_mode=context.storage_mode,
            storage_origin=context.storage_origin,
            indexing=context.indexing,
            og_preview=options.og_preview,
        ),
    )
    if updated_context.recursive_browse_cache is not None:
        updated_context.recursive_browse_cache.invalidate_path(path)
    return {"ok": True}


def _build_local_embedding_manager(
    startup: LocalStartupState,
    storage: BrowseAppStorage,
    workspace: Workspace,
    embedding_options: EmbeddingAppOptions,
) -> EmbeddingManager | None:
    if startup.storage_mode != "table" or not startup.table_parquet_path or not isinstance(storage, TableStorage):
        return None

    embedding_cache_store = embedding_cache_from_workspace(
        workspace,
        enabled=embedding_options.cache,
        cache_dir=embedding_options.cache_dir,
    )
    return build_embedding_manager(
        startup.table_parquet_path,
        storage,
        startup.embedding_detection,
        cache=embedding_cache_store,
        preload=embedding_options.preload,
    )


def create_local_app(
    root_path: str,
    *,
    options: LocalAppOptions | None = None,
    table_launch: TableLaunchResult | None = None,
) -> FastAPI:
    """Create a browse app for a local image directory or local items.parquet."""
    options = options or LocalAppOptions()
    browse_options = options.browse
    embedding_options = options.embedding

    app = create_api_app(description="Lightweight image gallery server")
    workspace = resolve_local_workspace(root_path, options)
    set_mutation_policy(
        app,
        mutation_policy_for_workspace(
            workspace,
            trusted_write_origins=options.trusted_write_origins,
        ),
    )
    startup = resolve_local_storage_startup(
        root_path,
        workspace,
        options=options,
        browse_options=browse_options,
        embedding_options=embedding_options,
        table_launch=table_launch,
    )
    storage = startup.storage
    workspace = startup.workspace

    runtime = initialize_runtime(
        app,
        storage=storage,
        workspace=workspace,
        thumb_cache=browse_options.thumb_cache,
        presence_view_ttl=browse_options.presence_view_ttl,
        presence_edit_ttl=browse_options.presence_edit_ttl,
        presence_prune_interval=browse_options.presence_prune_interval,
    )

    embedding_manager = _build_local_embedding_manager(startup, storage, workspace, embedding_options)
    indexing = initialize_local_indexing(
        storage,
        browse_options,
    )
    install_local_indexing_lifecycle(app, storage, indexing, warmup_errors=_INDEX_WARMUP_ERRORS)
    adapters = build_local_browse_adapters(
        app,
        root_path=root_path,
        browse_options=browse_options,
        options=options,
        record_update=build_record_update(app),
        refresh_preindex_storage=refresh_preindex_storage,
    )

    return finalize_browse_app(
        app,
        BrowseAppAssembly(
            context=BrowseAppContextInputs(
                storage=storage,
                workspace=workspace,
                runtime=runtime,
                indexing=indexing,
                storage_mode=startup.storage_mode,
                storage_origin=startup.storage_origin,
                og_preview=options.og_preview,
            ),
            adapters=adapters,
            embedding_manager=embedding_manager,
        ),
    )


def initialize_local_indexing(
    storage: BrowseAppStorage,
    browse_options: BrowseAppOptions,
) -> IndexingLifecycle:
    _ = storage
    indexing = IndexingLifecycle(scope="/")
    if browse_options.indexing_listener is not None:
        indexing.subscribe(browse_options.indexing_listener)
    return indexing


def install_local_indexing_lifecycle(
    app: FastAPI,
    storage: BrowseAppStorage,
    indexing: IndexingLifecycle,
    *,
    warmup_errors: IndexWarmupErrors,
) -> None:
    started = False

    def _start_indexing() -> None:
        nonlocal started
        if started:
            return
        started = True
        indexing.start(scope="/")
        _start_index_warmup(storage, indexing, warmup_errors=warmup_errors)

    register_lifecycle_handlers(app, startup=_start_indexing)


def _start_index_warmup(
    storage: BrowseAppStorage,
    indexing: IndexingLifecycle,
    *,
    warmup_errors: IndexWarmupErrors,
) -> None:
    def _warm_index() -> None:
        try:
            storage.load_index("/")
            indexing.mark_ready()
        except warmup_errors as exc:
            report_degraded_feature("index warmup", exc, detail=f"failed to build index: {exc}")
            indexing.mark_error(str(exc) or "failed to build index")

    threading.Thread(target=_warm_index, daemon=True).start()


def build_local_browse_adapters(
    app: FastAPI,
    *,
    root_path: str,
    browse_options: BrowseAppOptions,
    options: LocalAppOptions,
    record_update: RecordUpdateFn,
    refresh_preindex_storage: LocalPreindexRefreshFn,
) -> BrowseAppAdapters:
    def _to_item(storage: SidecarStateStorage, cached: Any) -> Any:
        sidecar_state = storage.get_sidecar_readonly(cached.path)
        return build_item_payload(
            cached,
            sidecar_state,
            categoricals=categoricals_for_cached_item(storage, cached),
        )

    def _health_payload(request: Request) -> HealthResponse:
        context = get_app_context(app)
        return _base_health_payload(
            request=request,
            mode=context.storage_mode,
            workspace_id=_workspace_id_for_root_path(root_path),
            storage_origin=context.storage_origin,
            storage=context.storage,
            workspace=context.workspace,
            runtime=context.runtime,
            recursive_browse_cache=context.recursive_browse_cache,
        ).model_copy(
            update={
                "root": root_path,
                "indexing": _indexing_health_payload(context.indexing, context.storage),
            }
        )

    def _register_refresh_routes(target_app: FastAPI) -> None:
        @target_app.post(
            "/refresh",
            response_model=RefreshResponse,
            response_model_exclude_none=True,
            responses={403: {"model": ErrorResponse}},
        )
        def refresh(request: Request, path: str = "/") -> dict[str, Any] | RefreshResponse | JSONResponse:
            context = get_request_context(request)
            if denied := deny_if_mutation_forbidden(request, writes_enabled=context.workspace.can_write):
                return denied
            if context.storage_mode == "table" and context.storage_origin != "preindex":
                return RefreshResponse(ok=True, note=REFRESH_NOTE_TABLE_STATIC)

            path = canonical_path(path)

            if context.storage_mode == "table":
                return refresh_preindex_storage(
                    target_app,
                    context,
                    path=path,
                    root_path=root_path,
                    browse_options=browse_options,
                    options=options,
                )

            try:
                context.storage.refresh_subtree(path, preserve_sidecars=True)
            except ValueError as exc:
                raise HTTPException(400, "invalid path") from exc
            except FileNotFoundError as exc:
                raise HTTPException(404, "folder not found") from exc
            if context.recursive_browse_cache is not None:
                context.recursive_browse_cache.invalidate_path(path)
            return RefreshResponse(ok=True)

    return BrowseAppAdapters(
        include_index_routes=True,
        to_item=_to_item,
        record_update=record_update,
        health_payload=_health_payload,
        register_refresh_routes=_register_refresh_routes,
    )
