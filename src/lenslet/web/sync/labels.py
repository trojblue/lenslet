from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypedDict

from ...metrics import coerce_finite_metric_value
from ...storage.base import SidecarInventoryStorage, SidecarState
from ...storage.sidecar_state import ensure_sidecar_fields
from ...workspace import Workspace, WorkspaceReadResult
from ..paths import canonical_path
from .events import EventBroker, IdempotencyCache, IdempotencyPayload


class LabelPersistenceError(RuntimeError):
    """Raised when a label mutation cannot be admitted or made durable."""


class _PersistedSidecarRecordRequired(TypedDict):
    tags: list[str]
    notes: str
    star: int | None
    version: int
    updated_at: str
    updated_by: str


class PersistedSidecarRecord(_PersistedSidecarRecordRequired, total=False):
    metrics: dict[str, float]


class PersistedMutationResult(TypedDict):
    status: int
    payload: IdempotencyPayload


class LabelsSnapshotPayload(TypedDict):
    version: int
    last_event_id: int
    items: dict[str, PersistedSidecarRecord]
    mutations: dict[str, PersistedMutationResult]


@dataclass(frozen=True, slots=True)
class LoadedLabelState:
    last_event_id: int
    items: dict[str, PersistedSidecarRecord]
    mutations: dict[str, PersistedMutationResult]


@dataclass(frozen=True, slots=True)
class SnapshotWriterOptions:
    min_interval: float = 5.0
    min_updates: int = 20
    compact_threshold_bytes: int = 5_000_000


