"""Browse/search/item helpers shared by Lenslet server modules."""

from __future__ import annotations

import io
import math
import os
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request

from .browse_cache import RecursiveBrowseCache, RecursiveCachedItemSnapshot
from .metadata import read_jpeg_info, read_png_info, read_webp_info
from .server_models import DirEntry, FolderIndex, ImageMetadataResponse, Item, SearchResult, Sidecar
from .server_sync import _canonical_path, _sidecar_from_meta
from .workspace import Workspace


def _storage_from_request(request: Request):
    return request.state.storage  # type: ignore[attr-defined]


def _ensure_image(storage, path: str) -> None:
    try:
        storage.validate_image_path(path)
    except FileNotFoundError:
        raise HTTPException(404, "file not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))


def _build_sidecar(storage, path: str) -> Sidecar:
    meta = storage.get_metadata(path)
    return _sidecar_from_meta(meta)


def _build_image_metadata(storage, path: str) -> ImageMetadataResponse:
    mime = storage._guess_mime(path)  # type: ignore[attr-defined]
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


def _build_item(cached, meta: dict, source: str | None = None) -> Item:
    if source is None:
        source = getattr(cached, "source", None)
    canonical = _canonical_path(cached.path)
    metrics = getattr(cached, "metrics", None)
    if metrics is None:
        metrics = meta.get("metrics")
    return Item(
        path=canonical,
        name=cached.name,
        type=cached.mime,
        w=cached.width,
        h=cached.height,
        size=cached.size,
        hasThumb=True,
        hasMeta=True,
        addedAt=datetime.fromtimestamp(cached.mtime, tz=timezone.utc).isoformat(),
        star=meta.get("star"),
        comments=meta.get("notes", ""),
        url=getattr(cached, "url", None),
        source=source,
        metrics=metrics,
    )


def _child_folder_path(parent: str, child: str) -> str:
    parent_path = _canonical_path(parent)
    return _canonical_path(f"{parent_path.rstrip('/')}/{child}")


RECURSIVE_PAGE_DEFAULT = 1
RECURSIVE_PAGE_SIZE_DEFAULT = 200
RECURSIVE_PAGE_SIZE_MAX = 500
RECURSIVE_WINDOW_INSERT_MAX = 4096
RECURSIVE_SORT_MODE_SCAN = "scan"
RECURSIVE_CACHE_BUILD_MAX_RETRIES = 2
# Keep background full-snapshot warm/persist out of the first interactive
# browse window so initial scroll responsiveness is not CPU-contended.
RECURSIVE_CACHE_WARM_DELAY_SECONDS = 10.0
LEGACY_RECURSIVE_ROLLBACK_ENV = "LENSLET_ENABLE_LEGACY_RECURSIVE_ROLLBACK"
_LEGACY_RECURSIVE_ROLLBACK_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True)
class _RecursivePaginationWindow:
    page: int
    page_size: int
    page_count: int
    total_items: int
    start: int
    end: int


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


def _labels_health_payload(workspace: Workspace) -> dict[str, Any]:
    if not workspace.can_write:
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


def _parse_recursive_pagination_value(name: str, raw: str | None, default: int) -> int:
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(400, f"{name} must be an integer")
    if value <= 0:
        raise HTTPException(400, f"{name} must be >= 1")
    return value


def _resolve_recursive_pagination(page: str | None, page_size: str | None) -> tuple[int, int]:
    resolved_page = _parse_recursive_pagination_value("page", page, RECURSIVE_PAGE_DEFAULT)
    resolved_page_size = _parse_recursive_pagination_value(
        "page_size",
        page_size,
        RECURSIVE_PAGE_SIZE_DEFAULT,
    )
    if resolved_page_size > RECURSIVE_PAGE_SIZE_MAX:
        resolved_page_size = RECURSIVE_PAGE_SIZE_MAX
    return resolved_page, resolved_page_size


def _legacy_recursive_rollbacks_enabled() -> bool:
    raw = os.getenv(LEGACY_RECURSIVE_ROLLBACK_ENV, "").strip().lower()
    return raw in _LEGACY_RECURSIVE_ROLLBACK_TRUE_VALUES


def _recursive_window_from_values(
    total_items: int,
    page: int,
    page_size: int,
) -> _RecursivePaginationWindow:
    page_count = max(1, math.ceil(total_items / page_size))
    start = (page - 1) * page_size
    end = start + page_size
    return _RecursivePaginationWindow(
        page=page,
        page_size=page_size,
        page_count=page_count,
        total_items=total_items,
        start=start,
        end=end,
    )


