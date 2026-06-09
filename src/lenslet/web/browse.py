"""Browse/search/item helpers shared by Lenslet server modules."""

from __future__ import annotations

import io
import time
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, cast

from fastapi import HTTPException, Request

from ..browse.query import (
    BrowseQueryFolderEntry,
    BrowseQueryRecord,
    BrowseQueryResult,
    BrowseQuerySpec,
    browse_query_request_token,
    evaluate_browse_records,
)
from ..metrics import normalize_metric_mapping
from ..media_errors import MediaDecodeError, MediaError, MediaReadError
from .cache.browse import (
    CACHE_PERSIST_QUEUED,
    CACHE_PERSIST_SKIPPED,
    CACHE_PERSIST_WRITTEN,
    RecursiveBrowseCache,
    RecursiveCachePersistStatus,
    RecursiveCachedItemSnapshot,
)
from .metadata import read_jpeg_info, read_png_info, read_webp_info
from .context import get_request_context
from .generation import build_browse_generation_token
from .hotpath import HotpathTelemetry
from .media import media_failure_to_http_error
from .models import (
    BrowseFolderEntryPayload,
    BrowseFolderPayload,
    BrowseItemPayload,
    BrowseQueryResponse,
    BrowseSearchResultsPayload,
    BrowseFacetsPayload,
    CategoricalFacetPayload,
    CategoricalValueFacetPayload,
    ImageMetadataResponse,
    MetricFacetPayload,
    MetricHistogramFacetPayload,
    MetricCategoryFacetPayload,
    Sidecar,
)
from .paths import canonical_path
from .sidecars import sidecar_from_state
from ..storage.base import (
    BrowseAppStorage,
    BrowseItem,
    BrowseQueryStorage,
    BrowseStorage,
    BrowseWindowStorage,
    RecursiveLimitStorage,
    SearchStorage,
    SidecarState,
    SidecarStorage,
)
from ..storage.search_text import build_search_haystack, sidecar_source_fields


BrowseItemRecord = BrowseItem | RecursiveCachedItemSnapshot
ToItemFn = Callable[[BrowseStorage, BrowseItemRecord], BrowseItemPayload]


def storage_from_request(request: Request) -> BrowseAppStorage:
    return get_request_context(request).storage


def ensure_image(storage: BrowseStorage, path: str) -> None:
    try:
        storage.validate_image_path(path)
    except FileNotFoundError as exc:
        raise HTTPException(404, "file not found") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def build_sidecar(storage: SidecarStorage, path: str) -> Sidecar:
    sidecar_state = storage.get_sidecar_readonly(path)
    return build_sidecar_from_state(storage, path, sidecar_state)


def build_sidecar_from_state(storage: SidecarStorage, path: str, sidecar_state: SidecarState) -> Sidecar:
    sidecar = sidecar_from_state(sidecar_state)
    enrichment = storage.sidecar_enrichment_for_path(path)
    if not enrichment:
        return sidecar
    return sidecar.model_copy(update=enrichment)


def build_image_metadata(storage: BrowseStorage, path: str) -> ImageMetadataResponse:
    mime = storage.guess_mime(path)
    if mime not in ("image/png", "image/jpeg", "image/webp"):
        raise HTTPException(415, "metadata reading supports PNG, JPEG, and WebP images only")

    try:
        raw = storage.read_bytes(path)
    except HTTPException:
        raise
    except (FileNotFoundError, MediaError) as exc:
        raise media_failure_to_http_error(exc) from exc
    except (OSError, ValueError) as exc:
        raise media_failure_to_http_error(MediaReadError.from_exception(path, exc)) from exc

    try:
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
        raise media_failure_to_http_error(MediaDecodeError.from_exception(path, exc)) from exc

    return ImageMetadataResponse(path=path, format=fmt, meta=meta)


