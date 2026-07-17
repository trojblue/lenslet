from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from fastapi import Request

from ...indexing_status import IndexingLifecycle, coerce_progress_count
from ...storage.base import BrowseGenerationStorage, BrowseStorage, IndexingProgressStorage
from ...storage.dataset.storage import DatasetStorage
from ...storage.table.storage import TableStorage
from ...workspace import Workspace
from ..auth import TRUSTED_LOCAL_MUTATION_DENIAL_MESSAGE, request_can_mutate
from ..cache.browse import RecursiveBrowseCache
from .options import StorageMode, StorageRefreshMode
from ..generation import build_browse_generation_token
from ..models import (
    MAX_EXPORT_COMPARISON_PATHS_V2,
    MAX_EXPORT_COMPARISON_PATHS_V2_GIF,
    BrowseCacheHealthPayload,
    CompareExportHealthPayload,
    HealthResponse,
    HotpathHealthPayload,
    IndexingHealthPayload,
    LabelsHealthPayload,
    PresenceHealthPayload,
    RefreshStatusPayload,
    TableDimensionCoveragePayload,
    TableLaunchStatusPayload,
    TableSkippedRowsPayload,
    LaunchSessionPayload,
)
from ..presence_runtime import presence_runtime_payload
from ..runtime import AppRuntime

REFRESH_NOTE_DATASET_STATIC = "dataset mode is static"
REFRESH_NOTE_TABLE_STATIC = "table mode is static"
REFRESH_NOTE_PREINDEX_NO_WRITE = "preindex refresh disabled (no-write workspace)"


def _presence_health_payload(runtime: AppRuntime) -> PresenceHealthPayload:
    return PresenceHealthPayload.model_validate(
        presence_runtime_payload(
            presence=runtime.presence,
            broker=runtime.broker,
            metrics=runtime.presence_metrics,
            prune_interval_seconds=runtime.presence_prune_interval,
        )
    )


def _labels_health_payload(workspace: Workspace, *, writes_enabled: bool | None = None) -> LabelsHealthPayload:
    if writes_enabled is None:
        writes_enabled = workspace.can_write
    if not writes_enabled:
        return LabelsHealthPayload(enabled=False)
    return LabelsHealthPayload(
        enabled=True,
        log=str(workspace.labels_log_path()),
        snapshot=str(workspace.labels_snapshot_path()),
    )


def _base_health_payload(
    *,
    request: Request,
    mode: StorageMode,
    workspace_id: str | None,
    storage_origin: str | None,
    storage: BrowseStorage,
    workspace: Workspace,
    runtime: AppRuntime,
    recursive_browse_cache: RecursiveBrowseCache | None,
    launch_session: LaunchSessionPayload | None = None,
    refresh_mode: StorageRefreshMode | Literal["default"] = "default",
    static_refresh_note: str | None = None,
) -> HealthResponse:
    writes_enabled = request_can_mutate(request, writes_enabled=workspace.can_write)
    hotpath = runtime.hotpath_metrics.snapshot(storage)
    hotpath = hotpath.model_copy(update={
        "counters": {
            **hotpath.counters,
            **runtime.query_coordinator.diagnostics(),
        },
    })
    return HealthResponse(
        ok=True,
        mode=mode,
        can_write=writes_enabled,
        workspace_id=workspace_id,
        storage_origin=storage_origin,
        refresh=_refresh_health_payload(
            mode=mode,
            storage_origin=storage_origin,
            writes_enabled=writes_enabled,
            refresh_mode=refresh_mode,
            static_refresh_note=static_refresh_note,
        ),
        browse_cache=_browse_cache_health_payload(recursive_browse_cache),
        compare_export=_compare_export_health_payload(),
        labels=_labels_health_payload(workspace, writes_enabled=writes_enabled),
        presence=_presence_health_payload(runtime),
        hotpath=hotpath,
        table_launch_status=_table_launch_status_payload(storage, workspace),
        launch_session=launch_session,
    )


