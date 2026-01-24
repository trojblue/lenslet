from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

from fastapi import Request

from .server_models import Sidecar, SidecarPatch
from .workspace import Workspace


def _canonical_path(path: str | None) -> str:
    p = (path or "").replace("\\", "/").strip()
    if not p:
        return "/"
    while "//" in p:
        p = p.replace("//", "/")
    p = "/" + p.lstrip("/")
    if p != "/":
        p = p.rstrip("/")
    return p


def _gallery_id_from_path(path: str) -> str:
    path = _canonical_path(path)
    if path == "/":
        return "/"
    if "/" not in path[1:]:
        return "/"
    return path.rsplit("/", 1)[0] or "/"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_if_match(value: str | None) -> int | None:
    if not value:
        return None
    cleaned = value.strip()
    if cleaned.startswith("W/"):
        cleaned = cleaned[2:]
    cleaned = cleaned.strip('"')
    try:
        return int(cleaned)
    except (TypeError, ValueError):
        return None


def _parse_event_id(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _last_event_id_from_request(request: Request) -> int | None:
    header_id = _parse_event_id(request.headers.get("Last-Event-ID"))
    query_raw = request.query_params.get("last_event_id") or request.query_params.get("lastEventId")
    query_id = _parse_event_id(query_raw)
    if query_id is None:
        return header_id
    if header_id is None:
        return query_id
    return max(header_id, query_id)


def _normalize_tags(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        if not isinstance(raw, str):
            continue
        val = raw.strip()
        if not val or val in seen:
            continue
        seen.add(val)
        out.append(val)
    return out


def _ensure_meta_fields(meta: dict) -> dict:
    if "tags" not in meta or not isinstance(meta.get("tags"), list):
        meta["tags"] = []
    if "notes" not in meta or not isinstance(meta.get("notes"), str):
        meta["notes"] = ""
    if "star" not in meta:
        meta["star"] = None
    if "version" not in meta or not isinstance(meta.get("version"), int):
        meta["version"] = 1
    if "updated_at" not in meta or not isinstance(meta.get("updated_at"), str):
        meta["updated_at"] = ""
    if "updated_by" not in meta or not isinstance(meta.get("updated_by"), str):
        meta["updated_by"] = "server"
    return meta


def _sidecar_from_meta(meta: dict) -> Sidecar:
    meta = _ensure_meta_fields(meta)
    return Sidecar(
        tags=list(meta.get("tags", [])),
        notes=meta.get("notes", ""),
        exif={"width": meta.get("width", 0), "height": meta.get("height", 0)},
        star=meta.get("star"),
        version=meta.get("version", 1),
        updated_at=meta.get("updated_at", ""),
        updated_by=meta.get("updated_by", "server"),
    )


def _sidecar_payload(path: str, meta: dict) -> dict[str, Any]:
    meta = _ensure_meta_fields(meta)
    payload: dict[str, Any] = {
        "path": _canonical_path(path),
        "version": meta.get("version", 1),
        "tags": list(meta.get("tags", [])),
        "notes": meta.get("notes", ""),
        "star": meta.get("star"),
        "updated_at": meta.get("updated_at", ""),
        "updated_by": meta.get("updated_by", "server"),
    }
    if "metrics" in meta:
        payload["metrics"] = meta.get("metrics")
    return payload


def _format_sse(record: dict[str, Any]) -> str:
    data = json.dumps(record.get("data", {}), separators=(",", ":"))
    return f"event: {record.get('event','message')}\nid: {record.get('id','')}\ndata: {data}\n\n"


class EventBroker:
    def __init__(self, buffer_size: int = 500) -> None:
        self._buffer = deque(maxlen=buffer_size)
        self._next_id = 1
        self._clients: set[asyncio.Queue] = set()
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def ensure_loop(self) -> None:
        if self._loop is not None:
            return
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

    def set_next_id(self, next_id: int) -> None:
        with self._lock:
            self._next_id = max(self._next_id, next_id)

    def publish(self, event: str, data: dict[str, Any]) -> int:
        with self._lock:
            event_id = self._next_id
            self._next_id += 1
            record = {"id": event_id, "event": event, "data": data}
            self._buffer.append(record)
            loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._broadcast, record)
        return event_id

    def _broadcast(self, record: dict[str, Any]) -> None:
        for queue in list(self._clients):
            try:
                queue.put_nowait(record)
            except asyncio.QueueFull:
                continue

    def register(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        with self._lock:
            self._clients.add(queue)
        return queue

    def unregister(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._clients.discard(queue)

    def replay(self, last_id: int | None) -> list[dict[str, Any]]:
        if last_id is None:
            return []
        with self._lock:
            return [item for item in self._buffer if item.get("id", 0) > last_id]


class PresenceTracker:
    def __init__(self, view_ttl: float = 75.0, edit_ttl: float = 60.0) -> None:
        self._view_ttl = view_ttl
        self._edit_ttl = edit_ttl
        self._lock = threading.Lock()
        self._entries: dict[str, dict[str, dict[str, float]]] = {}

    def _counts_locked(self, gallery_id: str, now: float) -> tuple[int, int]:
        entries = self._entries.get(gallery_id, {})
        viewing = 0
        editing = 0
        stale: list[str] = []
        for client_id, record in entries.items():
            last_view = record.get("view", 0.0)
            last_edit = record.get("edit", 0.0)
            if now - last_view <= self._view_ttl:
                viewing += 1
            if now - last_edit <= self._edit_ttl:
                editing += 1
            if now - last_view > self._view_ttl and now - last_edit > self._edit_ttl:
                stale.append(client_id)
        for client_id in stale:
            entries.pop(client_id, None)
        if entries:
            self._entries[gallery_id] = entries
        else:
            self._entries.pop(gallery_id, None)
        return viewing, editing

    def touch_view(self, gallery_id: str, client_id: str) -> tuple[int, int]:
        now = time.monotonic()
        with self._lock:
            entries = self._entries.setdefault(gallery_id, {})
            record = entries.setdefault(client_id, {})
            record["view"] = now
            return self._counts_locked(gallery_id, now)

    def touch_edit(self, gallery_id: str, client_id: str) -> tuple[int, int]:
        now = time.monotonic()
        with self._lock:
            entries = self._entries.setdefault(gallery_id, {})
            record = entries.setdefault(client_id, {})
            record["view"] = now
            record["edit"] = now
            return self._counts_locked(gallery_id, now)


class IdempotencyCache:
    def __init__(self, ttl_seconds: int = 600) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[float, int, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        for key, (ts, _, _) in list(self._store.items()):
            if now - ts > self._ttl:
                self._store.pop(key, None)

    def get(self, key: str) -> tuple[int, dict[str, Any]] | None:
        now = time.time()
        with self._lock:
            self._prune(now)
            entry = self._store.get(key)
            if not entry:
                return None
            _, status, payload = entry
            return status, payload

    def set(self, key: str, status: int, payload: dict[str, Any]) -> None:
        now = time.time()
        with self._lock:
            self._prune(now)
            self._store[key] = (now, status, payload)


class SnapshotWriter:
    def __init__(
        self,
        workspace: Workspace,
        min_interval: float = 5.0,
        min_updates: int = 20,
        meta_lock: threading.Lock | None = None,
        log_lock: threading.Lock | None = None,
        compact_threshold_bytes: int = 5_000_000,
    ) -> None:
        self._workspace = workspace
        self._min_interval = min_interval
        self._min_updates = min_updates
        self._last_write = 0.0
        self._since = 0
        self._lock = threading.Lock()
        self._meta_lock = meta_lock
        self._log_lock = log_lock
        self._compact_threshold = compact_threshold_bytes

    def maybe_write(self, storage, last_event_id: int) -> None:
        if not self._workspace.can_write:
            return
        now = time.monotonic()
        with self._lock:
            self._since += 1
            if self._since < self._min_updates and now - self._last_write < self._min_interval:
                return
            self._since = 0
            self._last_write = now
        if self._meta_lock is None:
            payload = _build_snapshot_payload(storage, last_event_id)
        else:
            with self._meta_lock:
                payload = _build_snapshot_payload(storage, last_event_id)
        try:
            self._workspace.write_labels_snapshot(payload)
        except Exception as exc:
            print(f"[lenslet] Warning: failed to write labels snapshot: {exc}")
            return
        if self._compact_threshold <= 0:
            return
        try:
            if self._log_lock is None:
                self._workspace.compact_labels_log(last_event_id, max_bytes=self._compact_threshold)
            else:
                with self._log_lock:
                    self._workspace.compact_labels_log(last_event_id, max_bytes=self._compact_threshold)
        except Exception as exc:
            print(f"[lenslet] Warning: failed to compact labels log: {exc}")


def _build_snapshot_payload(storage, last_event_id: int) -> dict[str, Any]:
    meta_map = getattr(storage, "_metadata", None)
    items: dict[str, Any] = {}
    if isinstance(meta_map, dict):
        for path, meta in list(meta_map.items()):
            if not isinstance(meta, dict):
                continue
            meta = _ensure_meta_fields(meta)
            if not _should_persist_meta(meta):
                continue
            key = _canonical_path(path)
            items[key] = _persistable_meta(meta)
    return {"version": 1, "last_event_id": last_event_id, "items": items}


def _should_persist_meta(meta: dict) -> bool:
    if meta.get("version", 1) > 1:
        return True
    if meta.get("tags"):
        return True
    if meta.get("notes"):
        return True
    if meta.get("star") is not None:
        return True
    if meta.get("metrics"):
        return True
    return False


def _persistable_meta(meta: dict) -> dict[str, Any]:
    meta = _ensure_meta_fields(meta)
    payload: dict[str, Any] = {
        "tags": list(meta.get("tags", [])),
        "notes": meta.get("notes", ""),
        "star": meta.get("star"),
        "version": meta.get("version", 1),
        "updated_at": meta.get("updated_at", ""),
        "updated_by": meta.get("updated_by", "server"),
    }
    if "metrics" in meta:
        payload["metrics"] = meta.get("metrics")
    return payload


def _apply_persisted_record(storage, path: str, record: dict[str, Any]) -> bool:
    if not isinstance(record, dict):
        return False
    meta = storage.get_metadata(path)
    meta = _ensure_meta_fields(meta)
    incoming_version = record.get("version", meta.get("version", 1))
    if not isinstance(incoming_version, int):
        incoming_version = meta.get("version", 1)
    if incoming_version <= meta.get("version", 1):
        return False
    if "tags" in record:
        meta["tags"] = list(record.get("tags") or [])
    if "notes" in record:
        meta["notes"] = record.get("notes") or ""
    if "star" in record:
        meta["star"] = record.get("star")
    if "metrics" in record:
        meta["metrics"] = record.get("metrics")
    meta["version"] = incoming_version
    if "updated_at" in record:
        meta["updated_at"] = record.get("updated_at") or ""
    if "updated_by" in record:
        meta["updated_by"] = record.get("updated_by") or "server"
    storage.set_metadata(path, meta)
    return True


def _load_label_state(storage, workspace: Workspace) -> int:
    if not workspace.can_write:
        return 0
    max_event_id = 0
    last_snapshot_id = 0
    snapshot = workspace.read_labels_snapshot()
    if isinstance(snapshot, dict):
        last_snapshot_id = snapshot.get("last_event_id", 0) or 0
        items = snapshot.get("items", {})
        if isinstance(items, dict):
            for raw_path, record in items.items():
                path = _canonical_path(raw_path)
                _apply_persisted_record(storage, path, record if isinstance(record, dict) else {})
        if isinstance(last_snapshot_id, int):
            max_event_id = max(max_event_id, last_snapshot_id)
    for entry in workspace.read_labels_log():
        if not isinstance(entry, dict):
            continue
        event_id = entry.get("id", 0) or 0
        if isinstance(event_id, int) and event_id <= last_snapshot_id:
            continue
        if entry.get("type") not in ("item-updated", "metrics-updated"):
            if "path" not in entry:
                continue
        path = _canonical_path(entry.get("path"))
        _apply_persisted_record(storage, path, entry)
        if isinstance(event_id, int):
            max_event_id = max(max_event_id, event_id)
    return max_event_id


def _updated_by_from_request(request: Request | None) -> str:
    if request is None:
        return "server"
    return request.headers.get("x-updated-by") or request.headers.get("x-client-id") or "server"


def _client_id_from_request(request: Request | None) -> str | None:
    return request.headers.get("x-client-id") if request else None


def _apply_patch_to_meta(meta: dict, body: SidecarPatch) -> bool:
    updated = False
    fields = body.model_fields_set

    tags = list(meta.get("tags", []))
    if "set_tags" in fields:
        next_tags = _normalize_tags(body.set_tags or [])
        if next_tags != tags:
            updated = True
        tags = next_tags

    add_tags = _normalize_tags(body.add_tags or [])
    remove_tags = set(_normalize_tags(body.remove_tags or []))
    if add_tags or remove_tags:
        base = [t for t in tags if t not in remove_tags]
        for tag in add_tags:
            if tag not in base:
                base.append(tag)
        if base != tags:
            updated = True
        tags = base

    if "set_star" in fields:
        if meta.get("star") != body.set_star:
            updated = True
        meta["star"] = body.set_star

    if "set_notes" in fields:
        if meta.get("notes") != (body.set_notes or ""):
            updated = True
        meta["notes"] = body.set_notes or ""

    if tags != list(meta.get("tags", [])):
        meta["tags"] = tags

    return updated


def _init_sync_state(
    storage,
    workspace: Workspace,
    meta_lock: threading.Lock | None = None,
    log_lock: threading.Lock | None = None,
) -> tuple[EventBroker, IdempotencyCache, SnapshotWriter, int]:
    broker = EventBroker(buffer_size=500)
    max_event_id = _load_label_state(storage, workspace)
    if max_event_id:
        broker.set_next_id(max_event_id + 1)
    idempotency = IdempotencyCache(ttl_seconds=600)
    snapshotter = SnapshotWriter(workspace, meta_lock=meta_lock, log_lock=log_lock)
    return broker, idempotency, snapshotter, max_event_id
