from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias, TypedDict

from ...storage.base import SidecarPayload


SyncEventName: TypeAlias = Literal[
    "item-updated",
    "metrics-updated",
    "persistence",
    "presence",
    "table-source",
]
JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
IdempotencyPayload: TypeAlias = dict[str, JsonValue]


class PresenceEventData(TypedDict):
    gallery_id: str
    viewing: int
    editing: int


SyncEventData: TypeAlias = SidecarPayload | PresenceEventData | dict[str, JsonValue]


class SyncEventRecord(TypedDict):
    id: int
    event: SyncEventName
    data: SyncEventData


class EventBrokerDiagnostics(TypedDict):
    replay_miss_total: int
    dropped_client_event_total: int
    buffer_size: int
    buffer_capacity: int
    oldest_event_id: int | None
    newest_event_id: int | None
    connected_sse_clients: int


@dataclass(frozen=True, slots=True)
class IdempotencyCacheEntry:
    created_at: float
    status: int
    payload: IdempotencyPayload
    fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class IdempotencyClaim:
    """Outcome of presenting an Idempotency-Key with the request it names.

    - ``new``: the caller owns the key and must ``set`` or ``release`` it;
    - ``replay``: the same request already finished; return its result;
    - ``mismatch``: the key already names a different request;
    - ``busy``: the same request is still running past the wait budget.
    """

    kind: Literal["new", "replay", "mismatch", "busy"]
    status: int = 0
    payload: IdempotencyPayload | None = None


def format_sse(record: SyncEventRecord) -> str:
    data = json.dumps(record["data"], separators=(",", ":"))
    return f"event: {record['event']}\nid: {record['id']}\ndata: {data}\n\n"


class EventBroker:
    def __init__(self, buffer_size: int = 500) -> None:
        self._buffer: deque[SyncEventRecord] = deque(maxlen=buffer_size)
        self._next_id = 1
        self._next_publish_id = 1
        self._reservations: dict[int, SyncEventRecord | None | object] = {}
        self._clients: set[asyncio.Queue[SyncEventRecord]] = set()
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._replay_miss_total = 0
        self._dropped_client_event_total = 0

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
            self._next_publish_id = max(self._next_publish_id, next_id)

    def reserve(self) -> int:
        with self._lock:
            event_id = self._next_id
            self._next_id += 1
            self._reservations[event_id] = None
            return event_id

    def publish(self, event: SyncEventName, data: SyncEventData) -> int:
        event_id = self.reserve()
        self.publish_reserved(event_id, event, data)
        return event_id

    def publish_reserved(
        self,
        event_id: int,
        event: SyncEventName,
        data: SyncEventData,
    ) -> None:
        with self._lock:
            record: SyncEventRecord = {"id": event_id, "event": event, "data": data}
            if event_id not in self._reservations:
                raise RuntimeError(f"event {event_id} was not reserved")
            self._reservations[event_id] = record
            records = self._drain_reservations_locked()
            loop = self._loop
        if loop is not None:
            for ready in records:
                loop.call_soon_threadsafe(self._broadcast, ready)

    def cancel_reserved(self, event_id: int) -> None:
        with self._lock:
            if event_id not in self._reservations:
                return
            self._reservations[event_id] = _CANCELLED_RESERVATION
            records = self._drain_reservations_locked()
            loop = self._loop
        if loop is not None:
            for ready in records:
                loop.call_soon_threadsafe(self._broadcast, ready)

    def _drain_reservations_locked(self) -> list[SyncEventRecord]:
        records: list[SyncEventRecord] = []
        while self._next_publish_id in self._reservations:
            record = self._reservations[self._next_publish_id]
            if record is None:
                break
            self._reservations.pop(self._next_publish_id)
            self._next_publish_id += 1
            if record is _CANCELLED_RESERVATION:
                continue
            if not isinstance(record, dict):
                raise RuntimeError("invalid event reservation")
            self._buffer.append(record)
            records.append(record)
        return records

    def _broadcast(self, record: SyncEventRecord) -> None:
        for queue in list(self._clients):
            if queue.full():
                self._dropped_client_event_total += 1
                continue
            queue.put_nowait(record)

    def register(self) -> asyncio.Queue[SyncEventRecord]:
        queue: asyncio.Queue[SyncEventRecord] = asyncio.Queue(maxsize=200)
        with self._lock:
            self._clients.add(queue)
        return queue

    def unregister(self, queue: asyncio.Queue[SyncEventRecord]) -> None:
        with self._lock:
            self._clients.discard(queue)

    def replay(self, last_id: int | None) -> list[SyncEventRecord]:
        if last_id is None:
            return []
        with self._lock:
            if not self._buffer:
                return []
            oldest_id = self._buffer[0]["id"]
            newest_id = self._buffer[-1]["id"]
            if last_id >= newest_id:
                return []
            if last_id < oldest_id - 1:
                self._replay_miss_total += 1
            return [item for item in self._buffer if item["id"] > last_id]

    def diagnostics(self) -> EventBrokerDiagnostics:
        with self._lock:
            oldest = self._buffer[0]["id"] if self._buffer else None
            newest = self._buffer[-1]["id"] if self._buffer else None
            return {
                "replay_miss_total": self._replay_miss_total,
                "dropped_client_event_total": self._dropped_client_event_total,
                "buffer_size": len(self._buffer),
                "buffer_capacity": int(self._buffer.maxlen or 0),
                "oldest_event_id": oldest,
                "newest_event_id": newest,
                "connected_sse_clients": len(self._clients),
            }


