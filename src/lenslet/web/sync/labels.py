from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypedDict

from .events import EventBroker, IdempotencyCache
from ..paths import canonical_path
from ...storage.sidecar_state import ensure_sidecar_fields
from ...storage.base import SidecarInventoryStorage, SidecarState
from ...workspace import Workspace, WorkspaceReadResult


class LabelPersistenceError(RuntimeError):
    """Raised when a label mutation cannot be durably recorded."""


@dataclass(frozen=True)
class LabelSyncLocks:
    sidecar: threading.Lock | None = None
    log: threading.Lock | None = None


class _PersistedSidecarRecordRequired(TypedDict):
    tags: list[str]
    notes: str
    star: int | None
    version: int
    updated_at: str
    updated_by: str


class PersistedSidecarRecord(_PersistedSidecarRecordRequired, total=False):
    metrics: dict[str, float]


class LabelsSnapshotPayload(TypedDict):
    version: int
    last_event_id: int
    items: dict[str, PersistedSidecarRecord]


@dataclass(frozen=True)
class SnapshotWriterOptions:
    min_interval: float = 5.0
    min_updates: int = 20
    compact_threshold_bytes: int = 5_000_000


class SnapshotWriter:
    def __init__(
        self,
        workspace: Workspace,
        *,
        locks: LabelSyncLocks | None = None,
        options: SnapshotWriterOptions | None = None,
    ) -> None:
        config = options or SnapshotWriterOptions()
        self._workspace = workspace
        self._min_interval = config.min_interval
        self._min_updates = config.min_updates
        self._last_write = 0.0
        self._since = 0
        self._lock = threading.Lock()
        self._locks = locks or LabelSyncLocks()
        self._compact_threshold = config.compact_threshold_bytes

    def maybe_write(self, storage: SidecarInventoryStorage, last_event_id: int) -> None:
        if not self._workspace.can_write:
            return
        now = time.monotonic()
        with self._lock:
            self._since += 1
            if self._since < self._min_updates and now - self._last_write < self._min_interval:
                return
            self._since = 0
            self._last_write = now
        self.flush(storage, last_event_id)

    def flush(self, storage: SidecarInventoryStorage, last_event_id: int) -> bool:
        if not self._workspace.can_write:
            return False
        with self._lock:
            self._since = 0
            self._last_write = time.monotonic()
        if self._locks.sidecar is None:
            payload = _build_snapshot_payload(storage, last_event_id)
        else:
            with self._locks.sidecar:
                payload = _build_snapshot_payload(storage, last_event_id)
        try:
            self._workspace.write_labels_snapshot(payload)
        except (OSError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
            print(f"[lenslet] Warning: failed to write labels snapshot: {exc}")
            return False
        if self._compact_threshold <= 0:
            return True
        try:
            if self._locks.log is None:
                self._workspace.compact_labels_log(last_event_id, max_bytes=self._compact_threshold)
            else:
                with self._locks.log:
                    self._workspace.compact_labels_log(last_event_id, max_bytes=self._compact_threshold)
        except (OSError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
            print(f"[lenslet] Warning: failed to compact labels log: {exc}")
            return False
        return True


def _build_snapshot_payload(storage: SidecarInventoryStorage, last_event_id: int) -> LabelsSnapshotPayload:
    items: dict[str, PersistedSidecarRecord] = {}
    for path, sidecar in list(storage.sidecar_items()):
        sidecar = ensure_sidecar_fields(sidecar)
        if not _should_persist_sidecar(sidecar):
            continue
        key = canonical_path(path)
        items[key] = _persistable_sidecar(sidecar)
    return {"version": 1, "last_event_id": last_event_id, "items": items}


def _should_persist_sidecar(sidecar: SidecarState) -> bool:
    if sidecar.get("version", 1) > 1:
        return True
    if sidecar.get("tags"):
        return True
    if sidecar.get("notes"):
        return True
    if sidecar.get("star") is not None:
        return True
    if sidecar.get("metrics"):
        return True
    return False


def _persistable_sidecar(sidecar: SidecarState) -> PersistedSidecarRecord:
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


def _apply_persisted_record(storage: SidecarInventoryStorage, path: str, record: Mapping[str, object]) -> bool:
    sidecar = storage.ensure_sidecar(path)
    sidecar = ensure_sidecar_fields(sidecar)
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
    if "updated_at" in record:
        updated_at = record.get("updated_at")
        sidecar["updated_at"] = updated_at if isinstance(updated_at, str) else ""
    if "updated_by" in record:
        updated_by = record.get("updated_by")
        sidecar["updated_by"] = updated_by if isinstance(updated_by, str) and updated_by else "server"
    storage.set_sidecar(path, sidecar)
    return True


def _coerce_tags(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _coerce_star(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
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
            metrics[key] = float(metric_value)
    return metrics


def _load_label_state(storage: SidecarInventoryStorage, workspace: Workspace) -> int:
    if not workspace.can_write:
        return 0
    max_event_id = 0
    last_snapshot_id = 0
    snapshot_result = workspace.read_labels_snapshot_result()
    _raise_for_workspace_state("labels snapshot", snapshot_result)
    snapshot = snapshot_result.value
    if isinstance(snapshot, dict):
        last_snapshot_id = snapshot.get("last_event_id", 0) or 0
        items = snapshot.get("items", {})
        if isinstance(items, dict):
            for raw_path, record in items.items():
                path = canonical_path(raw_path if isinstance(raw_path, str) else None)
                if isinstance(record, Mapping):
                    _apply_persisted_record(storage, path, record)
        if isinstance(last_snapshot_id, int):
            max_event_id = max(max_event_id, last_snapshot_id)
    log_result = workspace.read_labels_log_result()
    _raise_for_workspace_state("labels log", log_result)
    for entry in log_result.value:
        if not isinstance(entry, dict):
            continue
        event_id = entry.get("id", 0) or 0
        if isinstance(event_id, int) and event_id <= last_snapshot_id:
            continue
        if entry.get("type") not in ("item-updated", "metrics-updated") and "path" not in entry:
            continue
        raw_path = entry.get("path")
        path = canonical_path(raw_path if isinstance(raw_path, str) else None)
        _apply_persisted_record(storage, path, entry)
        if isinstance(event_id, int):
            max_event_id = max(max_event_id, event_id)
    return max_event_id


def _raise_for_workspace_state(
    label: str,
    result: WorkspaceReadResult[Any],
) -> None:
    if result.status in {"missing", "ok"}:
        return
    detail = result.detail or result.status
    raise RuntimeError(f"workspace {label} is unreadable: {detail}")


def init_sync_state(
    storage: SidecarInventoryStorage,
    workspace: Workspace,
    locks: LabelSyncLocks | None = None,
) -> tuple[EventBroker, IdempotencyCache, SnapshotWriter, int]:
    broker = EventBroker(buffer_size=500)
    max_event_id = _load_label_state(storage, workspace)
    if max_event_id:
        broker.set_next_id(max_event_id + 1)
    idempotency = IdempotencyCache(ttl_seconds=600)
    snapshotter = SnapshotWriter(workspace, locks=locks)
    return broker, idempotency, snapshotter, max_event_id
