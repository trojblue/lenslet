"""Recursive browse cache helpers for deterministic recursive pagination."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

CACHE_SCHEMA_VERSION = 1
DEFAULT_BROWSE_CACHE_CAP_BYTES = 200 * 1024 * 1024
DEFAULT_BROWSE_MEMORY_ENTRY_LIMIT = 6


def _canonical_scope(path: str) -> str:
    value = (path or "").replace("\\", "/").strip()
    if not value:
        return "/"
    value = "/" + value.lstrip("/")
    if value != "/":
        value = value.rstrip("/")
    return value


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _coerce_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _normalize_metrics(raw: Any) -> dict[str, float] | None:
    if not isinstance(raw, dict):
        return None
    metrics: dict[str, float] = {}
    for key, value in raw.items():
        try:
            metrics[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return metrics or None


def _scopes_overlap(scope: str, changed: str) -> bool:
    if changed == "/" or scope == "/":
        return True
    if scope == changed:
        return True
    if scope.startswith(changed + "/"):
        return True
    return changed.startswith(scope + "/")


@dataclass(frozen=True)
class RecursiveCachedItemSnapshot:
    path: str
    name: str
    mime: str
    width: int
    height: int
    size: int
    mtime: float
    url: str | None = None
    source: str | None = None
    metrics: dict[str, float] | None = None

    @classmethod
    def from_cached_item(cls, cached: Any) -> "RecursiveCachedItemSnapshot":
        return cls(
            path=_canonical_scope(str(getattr(cached, "path", ""))),
            name=str(getattr(cached, "name", "")),
            mime=str(getattr(cached, "mime", "image/jpeg")),
            width=_coerce_int(getattr(cached, "width", 0)),
            height=_coerce_int(getattr(cached, "height", 0)),
            size=_coerce_int(getattr(cached, "size", 0)),
            mtime=_coerce_float(getattr(cached, "mtime", 0)),
            url=_coerce_optional_text(getattr(cached, "url", None)),
            source=_coerce_optional_text(getattr(cached, "source", None)),
            metrics=_normalize_metrics(getattr(cached, "metrics", None)),
        )

    @classmethod
    def from_payload(cls, payload: Any) -> "RecursiveCachedItemSnapshot":
        if not isinstance(payload, dict):
            raise ValueError("invalid cached item payload")
        return cls(
            path=_canonical_scope(str(payload.get("path", ""))),
            name=str(payload.get("name", "")),
            mime=str(payload.get("mime", "image/jpeg")),
            width=_coerce_int(payload.get("width", 0)),
            height=_coerce_int(payload.get("height", 0)),
            size=_coerce_int(payload.get("size", 0)),
            mtime=_coerce_float(payload.get("mtime", 0)),
            url=_coerce_optional_text(payload.get("url")),
            source=_coerce_optional_text(payload.get("source")),
            metrics=_normalize_metrics(payload.get("metrics")),
        )

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path": self.path,
            "name": self.name,
            "mime": self.mime,
            "width": self.width,
            "height": self.height,
            "size": self.size,
            "mtime": self.mtime,
        }
        if self.url:
            payload["url"] = self.url
        if self.source:
            payload["source"] = self.source
        if self.metrics is not None:
            payload["metrics"] = self.metrics
        return payload


def _coerce_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class RecursiveSnapshotWindow:
    scope_path: str
    sort_mode: str
    generation: str
    items: tuple[RecursiveCachedItemSnapshot, ...]

    @property
    def total_items(self) -> int:
        return len(self.items)


class RecursiveBrowseCache:
    """Hybrid in-memory/on-disk cache for recursive browse windows."""

    def __init__(
        self,
        *,
        cache_dir: Path | None = None,
        max_disk_bytes: int = DEFAULT_BROWSE_CACHE_CAP_BYTES,
        max_memory_entries: int = DEFAULT_BROWSE_MEMORY_ENTRY_LIMIT,
    ) -> None:
        self._lock = threading.Lock()
        self._memory: dict[tuple[str, str, str], RecursiveSnapshotWindow] = {}
        self._memory_access: dict[tuple[str, str, str], float] = {}
        self._max_memory_entries = max(1, int(max_memory_entries))
        self._max_disk_bytes = max(0, int(max_disk_bytes))
        self._cache_dir = Path(cache_dir) if cache_dir is not None else None
        self._persistence_enabled = self._enable_persistence()
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
    ) -> tuple[RecursiveSnapshotWindow, bool]:
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
        wrote_disk = self._save_disk_window(window)
        return window, wrote_disk

    def invalidate_path(self, path: str | None = None) -> None:
        if path is None:
            with self._lock:
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

        # Path-scoped disk invalidation would require parsing full entry payloads.
        # For now we clear persisted entries to avoid stale ancestor/descendant reuse.
        self._clear_disk()

    def clear(self) -> None:
        self.invalidate_path(None)

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

    def _enable_persistence(self) -> bool:
        if self._cache_dir is None:
            return False
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            probe = self._cache_dir / ".browse-cache-write-probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return True
        except Exception:
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
        assert self._cache_dir is not None
        return self._cache_dir / digest[:2] / f"{digest}.json.gz"

    def _load_disk_window(
        self,
        scope_path: str,
        sort_mode: str,
        generation: str,
    ) -> RecursiveSnapshotWindow | None:
        try:
            path = self._disk_path_for(scope_path, sort_mode, generation)
        except Exception:
            return None
        if not path.is_file():
            return None
        try:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            return None

        if not isinstance(payload, dict):
            self._safe_unlink(path)
            return None
        if payload.get("schema_version") != CACHE_SCHEMA_VERSION:
            self._safe_unlink(path)
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
        except Exception:
            self._safe_unlink(path)
            return None

        try:
            os.utime(path, None)
        except OSError:
            pass

        return RecursiveSnapshotWindow(
            scope_path=_canonical_scope(scope_path),
            sort_mode=sort_mode,
            generation=generation,
            items=tuple(snapshots),
        )

    def _save_disk_window(self, window: RecursiveSnapshotWindow) -> bool:
        if not self._persistence_enabled:
            return False
        tmp: Path | None = None
        try:
            path = self._disk_path_for(window.scope_path, window.sort_mode, window.generation)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
            payload = {
                "schema_version": CACHE_SCHEMA_VERSION,
                "scope_path": window.scope_path,
                "sort_mode": window.sort_mode,
                "generation": window.generation,
                "items": [item.to_payload() for item in window.items],
            }
            with gzip.open(tmp, "wt", encoding="utf-8") as handle:
                json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
            tmp.replace(path)
            self._evict_disk_to_cap()
            return path.exists()
        except Exception:
            if tmp is not None:
                try:
                    tmp.unlink(missing_ok=True)
                except Exception:
                    pass
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

    def _safe_unlink(self, path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            return
        except Exception:
            return

    def _cleanup_empty_dirs(self) -> None:
        if self._cache_dir is None or not self._cache_dir.exists():
            return
        try:
            candidates = sorted(self._cache_dir.rglob("*"), reverse=True)
        except Exception:
            return
        for path in candidates:
            if not path.is_dir():
                continue
            try:
                path.rmdir()
            except OSError:
                continue