def build_item_payload(
    cached: BrowseItemRecord,
    sidecar_state: SidecarState,
    source: str | None = None,
    categoricals: dict[str, str] | None = None,
) -> BrowseItemPayload:
    if source is None:
        source = getattr(cached, "source", None)
    canonical = canonical_path(cached.path)
    raw_metrics = getattr(cached, "metrics", None)
    if raw_metrics is None:
        raw_metrics = sidecar_state.get("metrics")
    metrics = normalize_metric_mapping(raw_metrics)
    metric_labels = getattr(cached, "metric_labels", None)
    if categoricals is None:
        categoricals = getattr(cached, "categoricals", None)
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
        has_thumbnail=True,
        has_metadata=True,
        added_at=added_at,
        star=sidecar_state.get("star"),
        notes=sidecar_state.get("notes", ""),
        url=getattr(cached, "url", None),
        source=source,
        metrics=metrics,
        metric_labels=metric_labels or None,
        categoricals=categoricals or None,
    )


def categoricals_for_cached_item(storage: BrowseStorage, cached: BrowseItemRecord) -> dict[str, str] | None:
    getter = getattr(storage, "categoricals_for_path", None)
    if callable(getter):
        categoricals = getter(cached.path)
        return categoricals or None
    categoricals = getattr(cached, "categoricals", None)
    return categoricals or None


def _metric_keys_from_cached_items(cached_items: Iterable[Any]) -> list[str]:
    metric_keys: set[str] = set()
    for cached in cached_items:
        metrics = normalize_metric_mapping(getattr(cached, "metrics", None))
        if not isinstance(metrics, dict):
            continue
        for raw_key in metrics.keys():
            key = str(raw_key).strip()
            if key:
                metric_keys.add(key)
    return sorted(metric_keys)


def _categorical_keys_from_cached_items(cached_items: Iterable[Any]) -> list[str]:
    categorical_keys: set[str] = set()
    for cached in cached_items:
        categoricals = getattr(cached, "categoricals", None)
        if not isinstance(categoricals, dict):
            continue
        for raw_key in categoricals.keys():
            key = str(raw_key).strip()
            if key:
                categorical_keys.add(key)
    return sorted(categorical_keys)


def _categorical_keys_from_storage(storage: BrowseStorage) -> list[str] | None:
    getter = getattr(storage, "categorical_keys", None)
    if not callable(getter):
        return None
    keys: set[str] = set()
    for raw_key in getter():
        key = str(raw_key).strip()
        if key:
            keys.add(key)
    return sorted(keys)


def _metric_keys_from_storage(storage: BrowseStorage) -> list[str] | None:
    getter = getattr(storage, "metric_keys", None)
    if not callable(getter):
        return None
    keys: set[str] = set()
    for raw_key in getter():
        key = str(raw_key).strip()
        if key:
            keys.add(key)
    return sorted(keys)


def _metric_keys_for_folder(
    storage: BrowseStorage,
    canonical_path: str,
    index: Any,
    *,
    recursive: bool,
    snapshots: Iterable[RecursiveCachedItemSnapshot] | None = None,
) -> list[str]:
    storage_keys = _metric_keys_from_storage(storage)
    if storage_keys is not None:
        return storage_keys
    if recursive:
        if snapshots is not None:
            return _metric_keys_from_cached_items(snapshots)
        return _metric_keys_from_cached_items(storage.items_in_scope(canonical_path))
    return _metric_keys_from_cached_items(getattr(index, "items", []) or [])


def _categorical_keys_for_folder(
    storage: BrowseStorage,
    canonical_path: str,
    index: Any,
    *,
    recursive: bool,
    snapshots: Iterable[RecursiveCachedItemSnapshot] | None = None,
) -> list[str]:
    storage_keys = _categorical_keys_from_storage(storage)
    if storage_keys is not None:
        return storage_keys
    if recursive:
        if snapshots is not None:
            return _categorical_keys_from_cached_items(snapshots)
        return _categorical_keys_from_cached_items(storage.items_in_scope(canonical_path))
    return _categorical_keys_from_cached_items(getattr(index, "items", []) or [])


FACET_HISTOGRAM_BINS = 40


def _histogram_payload(values: list[float], bins: int = FACET_HISTOGRAM_BINS) -> MetricHistogramFacetPayload | None:
    if not values:
        return None
    safe_bins = max(1, bins)
    min_value = min(values)
    max_value = max(values)
    if min_value == max_value:
        max_value = min_value + 1
    counts = [0] * safe_bins
    scale = safe_bins / (max_value - min_value)
    for value in values:
        idx = max(0, min(safe_bins - 1, int((value - min_value) * scale)))
        counts[idx] += 1
    return MetricHistogramFacetPayload(
        bins=counts,
        min=min_value,
        max=max_value,
        count=len(values),
    )


