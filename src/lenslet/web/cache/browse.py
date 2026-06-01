"""Recursive browse cache helpers for deterministic recursive pagination."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Iterable, Literal

from ...atomic_write import atomic_write_gzip_json
from .browse_snapshot import (
    RecursiveCachedItemSnapshot,
    RecursiveSnapshotWindow,
    canonical_scope as _canonical_scope,
)
from .signals import BestEffortCacheMixin

CACHE_SCHEMA_VERSION = 1
DEFAULT_BROWSE_CACHE_CAP_BYTES = 200 * 1024 * 1024
DEFAULT_BROWSE_MEMORY_ENTRY_LIMIT = 6
RecursiveCachePersistStatus = Literal["written", "queued", "skipped"]
CACHE_PERSIST_WRITTEN: RecursiveCachePersistStatus = "written"
CACHE_PERSIST_QUEUED: RecursiveCachePersistStatus = "queued"
CACHE_PERSIST_SKIPPED: RecursiveCachePersistStatus = "skipped"


def _scopes_overlap(scope: str, changed: str) -> bool:
    if changed == "/" or scope == "/":
        return True
    if scope == changed:
        return True
    if scope.startswith(changed + "/"):
        return True
    return changed.startswith(scope + "/")


class RecursiveBrowseCache(BestEffortCacheMixin):
    """Hybrid in-memory/on-disk cache for recursive browse windows."""

    def __init__(
        self,
        *,
        cache_dir: Path | None = None,
        max_disk_bytes: int = DEFAULT_BROWSE_CACHE_CAP_BYTES,
        max_memory_entries: int = DEFAULT_BROWSE_MEMORY_ENTRY_LIMIT,
    ) -> None:
        self._cache_name = "browse"
        self._last_failure = None
        self._lock = threading.Lock()
        self._memory: dict[tuple[str, str, str], RecursiveSnapshotWindow] = {}
        self._memory_access: dict[tuple[str, str, str], float] = {}
        self._max_memory_entries = max(1, int(max_memory_entries))
        self._max_disk_bytes = max(0, int(max_disk_bytes))
        self._cache_dir = Path(cache_dir) if cache_dir is not None else None
        self._persistence_enabled = self._enable_persistence()
        self._warm_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="lenslet-recursive-cache-warm",
        )
        self._warm_jobs: dict[tuple[str, str, str], threading.Event] = {}
        self._persist_jobs: dict[tuple[str, str, str], threading.Event] = {}
        if self._persistence_enabled:
            self._evict_disk_to_cap()

    @property
    def cache_dir(self) -> Path | None:
        return self._cache_dir

    @property
    def persistence_enabled(self) -> bool:
        return self._persistence_enabled

    @property
    def max_disk_bytes(self) -> int:
        return self._max_disk_bytes

    def pending_warm_count(self) -> int:
        with self._lock:
            return len(self._warm_jobs)

    def load(
        self,
        scope_path: str,
        sort_mode: str,
        generation: str,
    ) -> tuple[RecursiveSnapshotWindow, str] | None:
        key = self._cache_key(scope_path, sort_mode, generation)
        with self._lock:
            cached = self._memory.get(key)
            if cached is not None:
                self._memory_access[key] = time.monotonic()
                return cached, "memory"

        if not self._persistence_enabled:
            return None

        loaded = self._load_disk_window(scope_path, sort_mode, generation)
        if loaded is None:
            return None

        with self._lock:
            self._insert_memory_locked(key, loaded)
        return loaded, "disk"

    def save(
        self,
        scope_path: str,
        sort_mode: str,
        generation: str,
        items: Iterable[RecursiveCachedItemSnapshot],
        *,
        defer_persist: bool = False,
    ) -> tuple[RecursiveSnapshotWindow, RecursiveCachePersistStatus]:
        scope = _canonical_scope(scope_path)
        snapshots = tuple(items)
        window = RecursiveSnapshotWindow(
            scope_path=scope,
            sort_mode=sort_mode,
            generation=generation,
            items=snapshots,
        )
        key = self._cache_key(scope_path, sort_mode, generation)
        with self._lock:
            self._insert_memory_locked(key, window)
        if defer_persist and self._persistence_enabled:
            status = CACHE_PERSIST_QUEUED if self._schedule_persist_write(key, window) else CACHE_PERSIST_SKIPPED
        else:
            status = CACHE_PERSIST_WRITTEN if self._save_disk_window(window) else CACHE_PERSIST_SKIPPED
        return window, status

    def invalidate_path(self, path: str | None = None) -> None:
        if path is None:
            with self._lock:
                self._cancel_pending_warms_locked(None)
                self._cancel_pending_persists_locked(None)
                self._memory.clear()
                self._memory_access.clear()
            self._clear_disk()
            return

        canonical = _canonical_scope(path)
        with self._lock:
            for key in list(self._memory.keys()):
                scope, _sort_mode, _generation = key
                if _scopes_overlap(scope, canonical):
                    self._memory.pop(key, None)
                    self._memory_access.pop(key, None)
            self._cancel_pending_warms_locked(canonical)
            self._cancel_pending_persists_locked(canonical)
        self._clear_disk_path(canonical)

    def clear(self) -> None:
        self.invalidate_path(None)

    def schedule_warm(
        self,
        scope_path: str,
        sort_mode: str,
        generation: str,
        producer: Callable[[threading.Event], Iterable[RecursiveCachedItemSnapshot] | None],
        *,
        delay_seconds: float = 0.0,
        on_saved: Callable[[RecursiveCachePersistStatus], None] | None = None,
    ) -> bool:
        key = self._cache_key(scope_path, sort_mode, generation)
        with self._lock:
            if key in self._memory or key in self._warm_jobs:
                return False
            cancel_event = threading.Event()
            self._warm_jobs[key] = cancel_event

        def _run() -> None:
            persist_status = CACHE_PERSIST_SKIPPED
            try:
                if delay_seconds > 0 and cancel_event.wait(timeout=delay_seconds):
                    return
                snapshots = producer(cancel_event)
                if snapshots is None or cancel_event.is_set():
                    return
                _window, persist_status = self.save(scope_path, sort_mode, generation, snapshots)
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                self._record_failure("warm", target=self._cache_dir, exc=exc)
                return
            finally:
                if on_saved is not None:
                    try:
                        on_saved(persist_status)
                    except (RuntimeError, TypeError, ValueError) as exc:
                        self._record_failure("warm-callback", target=self._cache_dir, exc=exc)
                with self._lock:
                    self._warm_jobs.pop(key, None)

        try:
            self._warm_executor.submit(_run)
            return True
        except RuntimeError as exc:
            self._record_failure("warm-submit", target=self._cache_dir, exc=exc)
            with self._lock:
                self._warm_jobs.pop(key, None)
            return False

    def disk_usage_bytes(self) -> int:
        if not self._persistence_enabled:
            return 0
        total = 0
        for path in self._iter_cache_files():
            try:
                total += path.stat().st_size
            except OSError:
                continue
        return total

    def _cache_key(self, scope_path: str, sort_mode: str, generation: str) -> tuple[str, str, str]:
        return (_canonical_scope(scope_path), sort_mode, generation)

    def _insert_memory_locked(
        self,
        key: tuple[str, str, str],
        window: RecursiveSnapshotWindow,
    ) -> None:
        self._memory[key] = window
        self._memory_access[key] = time.monotonic()
        while len(self._memory) > self._max_memory_entries:
            oldest_key = min(self._memory_access, key=self._memory_access.get)
            self._memory.pop(oldest_key, None)
            self._memory_access.pop(oldest_key, None)

    def _cancel_pending_warms_locked(self, path: str | None) -> None:
        if path is None:
            keys = list(self._warm_jobs.keys())
        else:
            canonical = _canonical_scope(path)
            keys = [key for key in self._warm_jobs.keys() if _scopes_overlap(key[0], canonical)]
        for key in keys:
            event = self._warm_jobs.pop(key, None)
            if event is not None:
                event.set()

    def _cancel_pending_persists_locked(self, path: str | None) -> None:
        if path is None:
            keys = list(self._persist_jobs.keys())
        else:
            canonical = _canonical_scope(path)
            keys = [key for key in self._persist_jobs.keys() if _scopes_overlap(key[0], canonical)]
        for key in keys:
            event = self._persist_jobs.pop(key, None)
            if event is not None:
                event.set()

    def _schedule_persist_write(
        self,
        key: tuple[str, str, str],
        window: RecursiveSnapshotWindow,
    ) -> bool:
        with self._lock:
            if key in self._persist_jobs:
                return False
            cancel_event = threading.Event()
            self._persist_jobs[key] = cancel_event

        def _run() -> None:
            try:
                self._save_disk_window(window, cancel_event=cancel_event)
            finally:
                with self._lock:
                    current = self._persist_jobs.get(key)
                    if current is cancel_event:
                        self._persist_jobs.pop(key, None)

        try:
            self._warm_executor.submit(_run)
            return True
        except RuntimeError as exc:
            self._record_failure("persist-submit", target=self._cache_dir, exc=exc)
            with self._lock:
                current = self._persist_jobs.get(key)
                if current is cancel_event:
                    self._persist_jobs.pop(key, None)
            return False

    def _enable_persistence(self) -> bool:
        if self._cache_dir is None:
            return False
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            probe = self._cache_dir / ".browse-cache-write-probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return True
        except OSError as exc:
            self._record_failure("enable-persistence", target=self._cache_dir, exc=exc)
            return False

    def _disk_path_for(self, scope_path: str, sort_mode: str, generation: str) -> Path:
        payload = json.dumps(
            {
                "scope": _canonical_scope(scope_path),
                "sort": sort_mode,
                "generation": generation,
                "schema": CACHE_SCHEMA_VERSION,
            },
            separators=(",", ":"),
            sort_keys=True,
            ensure_ascii=True,
        ).encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        if self._cache_dir is None:
            raise RuntimeError("persistent recursive browse cache has no cache directory")
        return self._cache_dir / digest[:2] / f"{digest}.json.gz"

    def _load_disk_window(
        self,
        scope_path: str,
        sort_mode: str,
        generation: str,
    ) -> RecursiveSnapshotWindow | None:
        try:
            path = self._disk_path_for(scope_path, sort_mode, generation)
        except RuntimeError as exc:
            self._record_failure(
                "resolve-path",
                target=self._cache_dir,
                exc=exc,
            )
            return None
        if not path.is_file():
            return None
        payload = self._load_disk_payload(path)
        if payload is None:
            return None
        if _canonical_scope(str(payload.get("scope_path", ""))) != _canonical_scope(scope_path):
            self._safe_unlink(path)
            return None
        if str(payload.get("sort_mode", "")) != sort_mode:
            self._safe_unlink(path)
            return None
        if str(payload.get("generation", "")) != generation:
            return None

        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            self._safe_unlink(path)
            return None

        snapshots: list[RecursiveCachedItemSnapshot] = []
        try:
            for entry in raw_items:
                snapshots.append(RecursiveCachedItemSnapshot.from_payload(entry))
        except (TypeError, ValueError):
            self._safe_unlink(path)
            return None

        try:
            os.utime(path, None)
        except OSError as exc:
            self._record_failure("touch", target=path, exc=exc)

        return RecursiveSnapshotWindow(
            scope_path=_canonical_scope(scope_path),
            sort_mode=sort_mode,
            generation=generation,
            items=tuple(snapshots),
        )

    def _save_disk_window(
        self,
        window: RecursiveSnapshotWindow,
        *,
        cancel_event: threading.Event | None = None,
    ) -> bool:
        if not self._persistence_enabled:
            return False
        path: Path | None = None
        try:
            if cancel_event is not None and cancel_event.is_set():
                return False
            path = self._disk_path_for(window.scope_path, window.sort_mode, window.generation)
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema_version": CACHE_SCHEMA_VERSION,
                "scope_path": window.scope_path,
                "sort_mode": window.sort_mode,
                "generation": window.generation,
                "items": [item.to_payload() for item in window.items],
            }
            atomic_write_gzip_json(
                path,
                payload,
                separators=(",", ":"),
                sort_keys=True,
            )
            if cancel_event is not None and cancel_event.is_set():
                self._safe_unlink(path)
                return False
            self._evict_disk_to_cap()
            return path.exists()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self._record_failure("write", target=path or self._cache_dir, exc=exc)
            return False

    def _evict_disk_to_cap(self) -> None:
        if not self._persistence_enabled or self._max_disk_bytes <= 0:
            return

        entries: list[tuple[float, int, Path]] = []
        total = 0
        for path in self._iter_cache_files():
            try:
                stat = path.stat()
            except OSError:
                continue
            total += stat.st_size
            entries.append((stat.st_mtime, stat.st_size, path))

        if total <= self._max_disk_bytes:
            return

        entries.sort(key=lambda entry: entry[0])
        for _mtime, size, path in entries:
            self._safe_unlink(path)
            total -= size
            if total <= self._max_disk_bytes:
                break
        self._cleanup_empty_dirs()

    def _iter_cache_files(self) -> list[Path]:
        if self._cache_dir is None or not self._cache_dir.exists():
            return []
        return [path for path in self._cache_dir.rglob("*.json.gz") if path.is_file()]

    def _clear_disk(self) -> None:
        if not self._persistence_enabled:
            return
        for path in self._iter_cache_files():
            self._safe_unlink(path)
        self._cleanup_empty_dirs()

    def _clear_disk_path(self, scope_path: str) -> None:
        if not self._persistence_enabled:
            return
        canonical = _canonical_scope(scope_path)
        for path in self._iter_cache_files():
            disk_scope = self._read_disk_scope(path)
            if disk_scope is None:
                continue
            if _scopes_overlap(disk_scope, canonical):
                self._safe_unlink(path)
        self._cleanup_empty_dirs()

    def _load_disk_payload(self, path: Path) -> dict[str, Any] | None:
        try:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, gzip.BadGzipFile, json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._record_failure("read", target=path, exc=exc)
            self._safe_unlink(path)
            return None
        if not isinstance(payload, dict):
            self._record_failure("read", target=path, detail="invalid cache payload")
            self._safe_unlink(path)
            return None
        if payload.get("schema_version") != CACHE_SCHEMA_VERSION:
            self._record_failure("read", target=path, detail="unsupported cache schema")
            self._safe_unlink(path)
            return None
        return payload

    def _read_disk_scope(self, path: Path) -> str | None:
        payload = self._load_disk_payload(path)
        if payload is None:
            return None
        raw_scope = payload.get("scope_path")
        if not isinstance(raw_scope, str):
            self._safe_unlink(path)
            return None
        return _canonical_scope(raw_scope)

    def _safe_unlink(self, path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            return
        except OSError as exc:
            self._record_failure("cleanup", target=path, exc=exc)
            return

    def _cleanup_empty_dirs(self) -> None:
        if self._cache_dir is None or not self._cache_dir.exists():
            return
        try:
            candidates = sorted(self._cache_dir.rglob("*"), reverse=True)
        except OSError as exc:
            self._record_failure("scan", target=self._cache_dir, exc=exc)
            return
        for path in candidates:
            if not path.is_dir():
                continue
            try:
                path.rmdir()
            except OSError as exc:
                if path.exists():
                    self._record_failure("cleanup", target=path, exc=exc)
                continue
