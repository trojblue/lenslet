from __future__ import annotations

import json
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, TypedDict
from uuid import uuid4

from ...workspace import Workspace
from .events import EventBroker, IdempotencyCache
from .labels import (
    LabelPersistenceError,
    LoadedLabelState,
    SnapshotWriter,
    coerce_durable_mutation_result,
    persistable_sidecar,
    should_persist_sidecar,
)

MAX_PENDING_EVENTS = 10_000
MAX_PENDING_BYTES = 16 * 1024 * 1024


class AcceptedEventIdentity(TypedDict):
    boot_epoch: str
    event_id: int


class LabelPersistenceStatus(TypedDict):
    enabled: bool
    boot_epoch: str
    state: Literal["disabled", "saved", "pending", "failed"]
    durable_watermark: AcceptedEventIdentity
    pending_count: int
    pending_bytes: int
    max_pending_count: int
    max_pending_bytes: int
    oldest_pending_age_ms: float | None
    error: str | None
    failure_total: int
    deadline_breach_total: int


@dataclass(slots=True)
class _PendingLabelEvent:
    event: dict[str, object]
    accepted_at: float
    encoded_bytes: int
    ready: bool = False


@dataclass(slots=True)
class _FlushAttempt:
    token: int
    recovery: bool
    deadline_breached: bool = False


