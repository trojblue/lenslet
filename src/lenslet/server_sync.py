from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

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
        self._replay_miss_total = 0

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
            if not self._buffer:
                return []
            oldest_id = int(self._buffer[0].get("id", 0))
            newest_id = int(self._buffer[-1].get("id", 0))
            if last_id >= newest_id:
                return []
            if last_id < oldest_id - 1:
                self._replay_miss_total += 1
            return [item for item in self._buffer if item.get("id", 0) > last_id]

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            oldest = int(self._buffer[0].get("id", 0)) if self._buffer else None
            newest = int(self._buffer[-1].get("id", 0)) if self._buffer else None
            return {
                "replay_miss_total": self._replay_miss_total,
                "buffer_size": len(self._buffer),
                "buffer_capacity": int(self._buffer.maxlen or 0),
                "oldest_event_id": oldest,
                "newest_event_id": newest,
                "connected_sse_clients": len(self._clients),
            }


@dataclass(frozen=True)
class PresenceCount:
    gallery_id: str
    viewing: int
    editing: int


@dataclass
class _PresenceSession:
    gallery_id: str
    lease_id: str
    last_view: float
    last_edit: float = 0.0


class PresenceLeaseError(Exception):
    pass


class PresenceScopeError(Exception):
    def __init__(self, expected_gallery_id: str, actual_gallery_id: str) -> None:
        super().__init__(f"scope mismatch: expected={expected_gallery_id}, actual={actual_gallery_id}")
        self.expected_gallery_id = expected_gallery_id
        self.actual_gallery_id = actual_gallery_id