def _insert_recursive_window_item(
    sorted_items: list[tuple[str, Any]],
    *,
    path: str,
    cached: Any,
    limit: int,
) -> None:
    if limit <= 0:
        return
    if len(sorted_items) >= limit and path >= sorted_items[-1][0]:
        return

    lo = 0
    hi = len(sorted_items)
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_items[mid][0] <= path:
            lo = mid + 1
        else:
            hi = mid
    sorted_items.insert(lo, (path, cached))
    if len(sorted_items) > limit:
        sorted_items.pop()


def _storage_recursive_index(storage, path: str):
    getter = getattr(storage, "get_index_for_recursive", None)
    if callable(getter):
        return getter(path)
    return storage.get_index(path)


def _hydrate_recursive_page_items(storage, items: list[Any]) -> list[Any]:
    hydrate_fn = getattr(storage, "hydrate_recursive_items", None)
    if not callable(hydrate_fn):
        return items
    try:
        hydrated = hydrate_fn(items)
    except Exception:
        return items
    if isinstance(hydrated, list):
        return hydrated
    return items


def _collect_recursive_cached_items(
    storage,
    root_path: str,
    root_index: Any,
    *,
    limit: int | None = None,
    cancelled: Callable[[], bool] | None = None,
    use_recursive_index: bool = False,
) -> tuple[list[Any], int]:
    queue: deque[tuple[str, Any]] = deque([(_canonical_path(root_path), root_index)])
    seen_folders: set[str] = set()
    seen_items: set[str] = set()
    items: list[tuple[str, Any]] = []
    use_window_insert = limit is not None and limit <= RECURSIVE_WINDOW_INSERT_MAX
    total_items = 0

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
            total_items += 1
            if limit is None:
                items.append((item_path, cached))
            elif use_window_insert:
                _insert_recursive_window_item(
                    items,
                    path=item_path,
                    cached=cached,
                    limit=limit,
                )
            else:
                items.append((item_path, cached))

        for child_name in folder_index.dirs:
            if cancelled is not None and cancelled():
                break
            child_path = _child_folder_path(folder_path, child_name)
            if child_path in seen_folders:
                continue
            try:
                if use_recursive_index:
                    child_index = _storage_recursive_index(storage, child_path)
                else:
                    child_index = storage.get_index(child_path)
            except (FileNotFoundError, ValueError):
                continue
            queue.append((child_path, child_index))

    if limit is None:
        items.sort(key=lambda pair: pair[0])
    elif not use_window_insert:
        items.sort(key=lambda pair: pair[0])
        items = items[:limit]
    return [cached for _, cached in items], total_items


def _recursive_cache_generation_token(storage) -> str:
    parts: list[str] = []
    signature_fn = getattr(storage, "browse_cache_signature", None)
    if callable(signature_fn):
        try:
            signature = str(signature_fn()).strip()
        except Exception:
            signature = ""
        if signature:
            parts.append(signature)

    generation_fn = getattr(storage, "browse_generation", None)
    if callable(generation_fn):
        try:
            generation = str(generation_fn()).strip()
        except Exception:
            generation = ""
        if generation:
            parts.append(generation)

    if not parts:
        return "default"
    return "|".join(parts)


def _load_or_build_recursive_snapshots(
    storage,
    canonical_path: str,
    root_index: Any,
    *,
    sort_mode: str,
    browse_cache: RecursiveBrowseCache,
    hotpath_metrics: HotpathTelemetry | None = None,
) -> tuple[tuple[RecursiveCachedItemSnapshot, ...], int]:
    generation_token = _recursive_cache_generation_token(storage)
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

        cached_items, total_items = _collect_recursive_cached_items(
            storage,
            canonical_path,
            root_index,
            use_recursive_index=False,
        )
        snapshots = tuple(
            RecursiveCachedItemSnapshot.from_cached_item(cached)
            for cached in cached_items
        )

        latest_generation = _recursive_cache_generation_token(storage)
        if latest_generation != generation_token:
            if hotpath_metrics is not None:
                hotpath_metrics.increment("folders_recursive_cache_stale_generation_total")
            generation_token = latest_generation
            try:
                root_index = storage.get_index(canonical_path)
            except (FileNotFoundError, ValueError):
                break
            continue

        _window, wrote_persisted = browse_cache.save(
            canonical_path,
            sort_mode,
            generation_token,
            snapshots,
        )
        if hotpath_metrics is not None and wrote_persisted:
            hotpath_metrics.increment("folders_recursive_cache_persist_write_total")
        return snapshots, total_items

    cached_items, total_items = _collect_recursive_cached_items(
        storage,
        canonical_path,
        root_index,
        use_recursive_index=False,
    )
    snapshots = tuple(
        RecursiveCachedItemSnapshot.from_cached_item(cached)
        for cached in cached_items
    )
    return snapshots, total_items


