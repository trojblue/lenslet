"""App-factory wiring for Lenslet server modes."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .embeddings.cache import EmbeddingCache
from .embeddings.config import EmbeddingConfig
from .embeddings.detect import columns_without_embeddings, detect_embeddings, EmbeddingDetection
from .embeddings.index import EmbeddingManager
from .server_browse import (
    _build_item,
    _create_hotpath_metrics,
    _labels_health_payload,
    _storage_from_request,
)
from .server_media import _thumb_worker_count
from .server_routes_common import RecordUpdateFn, register_common_api_routes as _register_common_api_routes
from .server_routes_embeddings import register_embedding_routes as _register_embedding_routes
from .server_routes_index import mount_frontend as _mount_frontend, register_index_routes as _register_index_routes
from .server_routes_og import register_og_routes as _register_og_routes
from .server_routes_presence import (
    install_presence_prune_loop as _install_presence_prune_loop,
    presence_runtime_payload as _presence_runtime_payload,
)
from .server_routes_views import register_views_routes as _register_views_routes
from .server_runtime import AppRuntime, build_app_runtime
from .server_sync import _canonical_path, _sidecar_payload
from .storage.dataset import DatasetStorage
from .storage.memory import MemoryStorage
from .storage.table import TableStorage, load_parquet_schema, load_parquet_table
from .thumb_cache import ThumbCache
from .workspace import Workspace


def _create_base_app(*, description: str) -> FastAPI:
    app = FastAPI(
        title="Lenslet",
        description=description,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app


def _attach_storage(app: FastAPI, storage) -> None:
    @app.middleware("http")
    async def attach_storage(request: Request, call_next):
        request.state.storage = storage
        return await call_next(request)


def _resolve_embedding_detection(
    parquet_path: str,
    embedding_config: EmbeddingConfig | None,
) -> EmbeddingDetection:
    config = embedding_config or EmbeddingConfig()
    try:
        schema = load_parquet_schema(parquet_path)
    except Exception as exc:
        print(f"[lenslet] Warning: failed to read embedding schema: {exc}")
        return EmbeddingDetection.empty()
    try:
        return detect_embeddings(schema, config)
    except Exception as exc:
        print(f"[lenslet] Warning: failed to detect embeddings: {exc}")
        return EmbeddingDetection.empty()


def _build_embedding_manager(
    parquet_path: str,
    storage: TableStorage,
    detection: EmbeddingDetection,
    cache: EmbeddingCache | None = None,
    preload: bool = False,
    prefer_faiss: bool = True,
) -> EmbeddingManager | None:
    if not parquet_path:
        return None
    try:
        manager = EmbeddingManager(
            parquet_path=parquet_path,
            detection=detection.available,
            rejected=detection.rejected,
            row_to_path=storage.row_index_map(),
            cache=cache,
            prefer_faiss=prefer_faiss,
        )
        if preload:
            manager.preload()
        return manager
    except Exception as exc:
        print(f"[lenslet] Warning: failed to initialize embeddings: {exc}")
        return None


def _build_record_update(
    storage,
    *,
    broker,
    workspace: Workspace,
    log_lock: threading.Lock,
    snapshotter,
    sync_state: dict[str, int],
) -> RecordUpdateFn:
    def _record_update(path: str, meta: dict, event_type: str = "item-updated") -> None:
        payload = _sidecar_payload(path, meta)
        event_id = broker.publish(event_type, payload)
        sync_state["last_event_id"] = event_id
        if workspace.can_write:
            entry = {"id": event_id, "type": event_type, **payload}
            try:
                with log_lock:
                    workspace.append_labels_log(entry)
            except Exception as exc:
                print(f"[lenslet] Warning: failed to append labels log: {exc}")
            snapshotter.maybe_write(storage, event_id)

    return _record_update


def _initialize_runtime(
    app: FastAPI,
    *,
    storage,
    workspace: Workspace,
    thumb_cache: bool,
    presence_view_ttl: float,
    presence_edit_ttl: float,
    presence_prune_interval: float,
    presence_lifecycle_v2: bool,
) -> AppRuntime:
    return build_app_runtime(
        app,
        storage=storage,
        workspace=workspace,
        presence_view_ttl=presence_view_ttl,
        presence_edit_ttl=presence_edit_ttl,
        presence_prune_interval=presence_prune_interval,
        presence_lifecycle_v2=presence_lifecycle_v2,
        thumb_cache_enabled=thumb_cache,
        thumb_worker_count=_thumb_worker_count(),
        build_thumb_cache=_thumb_cache_from_workspace,
        install_presence_prune_loop=_install_presence_prune_loop,
        build_hotpath_metrics=_create_hotpath_metrics,
    )


def _presence_health_payload(
    app: FastAPI,
    runtime: AppRuntime,
    *,
    lifecycle_v2_enabled: bool,
    prune_interval_fallback: float,
) -> dict[str, Any]:
    prune_interval = float(
        getattr(app.state, "presence_prune_interval", prune_interval_fallback),
    )
    return _presence_runtime_payload(
        presence=runtime.presence,
        broker=runtime.broker,
        metrics=runtime.presence_metrics,
        lifecycle_v2_enabled=lifecycle_v2_enabled,
        prune_interval_seconds=prune_interval,
    )


def _base_health_payload(
    app: FastAPI,
    *,
    mode: str,
    storage,
    workspace: Workspace,
    runtime: AppRuntime,
    lifecycle_v2_enabled: bool,
    prune_interval_fallback: float,
) -> dict[str, Any]:
    return {
        "ok": True,
        "mode": mode,
        "can_write": workspace.can_write,
        "labels": _labels_health_payload(workspace),
        "presence": _presence_health_payload(
            app,
            runtime,
            lifecycle_v2_enabled=lifecycle_v2_enabled,
            prune_interval_fallback=prune_interval_fallback,
        ),
        "hotpath": runtime.hotpath_metrics.snapshot(storage),
    }


def _register_common_routes(
    app: FastAPI,
    to_item,
    *,
    runtime: AppRuntime,
    lifecycle_v2_enabled: bool,
    record_update: RecordUpdateFn,
) -> None:
    _register_common_api_routes(
        app,
        to_item,
        meta_lock=runtime.meta_lock,
        presence=runtime.presence,
        broker=runtime.broker,
        lifecycle_v2_enabled=lifecycle_v2_enabled,
        presence_metrics=runtime.presence_metrics,
        idempotency_cache=runtime.idempotency_cache,
        record_update=record_update,
        thumb_queue=runtime.thumb_queue,
        thumb_cache=runtime.thumb_cache,
        hotpath_metrics=runtime.hotpath_metrics,
    )


def _register_static_refresh_route(app: FastAPI, note: str) -> None:
    @app.post("/refresh")
    def refresh(path: str = "/"):
        _ = path
        return {"ok": True, "note": note}


def _warn_dataset_embedding_search_unavailable(embedding_parquet_path: str | None) -> None:
    if not embedding_parquet_path:
        return
    print(
        "[lenslet] Warning: embedding search is unavailable in dataset mode; "
        "ignoring embedding_parquet_path",
    )


def create_app(
    root_path: str,
    thumb_size: int = 256,
    thumb_quality: int = 70,
    no_write: bool = False,
    source_column: str | None = None,
    skip_indexing: bool = False,
    thumb_cache: bool = True,
    og_preview: bool = False,
    embedding_config: EmbeddingConfig | None = None,
    embedding_cache: bool = True,
    embedding_cache_dir: str | None = None,
    embedding_preload: bool = False,
    presence_view_ttl: float = 75.0,
    presence_edit_ttl: float = 60.0,
    presence_prune_interval: float = 5.0,
    presence_lifecycle_v2: bool = True,
) -> FastAPI:
    """Create FastAPI app with in-memory storage."""

    app = _create_base_app(description="Lightweight image gallery server")

    # Create storage (prefer table dataset if present)
    items_path = Path(root_path) / "items.parquet"
    storage_mode = "memory"
    embedding_detection = EmbeddingDetection.empty()
    if items_path.is_file():
        columns = None
        try:
            schema = load_parquet_schema(str(items_path))
            embedding_detection = detect_embeddings(schema, embedding_config or EmbeddingConfig())
            columns = columns_without_embeddings(schema, embedding_detection)
        except Exception as exc:
            print(f"[lenslet] Warning: Failed to detect embeddings: {exc}")
        try:
            table = load_parquet_table(str(items_path), columns=columns)
            storage = TableStorage(
                table=table,
                root=root_path,
                thumb_size=thumb_size,
                thumb_quality=thumb_quality,
                source_column=source_column,
                skip_indexing=skip_indexing,
            )
            storage_mode = "table"
        except Exception as exc:
            print(f"[lenslet] Warning: Failed to load table dataset: {exc}")
            storage = MemoryStorage(
                root=root_path,
                thumb_size=thumb_size,
                thumb_quality=thumb_quality,
            )
            storage_mode = "memory"
    else:
        storage = MemoryStorage(
            root=root_path,
            thumb_size=thumb_size,
            thumb_quality=thumb_quality,
        )

    workspace = Workspace.for_dataset(root_path, can_write=not no_write)
    try:
        workspace.ensure()
    except Exception as exc:
        print(f"[lenslet] Warning: failed to initialize workspace: {exc}")
        workspace.can_write = False

    runtime = _initialize_runtime(
        app,
        storage=storage,
        workspace=workspace,
        thumb_cache=thumb_cache,
        presence_view_ttl=presence_view_ttl,
        presence_edit_ttl=presence_edit_ttl,
        presence_prune_interval=presence_prune_interval,
        presence_lifecycle_v2=presence_lifecycle_v2,
    )

    embedding_manager: EmbeddingManager | None = None
    if storage_mode == "table" and items_path.is_file() and isinstance(storage, TableStorage):
        embedding_cache_store = _embedding_cache_from_workspace(
            workspace,
            enabled=embedding_cache,
            cache_dir=embedding_cache_dir,
        )
        embedding_manager = _build_embedding_manager(
            str(items_path),
            storage,
            embedding_detection,
            cache=embedding_cache_store,
            preload=embedding_preload,
        )

    if hasattr(storage, "get_index"):

        def _warm_index() -> None:
            try:
                storage.get_index("/")  # type: ignore[call-arg]
            except Exception as exc:
                print(f"[lenslet] Warning: failed to build index: {exc}")

        threading.Thread(target=_warm_index, daemon=True).start()

    def _to_item(storage, cached):
        meta = storage.get_metadata(cached.path)
        return _build_item(cached, meta)

    record_update = _build_record_update(
        storage,
        broker=runtime.broker,
        workspace=workspace,
        log_lock=runtime.log_lock,
        snapshotter=runtime.snapshotter,
        sync_state=runtime.sync_state,
    )

    # Inject storage via middleware
    _attach_storage(app, storage)

    # --- Routes ---

    @app.get("/health")
    def health():
        return {
            **_base_health_payload(
                app,
                mode=storage_mode,
                storage=storage,
                workspace=workspace,
                runtime=runtime,
                lifecycle_v2_enabled=presence_lifecycle_v2,
                prune_interval_fallback=presence_prune_interval,
            ),
            "root": root_path,
        }

    @app.post("/refresh")
    def refresh(request: Request, path: str = "/"):
        if storage_mode != "memory":
            return {"ok": True, "note": f"{storage_mode} mode is static"}

        storage = _storage_from_request(request)
        path = _canonical_path(path)
        try:
            target = storage._abs_path(path)
        except ValueError:
            raise HTTPException(400, "invalid path")

        if not os.path.isdir(target):
            raise HTTPException(404, "folder not found")

        # Keep in-memory sidecar metadata so annotations survive refresh.
        storage.invalidate_subtree(path, clear_metadata=False)
        return {"ok": True}

    _register_common_routes(
        app,
        _to_item,
        runtime=runtime,
        lifecycle_v2_enabled=presence_lifecycle_v2,
        record_update=record_update,
    )

    _register_embedding_routes(app, storage, embedding_manager)
    _register_og_routes(app, storage, workspace, enabled=og_preview)
    _register_index_routes(app, storage, workspace, og_preview=og_preview)
    _register_views_routes(app, workspace)

    # Mount frontend if dist exists
    _mount_frontend(app)

    return app


def create_app_from_datasets(
    datasets: dict[str, list[str]],
    thumb_size: int = 256,
    thumb_quality: int = 70,
    show_source: bool = True,
    thumb_cache: bool = True,
    og_preview: bool = False,
    embedding_parquet_path: str | None = None,
    embedding_config: EmbeddingConfig | None = None,
    embedding_cache: bool = True,
    embedding_cache_dir: str | None = None,
    embedding_preload: bool = False,
    presence_view_ttl: float = 75.0,
    presence_edit_ttl: float = 60.0,
    presence_prune_interval: float = 5.0,
    presence_lifecycle_v2: bool = True,
) -> FastAPI:
    """Create FastAPI app with in-memory dataset storage."""

    app = _create_base_app(description="Lightweight image gallery server (dataset mode)")

    # Create dataset storage
    storage = DatasetStorage(
        datasets=datasets,
        thumb_size=thumb_size,
        thumb_quality=thumb_quality,
        include_source_in_search=show_source,
    )
    workspace = Workspace.for_dataset(None, can_write=False)
    runtime = _initialize_runtime(
        app,
        storage=storage,
        workspace=workspace,
        thumb_cache=thumb_cache,
        presence_view_ttl=presence_view_ttl,
        presence_edit_ttl=presence_edit_ttl,
        presence_prune_interval=presence_prune_interval,
        presence_lifecycle_v2=presence_lifecycle_v2,
    )
    _warn_dataset_embedding_search_unavailable(embedding_parquet_path)
    embedding_manager: EmbeddingManager | None = None

    def _to_item(storage: DatasetStorage, cached):
        meta = storage.get_metadata(cached.path)
        source = None
        if show_source:
            try:
                source = storage.get_source_path(cached.path)
            except Exception:
                source = None
        return _build_item(cached, meta, source=source)

    record_update = _build_record_update(
        storage,
        broker=runtime.broker,
        workspace=workspace,
        log_lock=runtime.log_lock,
        snapshotter=runtime.snapshotter,
        sync_state=runtime.sync_state,
    )

    # Inject storage via middleware
    _attach_storage(app, storage)

    # --- Routes ---

    @app.get("/health")
    def health():
        dataset_names = list(datasets.keys())
        total_images = sum(len(paths) for paths in datasets.values())
        return {
            **_base_health_payload(
                app,
                mode="dataset",
                storage=storage,
                workspace=workspace,
                runtime=runtime,
                lifecycle_v2_enabled=presence_lifecycle_v2,
                prune_interval_fallback=presence_prune_interval,
            ),
            "datasets": dataset_names,
            "total_images": total_images,
        }

    _register_static_refresh_route(app, note="dataset mode is static")

    _register_common_routes(
        app,
        _to_item,
        runtime=runtime,
        lifecycle_v2_enabled=presence_lifecycle_v2,
        record_update=record_update,
    )

    _register_embedding_routes(app, storage, embedding_manager)
    _register_views_routes(app, workspace)

    # Mount frontend if dist exists
    _mount_frontend(app)

    return app


def create_app_from_table(
    table: object,
    base_dir: str | None = None,
    thumb_size: int = 256,
    thumb_quality: int = 70,
    source_column: str | None = None,
    skip_indexing: bool = False,
    show_source: bool = True,
    allow_local: bool = True,
    og_preview: bool = False,
    workspace: Workspace | None = None,
    thumb_cache: bool = True,
    embedding_parquet_path: str | None = None,
    embedding_config: EmbeddingConfig | None = None,
    embedding_cache: bool = True,
    embedding_cache_dir: str | None = None,
    embedding_preload: bool = False,
    presence_view_ttl: float = 75.0,
    presence_edit_ttl: float = 60.0,
    presence_prune_interval: float = 5.0,
    presence_lifecycle_v2: bool = True,
) -> FastAPI:
    """Create FastAPI app with in-memory table storage."""
    storage = TableStorage(
        table=table,
        root=base_dir,
        thumb_size=thumb_size,
        thumb_quality=thumb_quality,
        source_column=source_column,
        skip_indexing=skip_indexing,
        allow_local=allow_local,
    )
    return create_app_from_storage(
        storage,
        show_source=show_source,
        og_preview=og_preview,
        workspace=workspace,
        thumb_cache=thumb_cache,
        embedding_parquet_path=embedding_parquet_path,
        embedding_config=embedding_config,
        embedding_cache=embedding_cache,
        embedding_cache_dir=embedding_cache_dir,
        embedding_preload=embedding_preload,
        presence_view_ttl=presence_view_ttl,
        presence_edit_ttl=presence_edit_ttl,
        presence_prune_interval=presence_prune_interval,
        presence_lifecycle_v2=presence_lifecycle_v2,
    )


def create_app_from_storage(
    storage: TableStorage,
    show_source: bool = True,
    og_preview: bool = False,
    workspace: Workspace | None = None,
    thumb_cache: bool = True,
    embedding_parquet_path: str | None = None,
    embedding_config: EmbeddingConfig | None = None,
    embedding_cache: bool = True,
    embedding_cache_dir: str | None = None,
    embedding_preload: bool = False,
    presence_view_ttl: float = 75.0,
    presence_edit_ttl: float = 60.0,
    presence_prune_interval: float = 5.0,
    presence_lifecycle_v2: bool = True,
) -> FastAPI:
    """Create FastAPI app using a pre-built TableStorage."""

    app = _create_base_app(description="Lightweight image gallery server (table mode)")

    if workspace is None:
        workspace = Workspace.for_dataset(None, can_write=False)
    runtime = _initialize_runtime(
        app,
        storage=storage,
        workspace=workspace,
        thumb_cache=thumb_cache,
        presence_view_ttl=presence_view_ttl,
        presence_edit_ttl=presence_edit_ttl,
        presence_prune_interval=presence_prune_interval,
        presence_lifecycle_v2=presence_lifecycle_v2,
    )
    embedding_manager: EmbeddingManager | None = None
    if embedding_parquet_path:
        detection = _resolve_embedding_detection(embedding_parquet_path, embedding_config)
        embed_cache = _embedding_cache_from_workspace(
            workspace,
            enabled=embedding_cache,
            cache_dir=embedding_cache_dir,
        )
        embedding_manager = _build_embedding_manager(
            embedding_parquet_path,
            storage,
            detection,
            cache=embed_cache,
            preload=embedding_preload,
        )

    def _to_item(storage: TableStorage, cached):
        meta = storage.get_metadata(cached.path)
        source = cached.source if show_source else None
        return _build_item(cached, meta, source=source)

    record_update = _build_record_update(
        storage,
        broker=runtime.broker,
        workspace=workspace,
        log_lock=runtime.log_lock,
        snapshotter=runtime.snapshotter,
        sync_state=runtime.sync_state,
    )

    _attach_storage(app, storage)

    @app.get("/health")
    def health():
        return {
            **_base_health_payload(
                app,
                mode="table",
                storage=storage,
                workspace=workspace,
                runtime=runtime,
                lifecycle_v2_enabled=presence_lifecycle_v2,
                prune_interval_fallback=presence_prune_interval,
            ),
            "total_images": len(storage._items),
        }

    _register_static_refresh_route(app, note="table mode is static")

    _register_common_routes(
        app,
        _to_item,
        runtime=runtime,
        lifecycle_v2_enabled=presence_lifecycle_v2,
        record_update=record_update,
    )

    _register_embedding_routes(app, storage, embedding_manager)
    _register_og_routes(app, storage, workspace, enabled=og_preview)
    _register_index_routes(app, storage, workspace, og_preview=og_preview)
    _register_views_routes(app, workspace)
    _mount_frontend(app)

    return app


def _thumb_cache_from_workspace(workspace: Workspace, enabled: bool) -> ThumbCache | None:
    if not enabled or not workspace.can_write:
        return None
    cache_dir = workspace.thumb_cache_dir()
    if cache_dir is None:
        return None
    return ThumbCache(cache_dir)


def _embedding_cache_from_workspace(
    workspace: Workspace,
    enabled: bool,
    cache_dir: str | None,
) -> EmbeddingCache | None:
    if not enabled or not workspace.can_write:
        return None
    if cache_dir:
        root = Path(cache_dir).expanduser()
        if root.name != "embeddings_cache":
            root = root / "embeddings_cache"
        return EmbeddingCache(root, allow_write=workspace.can_write)
    root = workspace.embedding_cache_dir()
    if root is None:
        return None
    return EmbeddingCache(root, allow_write=workspace.can_write)
