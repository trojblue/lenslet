"""Shared indexing lifecycle contracts for health and CLI consumers."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable, Literal

IndexingState = Literal["idle", "running", "ready", "error"]
IndexingListener = Callable[[dict[str, Any]], None]
_TERMINAL_STATES = frozenset({"ready", "error"})
_POLLING_STATES = frozenset({"idle", "running"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def coerce_progress_count(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def normalize_indexing_payload(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    state = payload.get("state")
    if state not in {"idle", "running", "ready", "error"}:
        return None

    done = coerce_progress_count(payload.get("done"))
    total = coerce_progress_count(payload.get("total"))
    if done is not None and total is not None and done > total:
        done = total

    normalized: dict[str, Any] = {"state": state}
    scope = payload.get("scope")
    if isinstance(scope, str):
        normalized["scope"] = scope
    if done is not None:
        normalized["done"] = done
    if total is not None:
        normalized["total"] = total
    started_at = payload.get("started_at")
    if isinstance(started_at, str):
        normalized["started_at"] = started_at
    finished_at = payload.get("finished_at")
    if isinstance(finished_at, str):
        normalized["finished_at"] = finished_at
    error = payload.get("error")
    if isinstance(error, str):
        normalized["error"] = error
    return normalized


def indexing_state_is_terminal(state: str) -> bool:
    return state in _TERMINAL_STATES


def indexing_state_requires_poll(state: str) -> bool:
    return state in _POLLING_STATES


def _scope_suffix(payload: dict[str, Any]) -> str:
    scope = payload.get("scope")
    if not isinstance(scope, str) or scope == "/":
        return ""
    return f" ({scope})"


def _progress_text(payload: dict[str, Any]) -> str:
    done = payload.get("done")
    total = payload.get("total")
    if isinstance(done, int) and isinstance(total, int):
        return f"{done}/{total}"
    return ""


def format_cli_indexing_message(payload: Any) -> str | None:
    normalized = normalize_indexing_payload(payload)
    if normalized is None:
        return None

    state = normalized["state"]
    scope = _scope_suffix(normalized)
    progress = _progress_text(normalized)
    if state == "running":
        if progress:
            return f"Startup indexing in progress{scope}: {progress}."
        return f"Startup indexing in progress{scope}."
    if state == "ready":
        if progress:
            return f"Startup indexing ready{scope}: {progress}."
        return f"Startup indexing ready{scope}."
    if state == "error":
        detail = normalized.get("error")
        if isinstance(detail, str) and detail:
            return f"Startup indexing failed{scope}: {detail}"
        return f"Startup indexing failed{scope}."
    return f"Startup indexing idle{scope}."


class CliIndexingReporter:
    """Emit deterministic CLI lifecycle lines from normalized indexing payloads."""

    def __init__(self, *, write: Callable[[str], None] = print) -> None:
        self._write = write
        self._last_state: IndexingState | None = None
        self._last_error: str | None = None
        self._saw_running = False

    def handle_update(self, payload: Any) -> None:
        normalized = normalize_indexing_payload(payload)
        if normalized is None:
            return

        state = normalized["state"]
        if state == "running":
            self._saw_running = True
            if self._last_state == "running":
                return
            self._emit(normalized, state)
            return

        if state == "ready":
            if not self._saw_running or self._last_state == "ready":
                self._last_state = "ready"
                self._last_error = None
                return
            self._emit(normalized, state)
            return

        if state == "error":
            detail = normalized.get("error") if isinstance(normalized.get("error"), str) else None
            if self._last_state == "error" and detail == self._last_error:
                return
            self._emit(normalized, state)
            self._last_error = detail
            return

        self._last_state = "idle"
        self._last_error = None

    def _emit(self, payload: dict[str, Any], state: IndexingState) -> None:
        message = format_cli_indexing_message(payload)
        self._last_state = state
        self._last_error = None
        if message:
            self._write(f"[lenslet] {message}")


class IndexingLifecycle:
    """Thread-safe tracker for startup indexing lifecycle state."""

    def __init__(self, *, scope: str = "/", initial_state: IndexingState = "idle") -> None:
        self._scope = scope
        self._state: IndexingState = initial_state
        self._started_at: str | None = None
        self._finished_at: str | None = None
        self._error: str | None = None
        self._listeners: list[IndexingListener] = []
        self._lock = Lock()

        if initial_state == "ready":
            now = _now_iso()
            self._started_at = now
            self._finished_at = now
        elif initial_state == "error":
            now = _now_iso()
            self._started_at = now
            self._finished_at = now
            self._error = "indexing failed"

    @classmethod
    def ready(cls, *, scope: str = "/") -> "IndexingLifecycle":
        return cls(scope=scope, initial_state="ready")

    def subscribe(self, listener: IndexingListener, *, emit_current: bool = False) -> None:
        payload: dict[str, Any] | None = None
        with self._lock:
            self._listeners.append(listener)
            if emit_current:
                payload = self._snapshot_unlocked()
        if payload is not None:
            self._notify(listener, payload)

    def start(self, *, scope: str | None = None) -> None:
        payload: dict[str, Any]
        with self._lock:
            if scope is not None:
                self._scope = scope
            self._state = "running"
            self._started_at = _now_iso()
            self._finished_at = None
            self._error = None
            payload = self._snapshot_unlocked()
        self._emit(payload)

    def mark_ready(self) -> None:
        payload: dict[str, Any]
        with self._lock:
            now = _now_iso()
            if self._started_at is None:
                self._started_at = now
            self._state = "ready"
            self._finished_at = now
            self._error = None
            payload = self._snapshot_unlocked()
        self._emit(payload)

    def mark_error(self, message: str) -> None:
        payload: dict[str, Any]
        with self._lock:
            now = _now_iso()
            if self._started_at is None:
                self._started_at = now
            self._state = "error"
            self._finished_at = now
            self._error = message
            payload = self._snapshot_unlocked()
        self._emit(payload)

    def snapshot(self, *, done: int | None = None, total: int | None = None) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_unlocked(done=done, total=total)

    def _snapshot_unlocked(self, *, done: int | None = None, total: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "state": self._state,
            "scope": self._scope,
        }
        if done is not None:
            payload["done"] = done
        if total is not None:
            payload["total"] = total
        if self._started_at is not None:
            payload["started_at"] = self._started_at
        if self._finished_at is not None:
            payload["finished_at"] = self._finished_at
        if self._error is not None:
            payload["error"] = self._error
        return payload

    def _emit(self, payload: dict[str, Any]) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            self._notify(listener, payload)

    @staticmethod
    def _notify(listener: IndexingListener, payload: dict[str, Any]) -> None:
        try:
            listener(dict(payload))
        except Exception:
            return