def _load_or_build_recursive_page_snapshots(
    storage,
    canonical_path: str,
    root_index: Any,
    *,
    page: int,
    page_size: int,
    sort_mode: str,
    browse_cache: RecursiveBrowseCache,
    hotpath_metrics: HotpathTelemetry | None = None,
) -> tuple[tuple[RecursiveCachedItemSnapshot, ...], int]:
    window_start = (page - 1) * page_size
    window_end = window_start + page_size
    generation_token = _recursive_cache_generation_token(storage)

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
            return window.items[window_start:window_end], window.total_items

        if hotpath_metrics is not None:
            hotpath_metrics.increment("folders_recursive_cache_miss_total")

        cached_items, total_items = _collect_recursive_cached_items(
            storage,
            canonical_path,
            root_index,
            limit=window_end,
            use_recursive_index=True,
        )
        page_items = cached_items[window_start:window_end]
        page_items = _hydrate_recursive_page_items(storage, page_items)
        page_snapshots = tuple(
            RecursiveCachedItemSnapshot.from_cached_item(cached)
            for cached in page_items
        )

        latest_generation = _recursive_cache_generation_token(storage)
        if latest_generation != generation_token:
            if hotpath_metrics is not None:
                hotpath_metrics.increment("folders_recursive_cache_stale_generation_total")
            generation_token = latest_generation
            try:
                root_index = _storage_recursive_index(storage, canonical_path)
            except (FileNotFoundError, ValueError):
                break
            continue

        if total_items <= len(cached_items):
            cached_items = _hydrate_recursive_page_items(storage, cached_items)
            snapshots = tuple(
                RecursiveCachedItemSnapshot.from_cached_item(cached)
                for cached in cached_items
            )
            _, wrote_persisted = browse_cache.save(
                canonical_path,
                sort_mode,
                generation_token,
                snapshots,
            )
            if hotpath_metrics is not None and wrote_persisted:
                hotpath_metrics.increment("folders_recursive_cache_persist_write_total")
            return page_snapshots, total_items

        expected_generation = generation_token

        def _warm_producer(cancel_event: threading.Event):
            if cancel_event.is_set():
                if hotpath_metrics is not None:
                    hotpath_metrics.increment("folders_recursive_cache_warm_cancel_total")
                return None
            try:
                warm_root = _storage_recursive_index(storage, canonical_path)
            except (FileNotFoundError, ValueError):
                return None
            warm_items, _ = _collect_recursive_cached_items(
                storage,
                canonical_path,
                warm_root,
                cancelled=cancel_event.is_set,
                use_recursive_index=True,
            )
            if cancel_event.is_set():
                if hotpath_metrics is not None:
                    hotpath_metrics.increment("folders_recursive_cache_warm_cancel_total")
                return None
            latest = _recursive_cache_generation_token(storage)
            if latest != expected_generation:
                if hotpath_metrics is not None:
                    hotpath_metrics.increment("folders_recursive_cache_stale_generation_total")
                return None
            return tuple(
                RecursiveCachedItemSnapshot.from_cached_item(cached)
                for cached in warm_items
            )

        def _on_saved(wrote_persisted: bool) -> None:
            if hotpath_metrics is not None:
                hotpath_metrics.increment("folders_recursive_cache_warm_complete_total")
                if wrote_persisted:
                    hotpath_metrics.increment("folders_recursive_cache_persist_write_total")

        scheduled = browse_cache.schedule_warm(
            canonical_path,
            sort_mode,
            expected_generation,
            _warm_producer,
            delay_seconds=RECURSIVE_CACHE_WARM_DELAY_SECONDS,
            on_saved=_on_saved,
        )
        if hotpath_metrics is not None:
            if scheduled:
                hotpath_metrics.increment("folders_recursive_cache_warm_schedule_total")
            else:
                hotpath_metrics.increment("folders_recursive_cache_warm_skip_total")
        return page_snapshots, total_items

    cached_items, total_items = _collect_recursive_cached_items(
        storage,
        canonical_path,
        root_index,
        limit=window_end,
        use_recursive_index=True,
    )
    page_items = cached_items[window_start:window_end]
    page_items = _hydrate_recursive_page_items(storage, page_items)
    page_snapshots = tuple(
        RecursiveCachedItemSnapshot.from_cached_item(cached)
        for cached in page_items
    )
    return page_snapshots, total_items