def _facets_from_items(
    storage: BrowseStorage,
    canonical: str,
    index: Any,
    *,
    recursive: bool,
) -> BrowseFacetsPayload:
    raw_items = (
        storage.items_in_scope(canonical)
        if recursive
        else list(getattr(index, "items", []) or [])
    )
    metric_values: dict[str, list[float]] = {}
    metric_categories: dict[str, dict[tuple[float, str], int]] = {}
    categorical_counts: dict[str, dict[str, int]] = {}

    for item in raw_items:
        metrics = normalize_metric_mapping(getattr(item, "metrics", None))
        metric_labels = getattr(item, "metric_labels", None)
        if isinstance(metrics, dict):
            for key, value in metrics.items():
                metric_values.setdefault(key, []).append(value)
                label = metric_labels.get(key) if isinstance(metric_labels, dict) else None
                if label:
                    category_key = (value, str(label))
                    categories = metric_categories.setdefault(key, {})
                    categories[category_key] = categories.get(category_key, 0) + 1
        categoricals = categoricals_for_cached_item(storage, item)
        if isinstance(categoricals, dict):
            for key, raw_value in categoricals.items():
                value = str(raw_value).strip()
                if not value:
                    continue
                counts = categorical_counts.setdefault(key, {})
                counts[value] = counts.get(value, 0) + 1

    metric_keys = sorted(set(_metric_keys_for_folder(storage, canonical, index, recursive=recursive)) | set(metric_values))
    categorical_keys = sorted(
        set(_categorical_keys_for_folder(storage, canonical, index, recursive=recursive))
        | set(categorical_counts)
    )
    return BrowseFacetsPayload(
        path=canonical,
        generated_at=index.generated_at,
        total_items=len(raw_items),
        metric_keys=metric_keys,
        categorical_keys=categorical_keys,
        metrics={
            key: MetricFacetPayload(
                histogram=_histogram_payload(values),
                categories=[
                    MetricCategoryFacetPayload(
                        code=code,
                        label=label,
                        population_count=count,
                    )
                    for (code, label), count in sorted(
                        metric_categories.get(key, {}).items(),
                        key=lambda item: (item[0][0], item[0][1]),
                    )
                ],
            )
            for key, values in metric_values.items()
        },
        categoricals={
            key: CategoricalFacetPayload(
                values=[
                    CategoricalValueFacetPayload(value=value, population_count=count)
                    for value, count in sorted(
                        counts.items(),
                        key=lambda item: (-item[1], item[0]),
                    )
                ]
            )
            for key, counts in categorical_counts.items()
        },
    )


def build_folder_facets(
    storage: BrowseStorage,
    path: str,
    *,
    recursive: bool = True,
) -> BrowseFacetsPayload:
    canonical = canonical_path(path)
    index = _load_folder_index(storage, canonical, recursive=recursive)
    facet_provider = getattr(storage, "facet_summary_for_scope", None)
    if callable(facet_provider):
        return BrowseFacetsPayload.model_validate(
            facet_provider(canonical, recursive=recursive, bins=FACET_HISTOGRAM_BINS)
        )
    return _facets_from_items(storage, canonical, index, recursive=recursive)


RECURSIVE_SORT_MODE_SCAN = "scan"
RECURSIVE_CACHE_BUILD_MAX_RETRIES = 2
RECURSIVE_ITEMS_HARD_LIMIT = 10_000
RECURSIVE_WINDOW_MAX_LIMIT = 10_000
BROWSE_QUERY_FALLBACK_MAX_ITEMS = 10_000


def _raise_recursive_items_limit() -> None:
    raise HTTPException(
        413,
        "recursive folder listing exceeds server safety limit; refine the path or use count_only",
    )


def _raise_browse_query_fallback_limit() -> None:
    raise HTTPException(
        413,
        "browse query fallback exceeds server safety limit; backend row-query support is required for larger scopes",
    )


