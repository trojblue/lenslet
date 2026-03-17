"""Browse/search/item helpers shared by Lenslet server modules."""

from __future__ import annotations

import io
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from fastapi import FastAPI, HTTPException, Request

from .browse_cache import RecursiveBrowseCache, RecursiveCachedItemSnapshot
from .metadata import read_jpeg_info, read_png_info, read_webp_info
from .server_context import get_request_context
from .server_models import (
    BrowseFolderEntryPayload,
    BrowseFolderPayload,
    BrowseItemPayload,
    BrowseSearchResultsPayload,
    ImageMetadataResponse,
    Sidecar,
)
from .server_sync import _canonical_path, _sidecar_from_meta
from .storage.base import BrowseItem, BrowseStorage
from .workspace import Workspace


BrowseItemRecord = BrowseItem | RecursiveCachedItemSnapshot
ToItemFn = Callable[[BrowseStorage, BrowseItemRecord], BrowseItemPayload]


def _storage_from_request(request: Request) -> BrowseStorage:
    return get_request_context(request).storage


def _ensure_image(storage: BrowseStorage, path: str) -> None:
    try:
        storage.validate_image_path(path)
    except FileNotFoundError:
        raise HTTPException(404, "file not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))


def _build_sidecar(storage: BrowseStorage, path: str) -> Sidecar:
    meta = storage.get_metadata_readonly(path)
    return _build_sidecar_from_meta(storage, path, meta)


def _build_sidecar_from_meta(storage: BrowseStorage, path: str, meta: dict) -> Sidecar:
    sidecar = _sidecar_from_meta(meta)
    enrichment = storage.sidecar_enrichment_for_path(path)
    if not enrichment:
        return sidecar
    return sidecar.model_copy(update=enrichment)


def _build_image_metadata(storage: BrowseStorage, path: str) -> ImageMetadataResponse:
    mime = storage.guess_mime(path)
    if mime not in ("image/png", "image/jpeg", "image/webp"):
        raise HTTPException(415, "metadata reading supports PNG, JPEG, and WebP images only")

    try:
        raw = storage.read_bytes(path)
        if mime == "image/png":
            meta = read_png_info(io.BytesIO(raw))
            fmt = "png"
        elif mime == "image/jpeg":
            meta = read_jpeg_info(io.BytesIO(raw))
            fmt = "jpeg"
        else:
            meta = read_webp_info(io.BytesIO(raw))
            fmt = "webp"
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - unexpected parse errors
        raise HTTPException(500, f"failed to parse metadata: {exc}")

    return ImageMetadataResponse(path=path, format=fmt, meta=meta)


def _build_item(
    cached: BrowseItemRecord,
    meta: dict[str, Any],
    source: str | None = None,
) -> BrowseItemPayload:
    if source is None:
        source = getattr(cached, "source", None)
    canonical = _canonical_path(cached.path)
    metrics = getattr(cached, "metrics", None)
    if metrics is None:
        metrics = meta.get("metrics")
    added_at = None
    mtime = float(getattr(cached, "mtime", 0) or 0)
    if mtime > 0:
        added_at = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    return BrowseItemPayload(
        path=canonical,
        name=cached.name,
        mime=cached.mime,
        width=cached.width,
        height=cached.height,
        size=cached.size,
        hasThumbnail=True,
        hasMetadata=True,
        addedAt=added_at,
        star=meta.get("star"),
        notes=meta.get("notes", ""),
        url=getattr(cached, "url", None),
        source=source,
        metrics=metrics,
    )


def _child_folder_path(parent: str, child: str) -> str:
    parent_path = _canonical_path(parent)
    return _canonical_path(f"{parent_path.rstrip('/')}/{child}")


def _metric_keys_from_cached_items(cached_items: Iterable[Any]) -> list[str]:
    metric_keys: set[str] = set()
    for cached in cached_items:
        metrics = getattr(cached, "metrics", None)
        if not isinstance(metrics, dict):
            continue
        for raw_key in metrics.keys():
            key = str(raw_key).strip()
            if key:
                metric_keys.add(key)
    return sorted(metric_keys)


def _metric_keys_for_folder(
    storage: BrowseStorage,
    canonical_path: str,
    index: Any,
    *,
    recursive: bool,
    snapshots: Iterable[RecursiveCachedItemSnapshot] | None = None,
) -> list[str]:
    if recursive:
        if snapshots is not None:
            return _metric_keys_from_cached_items(snapshots)
        return _metric_keys_from_cached_items(storage.items_in_scope(canonical_path))
    return _metric_keys_from_cached_items(getattr(index, "items", []) or [])


RECURSIVE_SORT_MODE_SCAN = "scan"
RECURSIVE_CACHE_BUILD_MAX_RETRIES = 2
RECURSIVE_ITEMS_HARD_LIMIT = 10_000


class HotpathTelemetry:
    """Lightweight in-process counters/timers for hot-path visibility."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {}
        self._timers: dict[str, tuple[int, float]] = {}

    def increment(self, key: str, amount: int = 1) -> None:
        if amount == 0:
            return
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + amount

    def observe_ms(self, key: str, duration_ms: float) -> None:
        if duration_ms < 0:
            duration_ms = 0
        with self._lock:
            count, total = self._timers.get(key, (0, 0.0))
            self._timers[key] = (count + 1, total + duration_ms)

    def snapshot(self, storage=None) -> dict[str, Any]:
        with self._lock:
            counters = dict(self._counters)
            timers = {
                key: {
                    "count": count,
                    "total_ms": round(total_ms, 3),
                    "avg_ms": round(total_ms / count, 3) if count else 0.0,
                }
                for key, (count, total_ms) in self._timers.items()
            }
        s3_creations = _storage_s3_client_creations(storage)
        if s3_creations is not None:
            counters["s3_client_create_total"] = s3_creations
        return {
            "counters": counters,
            "timers_ms": timers,
        }


def _create_hotpath_metrics(app: FastAPI) -> HotpathTelemetry:
    metrics = HotpathTelemetry()
    app.state.hotpath_metrics = metrics
    return metrics


def _labels_health_payload(workspace: Workspace, *, writes_enabled: bool | None = None) -> dict[str, Any]:
    if writes_enabled is None:
        writes_enabled = workspace.can_write
    if not writes_enabled:
        return {"enabled": False, "log": None, "snapshot": None}
    return {
        "enabled": True,
        "log": str(workspace.labels_log_path()),
        "snapshot": str(workspace.labels_snapshot_path()),
    }


def _storage_s3_client_creations(storage) -> int | None:
    getter = getattr(storage, "s3_client_creations", None)
    if callable(getter):
        try:
            return int(getter())
        except Exception:
            return None
    raw = getattr(storage, "_s3_client_creations", None)
    if isinstance(raw, int):
        return raw
    return None


def _raise_recursive_items_limit() -> None:
    raise HTTPException(
        413,
        "recursive folder listing exceeds server safety limit; refine the path or use count_only",
    )


def _recursive_items_hard_limit(storage: BrowseStorage) -> int | None:
    try:
        limit = storage.recursive_items_hard_limit()
    except Exception:
        return RECURSIVE_ITEMS_HARD_LIMIT
    if limit is None:
        return None
    try:
        parsed_limit = int(limit)
    except (TypeError, ValueError):
        return RECURSIVE_ITEMS_HARD_LIMIT
    if parsed_limit <= 0:
        return None
    return parsed_limit




def _collect_recursive_cached_items(
    storage: BrowseStorage,
    root_path: str,
    root_index: Any,
    *,
    max_items: int | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> tuple[list[Any], int]:
    queue: deque[tuple[str, Any]] = deque([(_canonical_path(root_path), root_index)])
    seen_folders: set[str] = set()
    seen_items: set[str] = set()
    items: list[tuple[str, Any]] = []
    total_items = 0
    get_index = _recursive_index_getter(storage)

    while queue:
        if cancelled is not None and cancelled():
            break
        folder_path, folder_index = queue.popleft()
        if folder_path in seen_folders:
            continue
        seen_folders.add(folder_path)

        for cached in folder_index.items:
            if cancelled is not None and cancelled():
                break
            item_path = _canonical_path(getattr(cached, "path", ""))
            if item_path in seen_items:
                continue
            seen_items.add(item_path)
            if max_items is not None and total_items >= max_items:
                _raise_recursive_items_limit()
            total_items += 1
            items.append((item_path, cached))

        for child_name in folder_index.dirs:
            if cancelled is not None and cancelled():
                break
            child_path = _child_folder_path(folder_path, child_name)
            if child_path in seen_folders:
                continue
            try:
                child_index = get_index(child_path)
            except (FileNotFoundError, ValueError):
                continue
            if child_index is None:
                continue
            queue.append((child_path, child_index))

    items.sort(key=lambda pair: pair[0])
    return [cached for _, cached in items], total_items


def _recursive_index_getter(storage: BrowseStorage) -> Callable[[str], Any]:
    return storage.get_recursive_index


def _snapshots_from_cached_items(
    cached_items: Iterable[Any],
) -> tuple[RecursiveCachedItemSnapshot, ...]:
    return tuple(
        RecursiveCachedItemSnapshot.from_cached_item(cached)
        for cached in cached_items
    )


def _build_recursive_snapshots(
    storage: BrowseStorage,
    canonical_path: str,
    root_index: Any,
    *,
    max_items: int | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> tuple[tuple[RecursiveCachedItemSnapshot, ...], int]:
    _ = root_index, cancelled
    snapshots = _snapshots_from_cached_items(storage.items_in_scope(canonical_path))
    if max_items is not None and len(snapshots) > max_items:
        _raise_recursive_items_limit()
    return snapshots, len(snapshots)


def _count_recursive_items(
    storage: BrowseStorage,
    canonical_path: str,
    root_index: Any,
) -> int:
    _ = root_index
    return int(storage.count_in_scope(canonical_path))


def _recursive_cache_generation_token(storage: BrowseStorage) -> str:
    parts: list[str] = []
    try:
        signature = str(storage.browse_cache_signature()).strip()
    except Exception:
        signature = ""
    if signature:
        parts.append(signature)

    try:
        generation = str(storage.browse_generation()).strip()
    except Exception:
        generation = ""
    if generation:
        parts.append(generation)

    if not parts:
        return "default"
    return "|".join(parts)


def _load_or_build_recursive_snapshots(
    storage: BrowseStorage,
    canonical_path: str,
    root_index: Any,
    *,
    sort_mode: str,
    browse_cache: RecursiveBrowseCache,
    defer_persist: bool = False,
    hotpath_metrics: HotpathTelemetry | None = None,
) -> tuple[tuple[RecursiveCachedItemSnapshot, ...], int]:
    generation_token = _recursive_cache_generation_token(storage)
    recursive_index = _recursive_index_getter(storage)
    max_items = _recursive_items_hard_limit(storage)
    for _attempt in range(RECURSIVE_CACHE_BUILD_MAX_RETRIES):
        cached_window = browse_cache.load(canonical_path, sort_mode, generation_token)
        if cached_window is not None:
            window, source = cached_window
            if hotpath_metrics is not None:
                hotpath_metrics.increment("folders_recursive_cache_hit_total")
                if source == "disk":
                    hotpath_metrics.increment("folders_recursive_cache_hit_disk_total")
                else:
                    hotpath_metrics.increment("folders_recursive_cache_hit_memory_total")
            return window.items, window.total_items

        if hotpath_metrics is not None:
            hotpath_metrics.increment("folders_recursive_cache_miss_total")

        snapshots, total_items = _build_recursive_snapshots(
            storage,
            canonical_path,
            root_index,
            max_items=max_items,
        )

        latest_generation = _recursive_cache_generation_token(storage)
        if latest_generation != generation_token:
            if hotpath_metrics is not None:
                hotpath_metrics.increment("folders_recursive_cache_stale_generation_total")
            generation_token = latest_generation
            try:
                root_index = recursive_index(canonical_path)
            except (FileNotFoundError, ValueError):
                break
            if root_index is None:
                break
            continue

        _window, wrote_persisted = browse_cache.save(
            canonical_path,
            sort_mode,
            generation_token,
            snapshots,
            defer_persist=defer_persist,
        )
        if hotpath_metrics is not None and wrote_persisted:
            hotpath_metrics.increment("folders_recursive_cache_persist_write_total")
        return snapshots, total_items

    return _build_recursive_snapshots(
        storage,
        canonical_path,
        root_index,
        max_items=max_items,
    )


def warm_recursive_cache(
    storage: BrowseStorage,
    path: str,
    browse_cache: RecursiveBrowseCache | None,
    *,
    hotpath_metrics: HotpathTelemetry | None = None,
) -> int:
    if browse_cache is None:
        return int(storage.count_in_scope(path))
    recursive_index = _recursive_index_getter(storage)
    try:
        root_index = recursive_index(path)
    except (FileNotFoundError, ValueError):
        return 0
    if root_index is None:
        return 0
    canonical_path = _canonical_path(path)
    _snapshots, total_items = _load_or_build_recursive_snapshots(
        storage,
        canonical_path,
        root_index,
        sort_mode=RECURSIVE_SORT_MODE_SCAN,
        browse_cache=browse_cache,
        defer_persist=False,
        hotpath_metrics=hotpath_metrics,
    )
    return total_items


def _build_folder_index(
    storage: BrowseStorage,
    path: str,
    to_item: ToItemFn,
    recursive: bool = False,
    count_only: bool = False,
    browse_cache: RecursiveBrowseCache | None = None,
    hotpath_metrics: HotpathTelemetry | None = None,
) -> BrowseFolderPayload:
    canonical_path = _canonical_path(path)
    try:
        if recursive:
            getter = _recursive_index_getter(storage)
            index = getter(canonical_path)
            if index is None:
                raise FileNotFoundError(canonical_path)
        else:
            index = storage.get_index(canonical_path)
            if index is None:
                raise FileNotFoundError(canonical_path)
    except ValueError:
        raise HTTPException(400, "invalid path")
    except FileNotFoundError:
        raise HTTPException(404, "folder not found")

    snapshots: tuple[RecursiveCachedItemSnapshot, ...] | None = None
    if recursive:
        if hotpath_metrics is not None:
            hotpath_metrics.increment("folders_recursive_requests_total")
        traversal_started = time.perf_counter()
        if count_only:
            total_items = _count_recursive_items(storage, canonical_path, index)
            items = []
        else:
            if browse_cache is not None:
                snapshots, total_items = _load_or_build_recursive_snapshots(
                    storage,
                    canonical_path,
                    index,
                    sort_mode=RECURSIVE_SORT_MODE_SCAN,
                    browse_cache=browse_cache,
                    defer_persist=True,
                    hotpath_metrics=hotpath_metrics,
                )
            else:
                snapshots, total_items = _build_recursive_snapshots(
                    storage,
                    canonical_path,
                    index,
                    max_items=_recursive_items_hard_limit(storage),
                )
            items = [to_item(storage, snapshot) for snapshot in snapshots]
        if hotpath_metrics is not None:
            hotpath_metrics.observe_ms(
                "folders_recursive_traversal_ms",
                (time.perf_counter() - traversal_started) * 1000.0,
            )
            hotpath_metrics.increment("folders_recursive_items_total", total_items)
    else:
        if count_only:
            total_items = len(getattr(index, "items", []) or [])
            items = []
        else:
            items = [to_item(storage, it) for it in index.items]
            total_items = None

    folders = [BrowseFolderEntryPayload(name=d, kind="branch") for d in sorted(index.dirs)]
    metric_keys = _metric_keys_for_folder(
        storage,
        canonical_path,
        index,
        recursive=recursive,
        snapshots=snapshots,
    )

    return BrowseFolderPayload(
        path=canonical_path,
        generatedAt=index.generated_at,
        items=items,
        folders=folders,
        metricKeys=metric_keys,
        page=None,
        pageSize=None,
        pageCount=None,
        totalItems=total_items if count_only else None,
    )


def _search_results(
    storage,
    to_item,
    q: str,
    path: str,
    limit: int,
) -> BrowseSearchResultsPayload:
    hits = storage.search(query=q, path=path, limit=limit)
    return BrowseSearchResultsPayload(items=[to_item(storage, it) for it in hits])
