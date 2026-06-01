"""Shared app assembly helpers for Lenslet browse modes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI
from pyarrow.lib import ArrowException

from ...degraded import report_degraded_feature
from ...embeddings.cache import EmbeddingCache
from ...embeddings.config import EmbeddingConfig
from ...embeddings.detect import EmbeddingDetection, detect_embeddings
from ...embeddings.index import EmbeddingManager
from ...storage.base import BrowseAppStorage, SidecarState
from ...storage.table.storage import TableStorage, load_parquet_schema
from ...workspace import Workspace
from ..auth import MutationPolicy, READ_ONLY_MUTATION_POLICY, trusted_local_mutation_policy
from ..cache.thumbs import ThumbCache
from ..context import get_app_context
from ..hotpath import build_hotpath_metrics
from ..media import thumb_worker_count
from ..models import RefreshResponse
from ..record_update import RecordUpdateFn
from ..runtime import (
    AppRuntime,
    AppRuntimeAssembly,
    AppRuntimeHooks,
    AppRuntimeSettings,
    build_app_runtime,
)
from ..sidecars import sidecar_payload
from ..sync.events import SyncEventName
from ..sync.labels import LabelPersistenceError, LabelSyncLocks, SnapshotWriter

_BYTES_PER_MIB = 1024 * 1024
DEFAULT_THUMB_CACHE_CAP_BYTES = 200 * _BYTES_PER_MIB

_PARQUET_SCHEMA_ERRORS = (ArrowException, ImportError, OSError, ValueError)
_EMBEDDING_DETECTION_ERRORS = (ArrowException, AttributeError, TypeError, ValueError)
_EMBEDDING_MANAGER_ERRORS = (AttributeError, ImportError, OSError, TypeError, ValueError)
_LABEL_LOG_ERRORS = (OSError, TypeError, ValueError)


def mutation_policy_for_workspace(
    workspace: Workspace,
    *,
    trusted_write_origins: tuple[str, ...] = (),
) -> MutationPolicy:
    if not workspace.can_write or not trusted_write_origins:
        return READ_ONLY_MUTATION_POLICY
    return trusted_local_mutation_policy(trusted_write_origins)


def resolve_embedding_detection(
    parquet_path: str,
    embedding_config: EmbeddingConfig | None,
) -> EmbeddingDetection:
    config = embedding_config or EmbeddingConfig()
    try:
        schema = load_parquet_schema(parquet_path)
    except _PARQUET_SCHEMA_ERRORS as exc:
        report_degraded_feature("embedding detection", exc, detail=f"failed to read schema: {exc}")
        return EmbeddingDetection.empty()
    try:
        return detect_embeddings(schema, config)
    except _EMBEDDING_DETECTION_ERRORS as exc:
        report_degraded_feature("embedding detection", exc, detail=f"failed to detect embeddings: {exc}")
        return EmbeddingDetection.empty()


def build_embedding_manager(
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
    except _EMBEDDING_MANAGER_ERRORS as exc:
        report_degraded_feature("embedding search", exc, detail=f"failed to initialize: {exc}")
        return None


def build_record_update(
    app: FastAPI,
) -> RecordUpdateFn:
    def _record_update(
        path: str,
        sidecar_state: SidecarState,
        event_type: SyncEventName,
        commit: Callable[[], None],
    ) -> int:
        context = get_app_context(app)
        workspace = context.workspace
        runtime = context.runtime
        payload = sidecar_payload(path, sidecar_state)

        def _commit_with_log(event_id: int) -> None:
            if workspace.can_write:
                entry = {"id": event_id, "type": event_type, **payload}
                try:
                    with runtime.log_lock:
                        workspace.append_labels_log(entry)
                except _LABEL_LOG_ERRORS as exc:
                    report_degraded_feature(
                        "label log persistence",
                        exc,
                        detail=f"failed to append labels event {event_id}: {exc}",
                        impact="mutation rejected before publishing",
                    )
                    raise LabelPersistenceError("failed to persist label update") from exc
            commit()

        event_id = runtime.broker.publish_after_commit(event_type, payload, _commit_with_log)
        runtime.sync_state["last_event_id"] = event_id
        return event_id

    return _record_update


def runtime_for_workspace(
    runtime: AppRuntime,
    workspace: Workspace,
    *,
    thumb_cache_enabled: bool,
) -> AppRuntime:
    return replace(
        runtime,
        snapshotter=SnapshotWriter(
            workspace,
            locks=LabelSyncLocks(sidecar=runtime.sidecar_lock, log=runtime.log_lock),
        ),
        thumb_cache=thumb_cache_from_workspace(workspace, thumb_cache_enabled),
    )


def initialize_runtime(
    app: FastAPI,
    *,
    storage: BrowseAppStorage,
    workspace: Workspace,
    thumb_cache: bool,
    presence_view_ttl: float,
    presence_edit_ttl: float,
    presence_prune_interval: float,
) -> AppRuntime:
    return build_app_runtime(
        app,
        AppRuntimeAssembly(
            storage=storage,
            workspace=workspace,
            settings=AppRuntimeSettings(
                presence_view_ttl=presence_view_ttl,
                presence_edit_ttl=presence_edit_ttl,
                presence_prune_interval=presence_prune_interval,
                thumb_cache_enabled=thumb_cache,
                thumb_worker_count=thumb_worker_count(),
            ),
            hooks=AppRuntimeHooks(
                build_thumb_cache=thumb_cache_from_workspace,
                build_hotpath_metrics=build_hotpath_metrics,
            ),
        ),
    )


def register_static_refresh_route(app: FastAPI, note: str) -> None:
    @app.post("/refresh", response_model=RefreshResponse, response_model_exclude_none=True)
    def refresh(path: str = "/") -> RefreshResponse:
        _ = path
        return RefreshResponse(ok=True, note=note)


def thumb_cache_from_workspace(workspace: Workspace, enabled: bool) -> ThumbCache | None:
    if not enabled or not workspace.can_write:
        return None
    cache_dir = workspace.thumb_cache_dir()
    if cache_dir is None:
        return None
    return ThumbCache(cache_dir, max_disk_bytes=DEFAULT_THUMB_CACHE_CAP_BYTES)


def embedding_cache_from_workspace(
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