def _recursive_items_hard_limit(storage: RecursiveLimitStorage) -> int | None:
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


def _snapshots_from_cached_items(
    cached_items: Iterable[Any],
) -> tuple[RecursiveCachedItemSnapshot, ...]:
    return tuple(
        RecursiveCachedItemSnapshot.from_cached_item(cached)
        for cached in cached_items
    )


def _items_in_scope_window(
    storage: BrowseStorage,
    canonical_path: str,
    *,
    offset: int,
    limit: int,
) -> list[Any]:
    window_loader = getattr(storage, "items_in_scope_window", None)
    if callable(window_loader):
        window_storage = cast(BrowseWindowStorage, storage)
        return list(window_storage.items_in_scope_window(canonical_path, offset, limit))
    return list(storage.items_in_scope(canonical_path))[offset:offset + limit]


def _validate_recursive_window(offset: int, limit: int | None) -> None:
    if offset < 0:
        raise HTTPException(400, "offset must be greater than or equal to 0")
    if limit is None:
        return
    if limit <= 0:
        raise HTTPException(400, "limit must be greater than 0")
    if limit > RECURSIVE_WINDOW_MAX_LIMIT:
        raise HTTPException(400, f"limit must be less than or equal to {RECURSIVE_WINDOW_MAX_LIMIT}")


def _build_recursive_snapshots(
    storage: BrowseStorage,
    canonical_path: str,
    *,
    max_items: int | None = None,
) -> tuple[tuple[RecursiveCachedItemSnapshot, ...], int]:
    if max_items is not None:
        try:
            total_items = int(storage.count_in_scope(canonical_path))
        except AttributeError:
            snapshots = _snapshots_from_cached_items(storage.items_in_scope(canonical_path))
            if len(snapshots) > max_items:
                _raise_recursive_items_limit()
            return snapshots, len(snapshots)
        if total_items > max_items:
            _raise_recursive_items_limit()
        snapshots = _snapshots_from_cached_items(storage.items_in_scope(canonical_path))
        return snapshots, total_items

    snapshots = _snapshots_from_cached_items(storage.items_in_scope(canonical_path))
    return snapshots, len(snapshots)


def _count_recursive_items(
    storage: BrowseStorage,
    canonical_path: str,
) -> int:
    return int(storage.count_in_scope(canonical_path))


def _build_recursive_window_snapshots(
    storage: BrowseStorage,
    canonical_path: str,
    *,
    offset: int,
    limit: int,
) -> tuple[tuple[RecursiveCachedItemSnapshot, ...], int]:
    total_items = _count_recursive_items(storage, canonical_path)
    if offset >= total_items:
        return (), total_items
    cached_items = _items_in_scope_window(
        storage,
        canonical_path,
        offset=offset,
        limit=limit,
    )
    return _snapshots_from_cached_items(cached_items), total_items


def _record_recursive_cache_persist_status(
    hotpath_metrics: HotpathTelemetry,
    status: RecursiveCachePersistStatus,
) -> None:
    if status == CACHE_PERSIST_WRITTEN:
        hotpath_metrics.increment("folders_recursive_cache_persist_write_total")
    elif status == CACHE_PERSIST_QUEUED:
        hotpath_metrics.increment("folders_recursive_cache_persist_queued_total")
    elif status == CACHE_PERSIST_SKIPPED:
        hotpath_metrics.increment("folders_recursive_cache_persist_skipped_total")


