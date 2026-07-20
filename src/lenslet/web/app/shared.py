"""Shared app assembly helpers for Lenslet browse modes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from fastapi import FastAPI
from pyarrow.lib import ArrowException

from ...degraded import report_degraded_feature
from ...diagnostics import request_phase
from ...embeddings.cache import EmbeddingCache
from ...embeddings.config import EmbeddingConfig
from ...embeddings.detect import EmbeddingDetection, detect_embeddings
from ...embeddings.index import EmbeddingManager
from ...storage.base import BrowseAppStorage, SidecarState
from ...storage.table.storage import TableStorage, load_parquet_schema
from ...workspace import Workspace
from ..auth import (
    MutationPolicy,
    PUBLIC_WRITE_MUTATION_POLICY,
    READ_ONLY_MUTATION_POLICY,
    trusted_local_mutation_policy,
)
from ..cache.thumbs import ThumbCache
from ..context import get_app_context
from ..hotpath import build_hotpath_metrics
from ..lifecycle import register_lifecycle_handlers
from ..media import thumb_worker_count
from ..models import RefreshResponse
from ..record_update import RecordUpdateFn, RecordUpdateResult
from ..runtime import (
    AppRuntime,
    AppRuntimeAssembly,
    AppRuntimeHooks,
    AppRuntimeSettings,
    build_app_runtime,
)
from ..sidecars import sidecar_payload
from ..sync.events import IdempotencyCache, SyncEventName
from ..sync.labels import (
    LabelPersistenceError,
    LoadedLabelState,
    load_label_state,
    persistable_sidecar,
    should_persist_sidecar,
)
from ..sync.persistence import LabelWriteBuffer

_BYTES_PER_MIB = 1024 * 1024
DEFAULT_THUMB_CACHE_CAP_BYTES = 200 * _BYTES_PER_MIB

_PARQUET_SCHEMA_ERRORS = (ArrowException, ImportError, OSError, ValueError)
_EMBEDDING_DETECTION_ERRORS = (ArrowException, AttributeError, TypeError, ValueError)
_EMBEDDING_MANAGER_ERRORS = (AttributeError, ImportError, OSError, TypeError, ValueError)


def mutation_policy_for_workspace(
    workspace: Workspace,
    *,
    trusted_write_origins: tuple[str, ...] = (),
    allow_remote_writes: bool = False,
) -> MutationPolicy:
    if not workspace.can_write:
        return READ_ONLY_MUTATION_POLICY
    if allow_remote_writes:
        return PUBLIC_WRITE_MUTATION_POLICY
    if not trusted_write_origins:
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
            source_guard=storage.ensure_source_current,
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
        *,
        mutation_id: str | None = None,
        changed_fields: tuple[str, ...] = (),
        mutation_sidecar_payload: dict | None = None,
    ) -> RecordUpdateResult:
        context = get_app_context(app)
        runtime = context.runtime
        payload = sidecar_payload(path, sidecar_state)
        if mutation_id is not None:
            payload["mutation_id"] = mutation_id
        payload["changed_fields"] = list(changed_fields)
        event_id = runtime.broker.reserve()
        accepted_event = runtime.label_writer.accepted_identity(event_id)
        persistence = runtime.label_writer.status()
        mutation_payload = {
            "sidecar": dict(mutation_sidecar_payload or {}),
            "mutation_id": mutation_id or f"event:{event_id}",
            "accepted_event": dict(accepted_event),
            "persistence": "pending",
            "durable_watermark": dict(persistence["durable_watermark"]),
        }
        payload.update(
            {
                "accepted_event": dict(accepted_event),
                "persistence": "pending",
                "durable_watermark": dict(persistence["durable_watermark"]),
            }
        )
        entry = {
            "id": event_id,
            "type": event_type,
            **payload,
            "mutation_result": {"status": 200, "payload": mutation_payload},
        }
        try:
            with request_phase("writer"):
                runtime.label_writer.accept(entry)
        except LabelPersistenceError:
            runtime.broker.cancel_reserved(event_id)
            raise
        try:
            commit()
            runtime.label_writer.mark_ready(event_id)
        except BaseException:
            runtime.label_writer.cancel(event_id)
            runtime.broker.cancel_reserved(event_id)
            raise
        runtime.broker.publish_reserved(event_id, event_type, payload)
        return RecordUpdateResult(
            event_id=event_id,
            accepted_event=accepted_event,
            persistence=runtime.label_writer.status(),
            mutation_payload=mutation_payload,
        )

    return _record_update


def runtime_for_workspace(
    app: FastAPI,
    runtime: AppRuntime,
    workspace: Workspace,
    storage: BrowseAppStorage,
    *,
    thumb_cache_enabled: bool,
) -> AppRuntime:
    runtime.label_writer.flush_all()
    loaded = load_label_state(storage, workspace)
    migrated_items = {
        path: persistable_sidecar(sidecar)
        for path, sidecar in storage.sidecar_items()
        if should_persist_sidecar(sidecar)
    }
    loaded = LoadedLabelState(
        last_event_id=loaded.last_event_id,
        items=migrated_items,
        mutations=loaded.mutations,
    )
    idempotency_cache = IdempotencyCache(ttl_seconds=600, max_entries=10_000)
    idempotency_cache.seed(loaded.mutations)
    label_writer = LabelWriteBuffer(
        workspace,
        loaded,
        broker=runtime.broker,
        idempotency_cache=idempotency_cache,
    )
    runtime.broker.set_next_id(loaded.last_event_id + 1)
    label_writer.persist_state()
    label_writer.start()
    register_lifecycle_handlers(app, shutdown=label_writer.close)
    return replace(
        runtime,
        idempotency_cache=idempotency_cache,
        label_writer=label_writer,
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