def _build_folder_index(
    storage,
    path: str,
    to_item,
    recursive: bool = False,
    page: str | None = None,
    page_size: str | None = None,
    legacy_recursive: bool = False,
    browse_cache: RecursiveBrowseCache | None = None,
    hotpath_metrics: HotpathTelemetry | None = None,
) -> FolderIndex:
    if recursive and legacy_recursive and not _legacy_recursive_rollbacks_enabled():
        raise HTTPException(
            400,
            (
                "legacy_recursive=1 is retired for UI stability. "
                f"Set {LEGACY_RECURSIVE_ROLLBACK_ENV}=1 to temporarily re-enable."
            ),
        )

    try:
        if recursive and not legacy_recursive:
            index = _storage_recursive_index(storage, path)
        else:
            index = storage.get_index(path)
    except ValueError:
        raise HTTPException(400, "invalid path")
    except FileNotFoundError:
        raise HTTPException(404, "folder not found")

    page_window: _RecursivePaginationWindow | None = None
    if recursive:
        if hotpath_metrics is not None:
            hotpath_metrics.increment("folders_recursive_requests_total")
        traversal_started = time.perf_counter()
        canonical_path = _canonical_path(path)
        resolved_page: int | None = None
        resolved_page_size: int | None = None
        if not legacy_recursive:
            resolved_page, resolved_page_size = _resolve_recursive_pagination(page, page_size)
        if browse_cache is not None:
            if legacy_recursive:
                snapshots, total_items = _load_or_build_recursive_snapshots(
                    storage,
                    canonical_path,
                    index,
                    sort_mode=RECURSIVE_SORT_MODE_SCAN,
                    browse_cache=browse_cache,
                    hotpath_metrics=hotpath_metrics,
                )
                snapshots_for_page = snapshots
            else:
                assert resolved_page is not None and resolved_page_size is not None
                snapshots_for_page, total_items = _load_or_build_recursive_page_snapshots(
                    storage,
                    canonical_path,
                    index,
                    page=resolved_page,
                    page_size=resolved_page_size,
                    sort_mode=RECURSIVE_SORT_MODE_SCAN,
                    browse_cache=browse_cache,
                    hotpath_metrics=hotpath_metrics,
                )
                page_window = _recursive_window_from_values(
                    total_items=total_items,
                    page=resolved_page,
                    page_size=resolved_page_size,
                )
                snapshots_for_page = _hydrate_recursive_page_items(storage, list(snapshots_for_page))
            items = [to_item(storage, snapshot) for snapshot in snapshots_for_page]
        else:
            if legacy_recursive:
                cached_items, total_items = _collect_recursive_cached_items(
                    storage,
                    canonical_path,
                    index,
                    use_recursive_index=False,
                )
                items = [to_item(storage, it) for it in cached_items]
            else:
                assert resolved_page is not None and resolved_page_size is not None
                window_end = resolved_page * resolved_page_size
                cached_items, total_items = _collect_recursive_cached_items(
                    storage,
                    canonical_path,
                    index,
                    limit=window_end,
                    use_recursive_index=True,
                )
                page_window = _recursive_window_from_values(
                    total_items=total_items,
                    page=resolved_page,
                    page_size=resolved_page_size,
                )
                page_items = cached_items[page_window.start:page_window.end]
                page_items = _hydrate_recursive_page_items(storage, page_items)
                items = [to_item(storage, it) for it in page_items]
        if hotpath_metrics is not None:
            hotpath_metrics.observe_ms(
                "folders_recursive_traversal_ms",
                (time.perf_counter() - traversal_started) * 1000.0,
            )
            hotpath_metrics.increment("folders_recursive_items_total", total_items)
    else:
        items = [to_item(storage, it) for it in index.items]

    dirs = [DirEntry(name=d, kind="branch") for d in sorted(index.dirs)]

    return FolderIndex(
        path=_canonical_path(path),
        generatedAt=index.generated_at,
        items=items,
        dirs=dirs,
        page=page_window.page if page_window else None,
        pageSize=page_window.page_size if page_window else None,
        pageCount=page_window.page_count if page_window else None,
        totalItems=page_window.total_items if page_window else None,
    )


def _search_results(storage, to_item, q: str, path: str, limit: int) -> SearchResult:
    hits = storage.search(query=q, path=path, limit=limit)
    return SearchResult(items=[to_item(storage, it) for it in hits])