def _load_or_build_recursive_snapshots(
    storage: BrowseStorage,
    canonical_path: str,
    *,
    sort_mode: str,
    browse_cache: RecursiveBrowseCache,
    defer_persist: bool = False,
    hotpath_metrics: HotpathTelemetry | None = None,
) -> tuple[tuple[RecursiveCachedItemSnapshot, ...], int]:
    generation_token = build_browse_generation_token(storage)
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
            max_items=max_items,
        )

        latest_generation = build_browse_generation_token(storage)
        if latest_generation != generation_token:
            if hotpath_metrics is not None:
                hotpath_metrics.increment("folders_recursive_cache_stale_generation_total")
            generation_token = latest_generation
            try:
                latest_index = storage.load_recursive_index(canonical_path)
            except (FileNotFoundError, ValueError):
                break
            if latest_index is None:
                break
            continue

        _window, persist_status = browse_cache.save(
            canonical_path,
            sort_mode,
            generation_token,
            snapshots,
            defer_persist=defer_persist,
        )
        if hotpath_metrics is not None:
            _record_recursive_cache_persist_status(hotpath_metrics, persist_status)
        return snapshots, total_items

    return _build_recursive_snapshots(
        storage,
        canonical_path,
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
    try:
        root_index = storage.load_recursive_index(path)
    except (FileNotFoundError, ValueError):
        return 0
    if root_index is None:
        return 0
    canonical = canonical_path(path)
    max_items = _recursive_items_hard_limit(storage)
    if max_items is not None:
        total_items = _count_recursive_items(storage, canonical)
        if total_items > max_items:
            return total_items
    _snapshots, total_items = _load_or_build_recursive_snapshots(
        storage,
        canonical,
        sort_mode=RECURSIVE_SORT_MODE_SCAN,
        browse_cache=browse_cache,
        defer_persist=False,
        hotpath_metrics=hotpath_metrics,
    )
    return total_items


def _load_folder_index(storage: BrowseStorage, canonical: str, *, recursive: bool) -> Any:
    try:
        if recursive:
            index = storage.load_recursive_index(canonical)
        else:
            index = storage.load_index(canonical)
        if index is None:
            raise FileNotFoundError(canonical)
        return index
    except ValueError as exc:
        raise HTTPException(400, "invalid path") from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, "folder not found") from exc


def _folder_entries(index: Any) -> list[BrowseFolderEntryPayload]:
    return [BrowseFolderEntryPayload(name=d, kind="branch") for d in sorted(index.dirs)]


def _direct_folder_total_items(index: Any) -> int:
    total_items = getattr(index, "total_items", None)
    if isinstance(total_items, int):
        return total_items
    return len(getattr(index, "items", []) or [])


def _build_direct_folder_payload(
    storage: BrowseStorage,
    canonical: str,
    index: Any,
    to_item: ToItemFn,
    *,
    count_only: bool,
) -> BrowseFolderPayload:
    if count_only:
        return BrowseFolderPayload(
            path=canonical,
            generated_at=index.generated_at,
            items=[],
            folders=_folder_entries(index),
            metric_keys=[],
            categorical_keys=[],
            total_items=_direct_folder_total_items(index),
        )

    return BrowseFolderPayload(
        path=canonical,
        generated_at=index.generated_at,
        items=[to_item(storage, it) for it in index.items],
        folders=_folder_entries(index),
        metric_keys=_metric_keys_for_folder(storage, canonical, index, recursive=False),
        categorical_keys=_categorical_keys_for_folder(storage, canonical, index, recursive=False),
        total_items=None,
    )


def _load_recursive_payload_snapshots(
    storage: BrowseStorage,
    canonical: str,
    browse_cache: RecursiveBrowseCache | None,
    hotpath_metrics: HotpathTelemetry | None,
) -> tuple[tuple[RecursiveCachedItemSnapshot, ...], int]:
    if browse_cache is not None:
        return _load_or_build_recursive_snapshots(
            storage,
            canonical,
            sort_mode=RECURSIVE_SORT_MODE_SCAN,
            browse_cache=browse_cache,
            defer_persist=True,
            hotpath_metrics=hotpath_metrics,
        )
    return _build_recursive_snapshots(
        storage,
        canonical,
        max_items=_recursive_items_hard_limit(storage),
    )


def _record_recursive_traversal(
    hotpath_metrics: HotpathTelemetry | None,
    traversal_started: float,
    total_items: int,
) -> None:
    if hotpath_metrics is None:
        return
    hotpath_metrics.observe_ms(
        "folders_recursive_traversal_ms",
        (time.perf_counter() - traversal_started) * 1000.0,
    )
    hotpath_metrics.increment("folders_recursive_items_total", total_items)