def _opaque_workspace_id(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


def _workspace_id_for_root_path(root_path: str) -> str:
    return _opaque_workspace_id(f"browse-root:{Path(root_path).resolve()}")


def _workspace_id_for_dataset_storage(storage: DatasetStorage) -> str:
    return _opaque_workspace_id(f"dataset-signature:{storage.browse_cache_signature()}")


def _workspace_id_for_table_storage(storage: TableStorage, workspace: Workspace) -> str:
    if workspace.views_path is not None:
        return _opaque_workspace_id(f"table-views-path:{workspace.views_path.resolve()}")
    if storage.root:
        return _opaque_workspace_id(
            f"table-root:{Path(storage.root).resolve()}|signature:{storage.browse_cache_signature()}",
        )
    return _opaque_workspace_id(f"table-signature:{storage.browse_cache_signature()}")


def _workspace_id_for_browse_storage(storage: BrowseStorage, workspace: Workspace) -> str:
    if isinstance(storage, TableStorage):
        return _workspace_id_for_table_storage(storage, workspace)
    if isinstance(storage, DatasetStorage):
        return _workspace_id_for_dataset_storage(storage)
    signature = storage.browse_cache_signature()
    root = getattr(storage, "root", None)
    if root:
        return _opaque_workspace_id(f"storage-root:{Path(root).resolve()}|signature:{signature}")
    if workspace.views_path is not None:
        return _opaque_workspace_id(f"storage-views-path:{workspace.views_path.resolve()}")
    return _opaque_workspace_id(f"storage-signature:{signature}")


def _workspace_mode(workspace: Workspace) -> str:
    if not workspace.can_write:
        return "read-only"
    if workspace.is_temp_workspace():
        return "temp"
    if workspace.views_override is not None:
        return "parquet-sidecar"
    if workspace.root is not None:
        return "workspace"
    return "memory"


def _redacted_table_base_dir(base_dir: str | None) -> str | None:
    if not base_dir:
        return None
    return "[local path]"


def _table_launch_status_payload(
    storage: BrowseStorage,
    workspace: Workspace,
) -> TableLaunchStatusPayload | None:
    status_fn = getattr(storage, "table_launch_status", None)
    if not callable(status_fn):
        return None
    status = status_fn(workspace_mode=_workspace_mode(workspace))
    skipped = status.skipped_rows
    coverage = status.dimension_coverage
    return TableLaunchStatusPayload(
        source_column=status.source_column,
        path_column=status.path_column,
        path_mode=status.path_mode,
        root_policy=status.root_policy,
        base_dir=_redacted_table_base_dir(status.base_dir),
        workspace_mode=status.workspace_mode,
        source_table_rows=status.source_table_rows,
        gallery_rows=status.gallery_rows,
        skipped_rows=TableSkippedRowsPayload(
            total=skipped.total,
            local_disabled=skipped.local_disabled,
            local_outside_root=skipped.local_outside_root,
            local_resolved_outside_root=skipped.local_resolved_outside_root,
            local_missing=skipped.local_missing,
            other=skipped.other,
        ),
        media_source_kind=status.media_source_kind,
        dimension_coverage=TableDimensionCoveragePayload(
            known=coverage.known,
            missing=coverage.missing,
            total=coverage.total,
        ),
        dimension_cache_policy=status.dimension_cache_policy,
        dimension_write_policy=status.dimension_write_policy,
        original_media_policy=status.original_media_policy.to_payload(),
        warnings=list(status.warnings),
    )


def _refresh_health_payload(
    *,
    mode: StorageMode,
    storage_origin: str | None,
    writes_enabled: bool,
    refresh_mode: StorageRefreshMode | Literal["default"] = "default",
    static_refresh_note: str | None = None,
) -> RefreshStatusPayload:
    if refresh_mode == "static":
        return RefreshStatusPayload(enabled=False, note=static_refresh_note or "storage mode is static")
    if refresh_mode == "subtree":
        if not writes_enabled:
            return RefreshStatusPayload(enabled=False, note=TRUSTED_LOCAL_MUTATION_DENIAL_MESSAGE)
        return RefreshStatusPayload(enabled=True)
    if mode == "dataset":
        return RefreshStatusPayload(enabled=False, note=REFRESH_NOTE_DATASET_STATIC)
    if mode == "table":
        if storage_origin != "preindex":
            return RefreshStatusPayload(enabled=False, note=REFRESH_NOTE_TABLE_STATIC)
        if not writes_enabled:
            return RefreshStatusPayload(enabled=False, note=REFRESH_NOTE_PREINDEX_NO_WRITE)
    if not writes_enabled:
        return RefreshStatusPayload(enabled=False, note=TRUSTED_LOCAL_MUTATION_DENIAL_MESSAGE)
    return RefreshStatusPayload(enabled=True)


def _compare_export_health_payload() -> CompareExportHealthPayload:
    return CompareExportHealthPayload(
        supported_versions=[2],
        max_paths_v2=MAX_EXPORT_COMPARISON_PATHS_V2,
        max_paths_v2_gif=MAX_EXPORT_COMPARISON_PATHS_V2_GIF,
    )


def _browse_cache_health_payload(cache: RecursiveBrowseCache | None) -> BrowseCacheHealthPayload:
    if cache is None:
        return BrowseCacheHealthPayload(
            enabled=False,
            persisted=False,
            max_bytes=0,
            pending_warms=0,
        )
    return BrowseCacheHealthPayload(
        enabled=True,
        persisted=cache.persistence_enabled,
        path=str(cache.cache_dir) if cache.cache_dir is not None else None,
        max_bytes=cache.max_disk_bytes,
        pending_warms=cache.pending_warm_count(),
    )


def _storage_indexing_progress(storage: IndexingProgressStorage) -> tuple[int | None, int | None]:
    try:
        snapshot = storage.indexing_progress()
    except Exception:
        return None, None
    if not isinstance(snapshot, dict):
        return None, None
    done = coerce_progress_count(snapshot.get("done"))
    total = coerce_progress_count(snapshot.get("total"))
    if done is not None and total is not None and done > total:
        done = total
    return done, total


def _indexing_health_payload(
    indexing: IndexingLifecycle,
    storage: IndexingProgressStorage | BrowseGenerationStorage,
) -> IndexingHealthPayload:
    done, total = _storage_indexing_progress(storage)
    payload = indexing.snapshot(done=done, total=total)
    if payload.get("state") == "error" and isinstance(payload.get("error"), str):
        payload["error"] = "failed to build index"
    payload["generation"] = build_browse_generation_token(storage)
    return IndexingHealthPayload.model_validate(payload)