class LabelWriteBuffer:
    """Bounded memory-first label writer with one ordered durability thread.

    Request lock order is sidecar -> broker reservation -> writer reservation. No
    request lock is held while this worker appends, flushes, fsyncs, snapshots,
    or compacts.
    """

    def __init__(
        self,
        workspace: Workspace,
        loaded: LoadedLabelState,
        *,
        broker: EventBroker,
        idempotency_cache: IdempotencyCache,
        clock: Callable[[], float] = time.monotonic,
        idle_flush_seconds: float = 1.0,
        deadline_start_seconds: float = 13.0,
        hard_deadline_seconds: float = 15.0,
        io_margin_seconds: float = 2.0,
        retry_seconds: float = 1.0,
        background: bool = True,
        max_pending_events: int = MAX_PENDING_EVENTS,
        max_pending_bytes: int = MAX_PENDING_BYTES,
    ) -> None:
        self._workspace = workspace
        self._broker = broker
        self._idempotency_cache = idempotency_cache
        self._clock = clock
        self._idle_flush_seconds = idle_flush_seconds
        self._deadline_start_seconds = deadline_start_seconds
        self._hard_deadline_seconds = hard_deadline_seconds
        self._io_margin_seconds = io_margin_seconds
        self._retry_seconds = retry_seconds
        self._background = background
        self._max_pending_events = max_pending_events
        self._max_pending_bytes = max_pending_bytes
        self._boot_epoch = uuid4().hex
        self._condition = threading.Condition()
        self._flush_lock = threading.Lock()
        self._pending: deque[_PendingLabelEvent] = deque()
        self._pending_bytes = 0
        self._durable_event_id = loaded.last_event_id
        self._durable_items = dict(loaded.items)
        self._durable_mutations = dict(loaded.mutations)
        self._failure: str | None = None
        self._failure_total = 0
        self._deadline_breach_total = 0
        self._next_retry_at = 0.0
        self._admission_pause: str | None = None
        self._flush_attempt_sequence = 0
        self._active_flush_attempt: _FlushAttempt | None = None
        self._thread: threading.Thread | None = None
        self._stopping = False
        self._snapshotter = SnapshotWriter(workspace)

    @property
    def boot_epoch(self) -> str:
        return self._boot_epoch

    def accepted_identity(self, event_id: int) -> AcceptedEventIdentity:
        return {"boot_epoch": self._boot_epoch, "event_id": event_id}

    def start(self) -> None:
        if not self._background:
            return
        with self._condition:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stopping = False
            self._thread = threading.Thread(
                target=self._run,
                name="lenslet-label-writer",
                daemon=True,
            )
            self._thread.start()

    def accept(self, event: dict[str, object]) -> AcceptedEventIdentity:
        self.start()
        encoded_bytes = len(
            (json.dumps(event, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")
        )
        event_id = event.get("id")
        accepted = event.get("accepted_event")
        if not isinstance(event_id, int) or not isinstance(accepted, Mapping):
            raise TypeError("label event requires an integer id and accepted_event")
        if accepted.get("boot_epoch") != self._boot_epoch or accepted.get("event_id") != event_id:
            raise ValueError("label event identity does not match the active writer epoch")
        with self._condition:
            if not self._workspace.can_write:
                raise LabelPersistenceError("label persistence is disabled")
            if self._admission_pause is not None:
                raise LabelPersistenceError(self._admission_pause)
            if self._failure is not None:
                raise LabelPersistenceError(f"label persistence unavailable: {self._failure}")
            if len(self._pending) >= self._max_pending_events:
                raise LabelPersistenceError("label persistence queue is full")
            if self._pending_bytes + encoded_bytes > self._max_pending_bytes:
                raise LabelPersistenceError("label persistence byte capacity is full")
            self._pending.append(
                _PendingLabelEvent(
                    event=dict(event),
                    accepted_at=self._clock(),
                    encoded_bytes=encoded_bytes,
                )
            )
            self._pending_bytes += encoded_bytes
            self._condition.notify_all()
        return {"boot_epoch": self._boot_epoch, "event_id": event_id}

    def mark_ready(self, event_id: int) -> None:
        with self._condition:
            pending = self._pending_event(event_id)
            if pending is None:
                raise RuntimeError(f"label event {event_id} is not pending")
            pending.ready = True
            self._condition.notify_all()

    def cancel(self, event_id: int) -> None:
        with self._condition:
            for pending in self._pending:
                if pending.event.get("id") != event_id:
                    continue
                if pending.ready:
                    raise RuntimeError("cannot cancel a committed label event")
                self._pending.remove(pending)
                self._pending_bytes -= pending.encoded_bytes
                self._condition.notify_all()
                return

    def status(self) -> LabelPersistenceStatus:
        with self._condition:
            return self._status_locked(self._clock())

    def pause_admission(self, reason: str) -> None:
        with self._condition:
            if self._admission_pause is not None:
                raise LabelPersistenceError(self._admission_pause)
            self._admission_pause = reason

    def resume_admission(self) -> None:
        with self._condition:
            self._admission_pause = None
            self._condition.notify_all()

    def publish_status(self) -> None:
        self._emit_status(self.status())

    def flush_due(self, *, force: bool = False, now: float | None = None) -> bool:
        with self._flush_lock:
            current = self._clock() if now is None else now
            batch = self._ready_batch(current, force=force)
            if not batch:
                return False
            return self._flush_batch(batch)

    def flush_all(self, *, retries: int = 2) -> None:
        attempts = 0
        while True:
            with self._condition:
                if not self._pending:
                    durable_items = dict(self._durable_items)
                    durable_mutations = dict(self._durable_mutations)
                    watermark = self._durable_event_id
                    break
                if not all(item.ready for item in self._pending):
                    raise LabelPersistenceError("cannot flush an uncommitted label reservation")
            if self.flush_due(force=True):
                attempts = 0
                continue
            attempts += 1
            if attempts > retries:
                status = self.status()
                raise LabelPersistenceError(status["error"] or "failed to flush label updates")
        if watermark > 0 or durable_items or durable_mutations:
            self._snapshotter.maybe_write(
                durable_items,
                durable_mutations,
                watermark,
                force=True,
            )

    def persist_state(self) -> None:
        with self._condition:
            durable_items = dict(self._durable_items)
            durable_mutations = dict(self._durable_mutations)
            watermark = self._durable_event_id
        if not self._snapshotter.maybe_write(
            durable_items,
            durable_mutations,
            watermark,
            force=True,
        ):
            raise LabelPersistenceError("failed to persist replacement label state")

    def close(self) -> None:
        error: BaseException | None = None
        try:
            self.flush_all()
        except BaseException as exc:
            error = exc
        with self._condition:
            self._stopping = True
            self._condition.notify_all()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(5.0, self._io_margin_seconds + 1.0))
            if thread.is_alive() and error is None:
                error = LabelPersistenceError("label writer did not stop")
        if error is not None:
            raise error

    def _run(self) -> None:
        while True:
            with self._condition:
                if self._stopping:
                    return
                wait_seconds = self._wait_seconds_locked(self._clock())
                if wait_seconds is None:
                    self._condition.wait()
                    continue
                if wait_seconds > 0:
                    self._condition.wait(timeout=wait_seconds)
                    continue
            self.flush_due()

    def _wait_seconds_locked(self, now: float) -> float | None:
        if not self._pending or not self._pending[0].ready:
            return None
        if self._failure is not None and now < self._next_retry_at:
            return self._next_retry_at - now
        ready = [item for item in self._pending if item.ready]
        if not ready:
            return None
        due_at = min(
            ready[-1].accepted_at + self._idle_flush_seconds,
            ready[0].accepted_at + self._deadline_start_seconds,
        )
        return max(0.0, due_at - now)

    def _ready_batch(self, now: float, *, force: bool) -> tuple[_PendingLabelEvent, ...]:
        with self._condition:
            if not self._pending or not self._pending[0].ready:
                return ()
            if self._failure is not None and not force and now < self._next_retry_at:
                return ()
            ready: list[_PendingLabelEvent] = []
            for item in self._pending:
                if not item.ready:
                    break
                ready.append(item)
            due_at = min(
                ready[-1].accepted_at + self._idle_flush_seconds,
                ready[0].accepted_at + self._deadline_start_seconds,
            )
            if not force and now < due_at:
                return ()
            return tuple(ready)

    def _flush_batch(self, batch: tuple[_PendingLabelEvent, ...]) -> bool:
        started_at = self._clock()
        attempt, watchdog = self._begin_flush_attempt(batch, started_at)
        try:
            self._workspace.append_labels_log_batch([item.event for item in batch])
        except (OSError, PermissionError, RuntimeError, TypeError, ValueError) as exc:
            watchdog.cancel()
            with self._condition:
                if self._active_flush_attempt is attempt:
                    self._active_flush_attempt = None
                if not attempt.deadline_breached:
                    self._failure = str(exc) or type(exc).__name__
                    self._failure_total += 1
                self._next_retry_at = self._clock() + self._retry_seconds
                status = self._status_locked(self._clock())
                self._condition.notify_all()
            self._emit_status(status)
            return False

        completed_at = self._clock()
        watchdog.cancel()
        if (
            not attempt.deadline_breached
            and (
                (
                    not attempt.recovery
                    and completed_at - batch[0].accepted_at > self._hard_deadline_seconds
                )
                or completed_at - started_at > self._io_margin_seconds
            )
        ):
            self._mark_deadline_breach(attempt)
        if attempt.deadline_breached:
            with self._condition:
                if self._active_flush_attempt is attempt:
                    self._active_flush_attempt = None
                self._next_retry_at = completed_at + self._retry_seconds
                self._condition.notify_all()
            return False

        with self._condition:
            if self._active_flush_attempt is attempt:
                self._active_flush_attempt = None
            for expected in batch:
                current = self._pending.popleft()
                if current is not expected:
                    raise RuntimeError("label persistence queue order changed during flush")
                self._pending_bytes -= current.encoded_bytes
                self._apply_durable_event(current.event)
            self._durable_event_id = int(batch[-1].event["id"])
            self._failure = None
            self._next_retry_at = 0.0
            durable_items = dict(self._durable_items)
            durable_mutations = dict(self._durable_mutations)
            watermark = self._durable_event_id
            status = self._status_locked(completed_at)
            self._condition.notify_all()
        self._snapshotter.maybe_write(durable_items, durable_mutations, watermark)
        self._emit_status(status)
        return True

    def _begin_flush_attempt(
        self,
        batch: tuple[_PendingLabelEvent, ...],
        started_at: float,
    ) -> tuple[_FlushAttempt, threading.Timer]:
        with self._condition:
            recovering = self._failure is not None
            self._flush_attempt_sequence += 1
            attempt = _FlushAttempt(self._flush_attempt_sequence, recovery=recovering)
            self._active_flush_attempt = attempt
        remaining = self._io_margin_seconds
        if not recovering:
            remaining = min(
                remaining,
                batch[0].accepted_at + self._hard_deadline_seconds - started_at,
            )
        watchdog = threading.Timer(
            max(0.0, remaining),
            self._mark_deadline_breach,
            args=(attempt,),
        )
        watchdog.name = "lenslet-label-writer-deadline"
        watchdog.daemon = True
        watchdog.start()
        return attempt, watchdog

    def _mark_deadline_breach(self, attempt: _FlushAttempt) -> None:
        with self._condition:
            if self._active_flush_attempt is not attempt or attempt.deadline_breached:
                return
            attempt.deadline_breached = True
            self._deadline_breach_total += 1
            self._failure_total += 1
            self._failure = "label persistence deadline exceeded"
            self._next_retry_at = self._clock() + self._retry_seconds
            status = self._status_locked(self._clock())
            self._condition.notify_all()
        self._emit_status(status)

    def _apply_durable_event(self, event: Mapping[str, object]) -> None:
        path = event.get("path")
        if isinstance(path, str):
            sidecar = dict(event)
            if should_persist_sidecar(sidecar):
                self._durable_items[path] = persistable_sidecar(sidecar)
            else:
                self._durable_items.pop(path, None)
        mutation_id = event.get("mutation_id")
        mutation_result = coerce_durable_mutation_result(event.get("mutation_result"))
        if isinstance(mutation_id, str) and mutation_result is not None:
            self._durable_mutations[mutation_id] = mutation_result
            self._idempotency_cache.set(
                mutation_id,
                mutation_result["status"],
                mutation_result["payload"],
            )
            while len(self._durable_mutations) > MAX_PENDING_EVENTS:
                self._durable_mutations.pop(next(iter(self._durable_mutations)))

    def _pending_event(self, event_id: int) -> _PendingLabelEvent | None:
        for pending in self._pending:
            if pending.event.get("id") == event_id:
                return pending
        return None

    def _status_locked(self, now: float) -> LabelPersistenceStatus:
        enabled = self._workspace.can_write
        oldest_age = None
        if self._pending:
            oldest_age = max(0.0, now - self._pending[0].accepted_at) * 1000.0
        if not enabled:
            state: Literal["disabled", "saved", "pending", "failed"] = "disabled"
        elif self._failure is not None:
            state = "failed"
        elif self._pending:
            state = "pending"
        else:
            state = "saved"
        return {
            "enabled": enabled,
            "boot_epoch": self._boot_epoch,
            "state": state,
            "durable_watermark": self.accepted_identity(self._durable_event_id),
            "pending_count": len(self._pending),
            "pending_bytes": self._pending_bytes,
            "max_pending_count": self._max_pending_events,
            "max_pending_bytes": self._max_pending_bytes,
            "oldest_pending_age_ms": oldest_age,
            "error": self._failure,
            "failure_total": self._failure_total,
            "deadline_breach_total": self._deadline_breach_total,
        }

    def _emit_status(self, status: LabelPersistenceStatus) -> None:
        try:
            self._broker.publish("persistence", dict(status))
        except Exception as exc:
            print(f"[lenslet] Warning: failed to publish label persistence status: {exc}")