def _build_recursive_folder_payload(
    storage: BrowseStorage,
    canonical: str,
    index: Any,
    to_item: ToItemFn,
    *,
    count_only: bool,
    offset: int = 0,
    limit: int | None = None,
    browse_cache: RecursiveBrowseCache | None,
    hotpath_metrics: HotpathTelemetry | None,
) -> BrowseFolderPayload:
    _validate_recursive_window(offset, limit)
    if hotpath_metrics is not None:
        hotpath_metrics.increment("folders_recursive_requests_total")
    traversal_started = time.perf_counter()

    if count_only:
        total_items = _count_recursive_items(storage, canonical)
        _record_recursive_traversal(hotpath_metrics, traversal_started, total_items)
        return BrowseFolderPayload(
            path=canonical,
            generated_at=index.generated_at,
            items=[],
            folders=_folder_entries(index),
            metric_keys=[],
            categorical_keys=[],
            total_items=total_items,
        )

    if limit is not None:
        snapshots, total_items = _build_recursive_window_snapshots(
            storage,
            canonical,
            offset=offset,
            limit=limit,
        )
    else:
        snapshots, total_items = _load_recursive_payload_snapshots(
            storage,
            canonical,
            browse_cache,
            hotpath_metrics,
        )
    _record_recursive_traversal(hotpath_metrics, traversal_started, total_items)
    return BrowseFolderPayload(
        path=canonical,
        generated_at=index.generated_at,
        items=[to_item(storage, snapshot) for snapshot in snapshots],
        folders=_folder_entries(index),
        metric_keys=_metric_keys_for_folder(
            storage,
            canonical,
            index,
            recursive=True,
            snapshots=snapshots,
        ),
        categorical_keys=_categorical_keys_for_folder(
            storage,
            canonical,
            index,
            recursive=True,
            snapshots=snapshots,
        ),
        total_items=total_items if limit is not None else None,
        offset=offset if limit is not None else None,
        limit=limit,
    )


def build_folder_index(
    storage: BrowseStorage,
    path: str,
    to_item: ToItemFn,
    recursive: bool = False,
    count_only: bool = False,
    offset: int = 0,
    limit: int | None = None,
    browse_cache: RecursiveBrowseCache | None = None,
    hotpath_metrics: HotpathTelemetry | None = None,
) -> BrowseFolderPayload:
    canonical = canonical_path(path)
    if recursive:
        return _build_recursive_folder_payload(
            storage,
            canonical,
            _load_folder_index(storage, canonical, recursive=True),
            to_item,
            count_only=count_only,
            offset=offset,
            limit=limit,
            browse_cache=browse_cache,
            hotpath_metrics=hotpath_metrics,
        )

    return _build_direct_folder_payload(
        storage,
        canonical,
        _load_folder_index(storage, canonical, recursive=False),
        to_item,
        count_only=count_only,
    )


def _query_result_payload(
    storage: BrowseStorage,
    result: BrowseQueryResult[Any],
    to_item: ToItemFn,
) -> BrowseQueryResponse:
    return BrowseQueryResponse(
        path=result.path,
        generated_at=result.generated_at,
        generation_token=result.generation_token,
        request_token=result.request_token,
        scope_total=result.scope_total,
        filtered_total=result.filtered_total,
        offset=result.offset,
        limit=result.limit,
        items=[item if isinstance(item, BrowseItemPayload) else to_item(storage, item) for item in result.items],
        folders=[
            BrowseFolderEntryPayload(name=folder.name, kind=folder.kind)
            for folder in result.folders
        ],
        metric_keys=list(result.metric_keys),
        categorical_keys=list(result.categorical_keys),
    )


def _sidecar_state_for_query(storage: BrowseStorage, path: str) -> SidecarState:
    getter = getattr(storage, "get_sidecar_readonly", None)
    if not callable(getter):
        return {}
    return cast(SidecarState, getter(path))