class IdempotencyCache:
    def __init__(self, ttl_seconds: int = 600, max_entries: int = 10_000) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._store: dict[str, IdempotencyCacheEntry] = {}
        self._inflight: dict[str, tuple[str, threading.Event]] = {}
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        for key, entry in list(self._store.items()):
            if now - entry.created_at > self._ttl:
                self._store.pop(key, None)
        while len(self._store) > self._max_entries:
            self._store.pop(next(iter(self._store)))

    def claim(self, key: str, fingerprint: str, *, wait_seconds: float = 30.0) -> IdempotencyClaim:
        """Atomically decide who handles ``key``; a concurrent duplicate waits for the first."""
        while True:
            with self._lock:
                self._prune(time.time())
                entry = self._store.get(key)
                if entry is not None:
                    if entry.fingerprint != fingerprint:
                        return IdempotencyClaim("mismatch")
                    return IdempotencyClaim("replay", entry.status, entry.payload)
                running = self._inflight.get(key)
                if running is None:
                    self._inflight[key] = (fingerprint, threading.Event())
                    return IdempotencyClaim("new")
                if running[0] != fingerprint:
                    return IdempotencyClaim("mismatch")
                done = running[1]
            if not done.wait(wait_seconds):
                return IdempotencyClaim("busy")

    def release(self, key: str) -> None:
        """Give up a claimed key without a result, waking any waiting duplicate."""
        with self._lock:
            running = self._inflight.pop(key, None)
        if running is not None:
            running[1].set()

    def set(
        self,
        key: str,
        status: int,
        payload: IdempotencyPayload,
        *,
        fingerprint: str | None = None,
    ) -> None:
        """Record a result; ``fingerprint`` defaults to the one already bound to ``key``."""
        now = time.time()
        with self._lock:
            self._prune(now)
            existing = self._store.get(key)
            running = self._inflight.pop(key, None)
            if fingerprint is None:
                fingerprint = existing.fingerprint if existing else running[0] if running else None
            if existing is None or not _would_regress_durable_result(existing.payload, payload):
                self._store[key] = IdempotencyCacheEntry(
                    created_at=now, status=status, payload=payload, fingerprint=fingerprint,
                )
            self._prune(now)
        if running is not None:
            running[1].set()

    def seed(
        self,
        entries: Mapping[str, Mapping[str, object]],
        *,
        replace: bool = False,
    ) -> None:
        now = time.time()
        with self._lock:
            if replace:
                self._store.clear()
            for key, entry in entries.items():
                status = entry.get("status")
                payload = entry.get("payload")
                if not isinstance(key, str) or not isinstance(status, int) or not isinstance(payload, dict):
                    continue
                fingerprint = entry.get("fingerprint")
                self._store[key] = IdempotencyCacheEntry(
                    created_at=now,
                    status=status,
                    payload=dict(payload),
                    fingerprint=fingerprint if isinstance(fingerprint, str) else None,
                )
            self._prune(now)


_CANCELLED_RESERVATION = object()


def _would_regress_durable_result(
    existing: Mapping[str, object],
    incoming: Mapping[str, object],
) -> bool:
    if existing.get("persistence") != "saved" or incoming.get("persistence") != "pending":
        return False
    existing_identity = existing.get("accepted_event")
    incoming_identity = incoming.get("accepted_event")
    return (
        isinstance(existing_identity, dict)
        and isinstance(incoming_identity, dict)
        and existing_identity == incoming_identity
    )
