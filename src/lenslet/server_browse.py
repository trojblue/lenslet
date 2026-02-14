"""Browse/search/item helpers shared by Lenslet server modules."""

from __future__ import annotations

import io
import threading
import time
from collections import deque
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


RECURSIVE_SORT_MODE_SCAN = "scan"
RECURSIVE_CACHE_BUILD_MAX_RETRIES = 2


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




def _collect_recursive_cached_items(
    storage,
    root_path: str,
    root_index: Any,
    *,
    cancelled: Callable[[], bool] | None = None,
) -> tuple[list[Any], int]:
    queue: deque[tuple[str, Any]] = deque([(_canonical_path(root_path), root_index)])
    seen_folders: set[str] = set()
    seen_items: set[str] = set()
    items: list[tuple[str, Any]] = []
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
            items.append((item_path, cached))

        for child_name in folder_index.dirs:
            if cancelled is not None and cancelled():
                break
            child_path = _child_folder_path(folder_path, child_name)
            if child_path in seen_folders:
                continue
            try:
                child_index = storage.get_index(child_path)
            except (FileNotFoundError, ValueError):
                continue
            queue.append((child_path, child_index))

    items.sort(key=lambda pair: pair[0])
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
    )
    snapshots = tuple(
        RecursiveCachedItemSnapshot.from_cached_item(cached)
        for cached in cached_items
    )
    return snapshots, total_items


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
    try:
        index = storage.get_index(path)
    except ValueError:
        raise HTTPException(400, "invalid path")
    except FileNotFoundError:
        raise HTTPException(404, "folder not found")

    if recursive:
        if hotpath_metrics is not None:
            hotpath_metrics.increment("folders_recursive_requests_total")
        traversal_started = time.perf_counter()
        canonical_path = _canonical_path(path)
        if browse_cache is not None:
            snapshots, total_items = _load_or_build_recursive_snapshots(
                storage,
                canonical_path,
                index,
                sort_mode=RECURSIVE_SORT_MODE_SCAN,
                browse_cache=browse_cache,
                hotpath_metrics=hotpath_metrics,
            )
            items = [to_item(storage, snapshot) for snapshot in snapshots]
        else:
            cached_items, total_items = _collect_recursive_cached_items(
                storage,
                canonical_path,
                index,
            )
            items = [to_item(storage, it) for it in cached_items]
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
        page=None,
        pageSize=None,
        pageCount=None,
        totalItems=None,
    )


def _search_results(storage, to_item, q: str, path: str, limit: int) -> SearchResult:
    hits = storage.search(query=q, path=path, limit=limit)
    return SearchResult(items=[to_item(storage, it) for it in hits])