def _query_record_from_payload(
    payload: BrowseItemPayload,
    sidecar_state: SidecarState,
) -> BrowseQueryRecord[BrowseItemPayload]:
    tags = sidecar_state.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    sidecar_source, sidecar_url = sidecar_source_fields(sidecar_state)
    source = " ".join(
        value for value in (payload.source, sidecar_source)
        if value
    ) or None
    url = " ".join(
        value for value in (payload.url, sidecar_url)
        if value
    ) or None
    search_text = build_search_haystack(
        logical_path=payload.path,
        name=payload.name,
        tags=tags,
        notes=sidecar_state.get("notes", ""),
        source=source,
        url=url,
        include_source_fields=bool(source or url),
    )
    return BrowseQueryRecord(
        payload=payload,
        stable_identity=payload.path,
        path=payload.path,
        name=payload.name,
        added_at=payload.added_at,
        width=payload.width,
        height=payload.height,
        source=payload.source,
        url=payload.url,
        metrics=payload.metrics or {},
        categoricals=payload.categoricals or {},
        star=payload.star,
        notes=payload.notes,
        search_text=search_text,
    )


def _records_from_items(
    storage: BrowseStorage,
    raw_items: Iterable[Any],
    to_item: ToItemFn,
) -> tuple[BrowseQueryRecord[BrowseItemPayload], ...]:
    records: list[BrowseQueryRecord[BrowseItemPayload]] = []
    for raw_item in raw_items:
        payload = to_item(storage, raw_item)
        records.append(_query_record_from_payload(
            payload,
            _sidecar_state_for_query(storage, payload.path),
        ))
    return tuple(records)


def _raw_items_for_query_fallback(
    storage: BrowseStorage,
    canonical: str,
    index: Any,
    *,
    recursive: bool,
) -> tuple[list[Any], int]:
    if not recursive:
        raw_items = list(getattr(index, "items", []) or [])
        return raw_items, _direct_folder_total_items(index)

    max_items = _recursive_items_hard_limit(storage)
    if max_items is None or max_items > BROWSE_QUERY_FALLBACK_MAX_ITEMS:
        max_items = BROWSE_QUERY_FALLBACK_MAX_ITEMS
    scope_total = _count_recursive_items(storage, canonical)
    if max_items is not None and scope_total > max_items:
        _raise_browse_query_fallback_limit()
    return list(storage.items_in_scope(canonical)), scope_total


def _fallback_browse_query_result(
    storage: BrowseStorage,
    spec: BrowseQuerySpec,
    index: Any,
    to_item: ToItemFn,
) -> BrowseQueryResult[BrowseItemPayload]:
    raw_items, scope_total = _raw_items_for_query_fallback(
        storage,
        spec.path,
        index,
        recursive=spec.recursive,
    )
    records = _records_from_items(storage, raw_items, to_item)
    evaluation = evaluate_browse_records(records, spec)
    return BrowseQueryResult(
        path=spec.path,
        generated_at=index.generated_at,
        generation_token=build_browse_generation_token(storage),
        request_token=browse_query_request_token(spec),
        scope_total=scope_total,
        filtered_total=evaluation.filtered_total,
        offset=spec.offset,
        limit=spec.limit,
        items=tuple(record.payload for record in evaluation.window),
        folders=tuple(
            BrowseQueryFolderEntry(name=folder.name, kind=folder.kind)
            for folder in _folder_entries(index)
        ),
        metric_keys=tuple(_metric_keys_for_folder(
            storage,
            spec.path,
            index,
            recursive=spec.recursive,
        )),
        categorical_keys=tuple(_categorical_keys_for_folder(
            storage,
            spec.path,
            index,
            recursive=spec.recursive,
        )),
    )


def build_folder_query(
    storage: BrowseStorage,
    spec: BrowseQuerySpec,
    to_item: ToItemFn,
) -> BrowseQueryResponse:
    index = _load_folder_index(storage, spec.path, recursive=spec.recursive)
    query_provider = getattr(storage, "query_browse_scope", None)
    if callable(query_provider):
        try:
            result = cast(BrowseQueryStorage, storage).query_browse_scope(spec)
        except ValueError as exc:
            raise HTTPException(400, "invalid path") from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, "folder not found") from exc
        return _query_result_payload(storage, result, to_item)

    return _query_result_payload(
        storage,
        _fallback_browse_query_result(storage, spec, index, to_item),
        to_item,
    )


def search_results(
    storage: SearchStorage,
    to_item: ToItemFn,
    q: str,
    path: str,
    limit: int,
) -> BrowseSearchResultsPayload:
    hits = storage.search(query=q, path=path, limit=limit)
    return BrowseSearchResultsPayload(items=[to_item(storage, it) for it in hits])