class SnapshotWriter:
    """Persist writer-owned durable state, never the live sidecar mapping."""

    def __init__(
        self,
        workspace: Workspace,
        *,
        options: SnapshotWriterOptions | None = None,
    ) -> None:
        config = options or SnapshotWriterOptions()
        self._workspace = workspace
        self._min_interval = config.min_interval
        self._min_updates = config.min_updates
        self._compact_threshold = config.compact_threshold_bytes
        self._last_write = 0.0
        self._since = 0
        self._lock = threading.Lock()

    def maybe_write(
        self,
        items: Mapping[str, PersistedSidecarRecord],
        mutations: Mapping[str, PersistedMutationResult],
        last_event_id: int,
        *,
        force: bool = False,
    ) -> bool:
        if not self._workspace.can_write:
            return False
        now = time.monotonic()
        with self._lock:
            self._since += 1
            if not force and self._since < self._min_updates and now - self._last_write < self._min_interval:
                return False
            self._since = 0
            self._last_write = now
        payload: LabelsSnapshotPayload = {
            "version": 2,
            "last_event_id": last_event_id,
            "items": {path: dict(record) for path, record in items.items()},
            "mutations": {
                key: {"status": result["status"], "payload": dict(result["payload"])}
                for key, result in mutations.items()
            },
        }
        try:
            self._workspace.write_labels_snapshot(payload)
            if self._compact_threshold > 0:
                self._workspace.compact_labels_log(
                    last_event_id,
                    max_bytes=self._compact_threshold,
                )
        except (OSError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
            print(f"[lenslet] Warning: failed to write labels snapshot: {exc}")
            return False
        return True


def persistable_sidecar(sidecar: SidecarState) -> PersistedSidecarRecord:
    sidecar = ensure_sidecar_fields(sidecar)
    payload: PersistedSidecarRecord = {
        "tags": _coerce_tags(sidecar.get("tags")),
        "notes": sidecar.get("notes", ""),
        "star": sidecar.get("star"),
        "version": sidecar.get("version", 1),
        "updated_at": sidecar.get("updated_at", ""),
        "updated_by": sidecar.get("updated_by", "server"),
    }
    metrics = _coerce_metrics(sidecar.get("metrics")) if "metrics" in sidecar else None
    if metrics is not None:
        payload["metrics"] = metrics
    return payload


def should_persist_sidecar(sidecar: SidecarState) -> bool:
    if sidecar.get("version", 1) > 1:
        return True
    if sidecar.get("tags") or sidecar.get("notes") or sidecar.get("star") is not None:
        return True
    return _coerce_metrics(sidecar.get("metrics")) is not None


def _apply_persisted_record(
    storage: SidecarInventoryStorage,
    path: str,
    record: Mapping[str, object],
) -> bool:
    sidecar = ensure_sidecar_fields(storage.ensure_sidecar(path))
    incoming_version = record.get("version", sidecar.get("version", 1))
    if not isinstance(incoming_version, int):
        incoming_version = sidecar.get("version", 1)
    if incoming_version <= sidecar.get("version", 1):
        return False
    if "tags" in record:
        sidecar["tags"] = _coerce_tags(record.get("tags"))
    if "notes" in record:
        notes = record.get("notes")
        sidecar["notes"] = notes if isinstance(notes, str) else ""
    if "star" in record:
        sidecar["star"] = _coerce_star(record.get("star"))
    if "metrics" in record:
        metrics = _coerce_metrics(record.get("metrics"))
        if metrics is not None:
            sidecar["metrics"] = metrics
    sidecar["version"] = incoming_version
    updated_at = record.get("updated_at")
    if isinstance(updated_at, str):
        sidecar["updated_at"] = updated_at
    updated_by = record.get("updated_by")
    if isinstance(updated_by, str) and updated_by:
        sidecar["updated_by"] = updated_by
    storage.set_sidecar(path, sidecar)
    return True


def _coerce_tags(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _coerce_star(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _coerce_metrics(value: object) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    metrics: dict[str, float] = {}
    for key, metric_value in value.items():
        if not isinstance(key, str) or isinstance(metric_value, bool):
            continue
        if isinstance(metric_value, (int, float)):
            coerced = coerce_finite_metric_value(metric_value)
            if coerced is not None:
                metrics[key] = coerced
    return metrics


def _coerce_persisted_record(record: Mapping[str, object]) -> PersistedSidecarRecord:
    payload: PersistedSidecarRecord = {
        "tags": _coerce_tags(record.get("tags")),
        "notes": record.get("notes") if isinstance(record.get("notes"), str) else "",
        "star": _coerce_star(record.get("star")),
        "version": record.get("version") if isinstance(record.get("version"), int) else 1,
        "updated_at": record.get("updated_at") if isinstance(record.get("updated_at"), str) else "",
        "updated_by": record.get("updated_by")
        if isinstance(record.get("updated_by"), str) and record.get("updated_by")
        else "server",
    }
    metrics = _coerce_metrics(record.get("metrics"))
    if metrics is not None:
        payload["metrics"] = metrics
    return payload


def coerce_durable_mutation_result(value: object) -> PersistedMutationResult | None:
    if not isinstance(value, Mapping):
        return None
    status = value.get("status")
    payload = value.get("payload")
    if not isinstance(status, int) or not isinstance(payload, dict):
        return None
    durable_payload = dict(payload)
    accepted_event = durable_payload.get("accepted_event")
    if isinstance(accepted_event, dict):
        durable_payload["persistence"] = "saved"
        durable_payload["durable_watermark"] = dict(accepted_event)
    return {"status": status, "payload": durable_payload}


def load_label_state(storage: SidecarInventoryStorage, workspace: Workspace) -> LoadedLabelState:
    max_event_id = 0
    last_snapshot_id = 0
    durable_items: dict[str, PersistedSidecarRecord] = {}
    durable_mutations: dict[str, PersistedMutationResult] = {}
    snapshot_result = workspace.read_labels_snapshot_result()
    _raise_for_workspace_state("labels snapshot", snapshot_result)
    snapshot = snapshot_result.value
    if isinstance(snapshot, dict):
        raw_snapshot_id = snapshot.get("last_event_id", 0)
        if isinstance(raw_snapshot_id, int):
            last_snapshot_id = raw_snapshot_id
            max_event_id = raw_snapshot_id
        items = snapshot.get("items", {})
        if isinstance(items, dict):
            for raw_path, record in items.items():
                path = canonical_path(raw_path if isinstance(raw_path, str) else None)
                if isinstance(record, Mapping):
                    _apply_persisted_record(storage, path, record)
                    durable_items[path] = _coerce_persisted_record(record)
        mutations = snapshot.get("mutations", {})
        if isinstance(mutations, dict):
            for key, value in mutations.items():
                result = coerce_durable_mutation_result(value)
                if isinstance(key, str) and result is not None:
                    durable_mutations[key] = result

    log_result = workspace.read_labels_log_result()
    _raise_for_workspace_state("labels log", log_result)
    for entry in log_result.value:
        event_id = entry.get("id", 0)
        if not isinstance(event_id, int):
            continue
        max_event_id = max(max_event_id, event_id)
        if event_id <= last_snapshot_id:
            continue
        raw_path = entry.get("path")
        path = canonical_path(raw_path if isinstance(raw_path, str) else None)
        if path and _apply_persisted_record(storage, path, entry):
            durable_items[path] = _coerce_persisted_record(entry)
        mutation_id = entry.get("mutation_id")
        mutation_result = coerce_durable_mutation_result(entry.get("mutation_result"))
        if isinstance(mutation_id, str) and mutation_result is not None:
            durable_mutations[mutation_id] = mutation_result
    return LoadedLabelState(max_event_id, durable_items, durable_mutations)


def _load_label_state(storage: SidecarInventoryStorage, workspace: Workspace) -> int:
    """Return the durable event watermark for focused workspace callers."""
    return load_label_state(storage, workspace).last_event_id


def _raise_for_workspace_state(label: str, result: WorkspaceReadResult[Any]) -> None:
    if result.status in {"missing", "ok", "recoverable_tail"}:
        return
    detail = result.detail or result.status
    raise RuntimeError(f"workspace {label} is unreadable: {detail}")


def init_sync_state(
    storage: SidecarInventoryStorage,
    workspace: Workspace,
) -> tuple[EventBroker, IdempotencyCache, LoadedLabelState]:
    loaded = load_label_state(storage, workspace)
    broker = EventBroker(buffer_size=500)
    broker.set_next_id(loaded.last_event_id + 1)
    idempotency = IdempotencyCache(ttl_seconds=600, max_entries=10_000)
    idempotency.seed(loaded.mutations)
    return broker, idempotency, loaded