class PresenceTracker:
    def __init__(self, view_ttl: float = 75.0, edit_ttl: float = 60.0) -> None:
        self._view_ttl = view_ttl
        self._edit_ttl = edit_ttl
        self._lock = threading.Lock()
        self._sessions: dict[str, _PresenceSession] = {}
        self._clients_by_scope: dict[str, set[str]] = {}
        self._stale_pruned_total = 0

    @property
    def view_ttl_seconds(self) -> float:
        return self._view_ttl

    @property
    def edit_ttl_seconds(self) -> float:
        return self._edit_ttl

    def _new_lease(self) -> str:
        return uuid4().hex

    def _scope_add_locked(self, gallery_id: str, client_id: str) -> None:
        members = self._clients_by_scope.setdefault(gallery_id, set())
        members.add(client_id)

    def _scope_remove_locked(self, gallery_id: str, client_id: str) -> None:
        members = self._clients_by_scope.get(gallery_id)
        if members is None:
            return
        members.discard(client_id)
        if not members:
            self._clients_by_scope.pop(gallery_id, None)

    def _remove_client_locked(self, client_id: str) -> str | None:
        session = self._sessions.pop(client_id, None)
        if session is None:
            return None
        self._scope_remove_locked(session.gallery_id, client_id)
        return session.gallery_id

    def _is_viewing(self, session: _PresenceSession, now: float) -> bool:
        return (now - session.last_view) <= self._view_ttl

    def _is_editing(self, session: _PresenceSession, now: float) -> bool:
        if session.last_edit <= 0.0:
            return False
        return (now - session.last_edit) <= self._edit_ttl

    def _prune_stale_locked(self, now: float) -> set[str]:
        affected: set[str] = set()
        if not self._sessions:
            return affected
        stale_clients: list[str] = []
        for client_id, session in self._sessions.items():
            if self._is_viewing(session, now) or self._is_editing(session, now):
                continue
            stale_clients.append(client_id)
        for client_id in stale_clients:
            removed_scope = self._remove_client_locked(client_id)
            if removed_scope is not None:
                self._stale_pruned_total += 1
                affected.add(removed_scope)
        return affected

    def _counts_locked(self, gallery_id: str, now: float) -> tuple[int, int]:
        members = self._clients_by_scope.get(gallery_id)
        if not members:
            return 0, 0
        viewing = 0
        editing = 0
        for client_id in tuple(members):
            session = self._sessions.get(client_id)
            if session is None or session.gallery_id != gallery_id:
                self._scope_remove_locked(gallery_id, client_id)
                continue
            if self._is_viewing(session, now):
                viewing += 1
            if self._is_editing(session, now):
                editing += 1
        return viewing, editing

    def _counts_payloads_locked(self, scopes: set[str], now: float) -> list[PresenceCount]:
        payloads: list[PresenceCount] = []
        for gallery_id in sorted(scopes):
            viewing, editing = self._counts_locked(gallery_id, now)
            payloads.append(PresenceCount(gallery_id=gallery_id, viewing=viewing, editing=editing))
        return payloads

    def _session_for_lease_locked(self, client_id: str, lease_id: str) -> _PresenceSession:
        session = self._sessions.get(client_id)
        if session is None or session.lease_id != lease_id:
            raise PresenceLeaseError("invalid lease")
        return session

    def _resolve_session_locked(
        self,
        gallery_id: str,
        client_id: str,
        now: float,
        lease_id: str | None = None,
    ) -> tuple[str, set[str]]:
        affected: set[str] = {gallery_id}
        session = self._sessions.get(client_id)
        if session is None:
            lease = self._new_lease()
            self._sessions[client_id] = _PresenceSession(
                gallery_id=gallery_id,
                lease_id=lease,
                last_view=now,
                last_edit=0.0,
            )
            self._scope_add_locked(gallery_id, client_id)
            return lease, affected

        if lease_id and session.lease_id != lease_id:
            raise PresenceLeaseError("invalid lease")

        lease = session.lease_id
        if session.gallery_id != gallery_id:
            old_gallery = session.gallery_id
            self._scope_remove_locked(old_gallery, client_id)
            session.gallery_id = gallery_id
            session.last_edit = 0.0
            self._scope_add_locked(gallery_id, client_id)
            affected.add(old_gallery)
        session.last_view = now
        return lease, affected

    def _touch_locked(
        self,
        gallery_id: str,
        client_id: str,
        now: float,
        lease_id: str | None = None,
        *,
        editing: bool,
    ) -> tuple[str, list[PresenceCount]]:
        affected = self._prune_stale_locked(now)
        lease, touched = self._resolve_session_locked(gallery_id, client_id, now, lease_id=lease_id)
        if editing:
            self._sessions[client_id].last_edit = now
        affected.update(touched)
        return lease, self._counts_payloads_locked(affected, now)

    def join(self, gallery_id: str, client_id: str, lease_id: str | None = None) -> tuple[str, list[PresenceCount]]:
        now = time.monotonic()
        with self._lock:
            affected = self._prune_stale_locked(now)
            existing = self._sessions.get(client_id)
            reuse_existing_lease = existing is not None and lease_id == existing.lease_id
            if existing is not None and lease_id and not reuse_existing_lease:
                raise PresenceLeaseError("invalid lease")
            if existing is not None and not reuse_existing_lease:
                removed_scope = self._remove_client_locked(client_id)
                if removed_scope is not None:
                    affected.add(removed_scope)
            resolved_lease = lease_id if reuse_existing_lease else None
            lease, touched = self._resolve_session_locked(gallery_id, client_id, now, lease_id=resolved_lease)
            affected.update(touched)
            return lease, self._counts_payloads_locked(affected, now)

    def touch_view(
        self,
        gallery_id: str,
        client_id: str,
        lease_id: str | None = None,
    ) -> tuple[str, list[PresenceCount]]:
        now = time.monotonic()
        with self._lock:
            return self._touch_locked(gallery_id, client_id, now, lease_id=lease_id, editing=False)

    def touch_edit(
        self,
        gallery_id: str,
        client_id: str,
        lease_id: str | None = None,
    ) -> tuple[str, list[PresenceCount]]:
        now = time.monotonic()
        with self._lock:
            return self._touch_locked(gallery_id, client_id, now, lease_id=lease_id, editing=True)

    def move(
        self,
        from_gallery_id: str,
        to_gallery_id: str,
        client_id: str,
        lease_id: str,
    ) -> list[PresenceCount]:
        now = time.monotonic()
        with self._lock:
            affected = self._prune_stale_locked(now)
            session = self._session_for_lease_locked(client_id, lease_id)
            current = session.gallery_id
            if current == to_gallery_id:
                session.last_view = now
                affected.add(current)
                return self._counts_payloads_locked(affected, now)
            if current != from_gallery_id:
                raise PresenceScopeError(expected_gallery_id=from_gallery_id, actual_gallery_id=current)
            self._scope_remove_locked(current, client_id)
            session.gallery_id = to_gallery_id
            session.last_view = now
            session.last_edit = 0.0
            self._scope_add_locked(to_gallery_id, client_id)
            affected.add(current)
            affected.add(to_gallery_id)
            return self._counts_payloads_locked(affected, now)

    def leave(
        self,
        gallery_id: str,
        client_id: str,
        lease_id: str,
    ) -> tuple[bool, list[PresenceCount]]:
        now = time.monotonic()
        with self._lock:
            affected = self._prune_stale_locked(now)
            affected.add(gallery_id)
            session = self._sessions.get(client_id)
            if session is None:
                return False, self._counts_payloads_locked(affected, now)
            if session.lease_id != lease_id:
                raise PresenceLeaseError("invalid lease")
            if session.gallery_id != gallery_id:
                raise PresenceScopeError(expected_gallery_id=gallery_id, actual_gallery_id=session.gallery_id)
            removed_scope = self._remove_client_locked(client_id)
            if removed_scope is not None:
                affected.add(removed_scope)
            return True, self._counts_payloads_locked(affected, now)

    def snapshot_counts(self) -> dict[str, PresenceCount]:
        now = time.monotonic()
        with self._lock:
            self._prune_stale_locked(now)
            out: dict[str, PresenceCount] = {}
            for gallery_id in sorted(self._clients_by_scope):
                viewing, editing = self._counts_locked(gallery_id, now)
                out[gallery_id] = PresenceCount(gallery_id=gallery_id, viewing=viewing, editing=editing)
            return out

    def debug_state(self) -> dict[str, Any]:
        with self._lock:
            clients = {
                client_id: {
                    "gallery_id": session.gallery_id,
                    "lease_id": session.lease_id,
                    "last_view": session.last_view,
                    "last_edit": session.last_edit,
                }
                for client_id, session in self._sessions.items()
            }
            scopes = {gallery_id: sorted(members) for gallery_id, members in self._clients_by_scope.items()}
            return {
                "clients": clients,
                "scopes": scopes,
                "stale_pruned_total": self._stale_pruned_total,
            }

    def diagnostics(self) -> dict[str, int]:
        with self._lock:
            return {
                "active_clients": len(self._sessions),
                "active_scopes": len(self._clients_by_scope),
                "stale_pruned_total": self._stale_pruned_total,
            }


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
