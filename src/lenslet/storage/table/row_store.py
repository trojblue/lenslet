from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from typing import Callable

from ..base import SidecarState
from ..image_media import ImageMime, normalize_image_mime
from ..progress import ProgressTicker
from ..search_text import normalize_search_path
from ..source.backed import SourceBackedConfig, SourceBackedServices
from ..source.media import MediaReadService
from ..source.paths import (
    dedupe_path,
    derive_http_logical_path,
    derive_logical_path,
    extract_name,
    is_http_url,
    is_s3_uri,
    normalize_item_path,
)
from .schema import coerce_int, coerce_timestamp
from .row_scan import (
    IndexColumns,
    LocalSkipCounts,
    LocalSourceResolution,
    _can_scan_uniform_http_rows,
    _cached_dimensions_for_row,
    _fast_path_folder_and_name,
    _fast_text,
    _resolve_local_source,
    _resolve_row_identity,
    _resolve_row_media_fields,
)
from .index_types import TableIndexInput


MetricProvider = Callable[[int], dict[str, float]]
MediaUpdateCallback = Callable[[int, int, int], None]


@dataclass(init=False, slots=True)
class TableRowViewItem:
    """Materialized table-row browse item produced only at API/media boundaries."""

    path: str
    name: str
    mime: ImageMime
    _width: int
    _height: int
    _size: int
    mtime: float
    url: str | None
    source: str | None
    metric_labels: dict[str, str]
    categoricals: dict[str, str]
    row_idx: int
    _metrics: dict[str, float] | None
    _metrics_provider: MetricProvider | None
    _media_update: MediaUpdateCallback | None
    sidecar_snapshot: SidecarState | None
    mutable_metric_keys: tuple[str, ...]

    def __init__(
        self,
        *,
        path: str,
        name: str,
        mime: ImageMime,
        width: int,
        height: int,
        size: int,
        mtime: float,
        url: str | None,
        source: str | None,
        row_idx: int,
        metric_labels: dict[str, str] | None = None,
        categoricals: dict[str, str] | None = None,
        metrics: dict[str, float] | None = None,
        metrics_provider: MetricProvider | None = None,
        media_update: MediaUpdateCallback | None = None,
        sidecar_snapshot: SidecarState | None = None,
        mutable_metric_keys: tuple[str, ...] = (),
    ) -> None:
        self.path = path
        self.name = name
        self.mime = mime
        self._width = width
        self._height = height
        self._size = size
        self.mtime = mtime
        self.url = url
        self.source = source
        self.metric_labels = metric_labels or {}
        self.categoricals = categoricals or {}
        self.row_idx = row_idx
        self._metrics = metrics
        self._metrics_provider = metrics_provider
        self._media_update = media_update
        self.sidecar_snapshot = sidecar_snapshot
        self.mutable_metric_keys = mutable_metric_keys

    def _write_media_update(self) -> None:
        if self._media_update is not None:
            self._media_update(self._width, self._height, self._size)

    @property
    def width(self) -> int:
        return self._width

    @width.setter
    def width(self, value: int) -> None:
        self._width = value
        self._write_media_update()

    @property
    def height(self) -> int:
        return self._height

    @height.setter
    def height(self, value: int) -> None:
        self._height = value
        self._write_media_update()

    @property
    def size(self) -> int:
        return self._size

    @size.setter
    def size(self, value: int) -> None:
        self._size = value
        self._write_media_update()

    @property
    def metrics(self) -> dict[str, float]:
        metrics = self._metrics
        if metrics is None:
            if self._metrics_provider is None:
                metrics = {}
            else:
                metrics = self._metrics_provider(self.row_idx)
            self._metrics = metrics
        return metrics

    @metrics.setter
    def metrics(self, value: dict[str, float]) -> None:
        self._metrics = value


@dataclass(slots=True)
class TableRowStore:
    """Compact row-owned table state for the row-view backend."""

    row_count: int
    paths: tuple[str, ...]
    sources: tuple[str, ...]
    names: tuple[str, ...]
    mimes: tuple[ImageMime, ...]
    widths: tuple[int, ...]
    heights: tuple[int, ...]
    sizes: tuple[int, ...]
    mtimes: tuple[float, ...]
    urls: tuple[str | None, ...]
    sorted_paths: tuple[str, ...]
    sorted_rows: tuple[int, ...]
    path_to_row: dict[str, int]
    row_to_path: list[str | None]
    row_to_slot: list[int] | None
    folder_rows: dict[str, tuple[int, ...]]
    folder_children: dict[str, tuple[str, ...]]
    row_dimensions: list[tuple[int, int] | None]
    dimensions: dict[str, tuple[int, int]] = field(default_factory=dict)
    size_overrides: dict[int, int] = field(default_factory=dict)
    materialized_item_count: int = 0

    def total_rows(self) -> int:
        return len(self.paths)

    def _slot_for_row(self, row_idx: int) -> int:
        if self.row_to_slot is None:
            if 0 <= row_idx < len(self.paths):
                return row_idx
            raise FileNotFoundError(row_idx)
        if 0 <= row_idx < len(self.row_to_slot):
            slot = self.row_to_slot[row_idx]
            if slot >= 0:
                return slot
        raise FileNotFoundError(row_idx)

    def _path_candidates(self, path: str) -> tuple[str, ...]:
        normalized = normalize_item_path(path)
        rooted = f"/{normalized}" if normalized else "/"
        candidates: list[str] = []
        for candidate in (path, normalized, path.lstrip("/"), rooted):
            cleaned = normalize_item_path(candidate)
            if cleaned and cleaned not in candidates:
                candidates.append(cleaned)
        return tuple(candidates)

    def row_index_for_path(self, path: str) -> int | None:
        for candidate in self._path_candidates(path):
            row_idx = self.path_to_row.get(candidate)
            if row_idx is not None:
                return row_idx
        return None

    def path_for_row_index(self, row_idx: int) -> str | None:
        if 0 <= row_idx < len(self.row_to_path):
            return self.row_to_path[row_idx]
        return None

    def source_for_path(self, path: str) -> str:
        row_idx = self.row_index_for_path(path)
        if row_idx is None:
            raise FileNotFoundError(path)
        return self.sources[self._slot_for_row(row_idx)]

    def exists(self, path: str) -> bool:
        return self.row_index_for_path(path) is not None

    def size_for_row(self, row_idx: int) -> int:
        if row_idx in self.size_overrides:
            return self.size_overrides[row_idx]
        return self.sizes[self._slot_for_row(row_idx)]

    def size_for_path(self, path: str) -> int:
        row_idx = self.row_index_for_path(path)
        if row_idx is None:
            raise FileNotFoundError(path)
        return self.size_for_row(row_idx)

    def mtime_for_row(self, row_idx: int) -> float:
        return self.mtimes[self._slot_for_row(row_idx)]

    def source_for_row(self, row_idx: int) -> str:
        return self.sources[self._slot_for_row(row_idx)]

    def name_for_row(self, row_idx: int) -> str:
        return self.names[self._slot_for_row(row_idx)]

    def url_for_row(self, row_idx: int) -> str | None:
        return self.urls[self._slot_for_row(row_idx)]

    def item_fields_for_row(
        self,
        row_idx: int,
    ) -> tuple[str, str, ImageMime, int, int, int, float, str | None, str]:
        slot = self._slot_for_row(row_idx)
        width, height = self.dimensions_for_row(row_idx)
        return (
            self.paths[slot],
            self.names[slot],
            self.mimes[slot],
            width,
            height,
            self.size_for_row(row_idx),
            self.mtimes[slot],
            self.urls[slot],
            self.sources[slot],
        )

    def dimensions_for_row(self, row_idx: int) -> tuple[int, int]:
        path = self.path_for_row_index(row_idx)
        if path is not None and path in self.dimensions:
            return self.dimensions[path]
        dims = self.row_dimensions[row_idx] if 0 <= row_idx < len(self.row_dimensions) else None
        if dims is not None:
            return dims
        slot = self._slot_for_row(row_idx)
        return self.widths[slot], self.heights[slot]

    def dimensions_for_path(self, path: str) -> tuple[int, int]:
        row_idx = self.row_index_for_path(path)
        if row_idx is None:
            raise FileNotFoundError(path)
        return self.dimensions_for_row(row_idx)

    def update_dimensions(
        self,
        path: str,
        dims: tuple[int, int],
        *,
        size: int | None = None,
    ) -> None:
        row_idx = self.row_index_for_path(path)
        if row_idx is None:
            raise FileNotFoundError(path)
        logical_path = self.path_for_row_index(row_idx)
        if logical_path is None:
            raise FileNotFoundError(path)
        self.dimensions[logical_path] = dims
        self.row_dimensions[row_idx] = dims
        if size is not None:
            self.size_overrides[row_idx] = size

    def update_size(self, path: str, size: int) -> None:
        row_idx = self.row_index_for_path(path)
        if row_idx is None:
            raise FileNotFoundError(path)
        self.size_overrides[row_idx] = size

    def _update_materialized_media(
        self,
        row_idx: int,
        path: str,
        width: int,
        height: int,
        size: int,
    ) -> None:
        self.dimensions[path] = (width, height)
        self.row_dimensions[row_idx] = (width, height)
        self.size_overrides[row_idx] = size

    def folder_dirs(self, path: str) -> tuple[str, ...]:
        return self.folder_children.get(normalize_search_path(path), ())

    def direct_rows(self, path: str) -> tuple[int, ...]:
        return self.folder_rows.get(normalize_search_path(path), ())

    def scope_bounds(self, path: str) -> tuple[int, int]:
        scope_norm = normalize_search_path(path)
        if not scope_norm:
            return 0, len(self.sorted_rows)
        prefix = f"{scope_norm}/"
        start = bisect_left(self.sorted_paths, prefix)
        end = bisect_right(self.sorted_paths, prefix + "\uffff")
        return start, end

    def rows_in_scope(self, path: str) -> tuple[int, ...]:
        start, end = self.scope_bounds(path)
        return self.sorted_rows[start:end]

    def rows_in_scope_window(self, path: str, offset: int, limit: int) -> tuple[int, ...]:
        start, end = self.scope_bounds(path)
        window_start = min(end, start + max(0, offset))
        window_end = min(end, window_start + max(0, limit))
        return self.sorted_rows[window_start:window_end]

    def count_in_scope(self, path: str) -> int:
        start, end = self.scope_bounds(path)
        return max(0, end - start)

    def materialize_item(
        self,
        row_idx: int,
        *,
        metrics_provider: MetricProvider | None = None,
        dimensions: tuple[int, int] | None = None,
        sidecar_snapshot: SidecarState | None = None,
        mutable_metric_keys: tuple[str, ...] = (),
    ) -> TableRowViewItem:
        path, name, mime, width, height, size, mtime, url, source = self.item_fields_for_row(row_idx)
        if dimensions is not None:
            width, height = dimensions
        self.materialized_item_count += 1
        return TableRowViewItem(
            path=path,
            name=name,
            mime=mime,
            width=width,
            height=height,
            size=size,
            mtime=mtime,
            url=url,
            source=source,
            row_idx=row_idx,
            metrics_provider=metrics_provider,
            sidecar_snapshot=sidecar_snapshot,
            mutable_metric_keys=mutable_metric_keys,
            media_update=lambda new_width, new_height, new_size: self._update_materialized_media(
                row_idx,
                path,
                new_width,
                new_height,
                new_size,
            ),
        )


@dataclass(frozen=True, slots=True)
class TableRowRemoteDimensionTask:
    row_idx: int
    path: str
    source: str
    name: str


@dataclass(slots=True)
class TableRowStoreBuildResult:
    store: TableRowStore
    remote_tasks: list[TableRowRemoteDimensionTask]
    skipped_local_disabled: int
    skipped_local_outside_root: int
    skipped_local_resolved_outside_root: int
    skipped_local_missing: int


def _record_folder_children(
    folder_norm: str,
    *,
    seen_folders: set[str],
    dir_children: dict[str, set[str]],
) -> None:
    if folder_norm in seen_folders:
        return
    seen_folders.add(folder_norm)
    parts = folder_norm.split("/") if folder_norm else []
    for depth in range(len(parts)):
        parent = "/".join(parts[:depth])
        child = parts[depth]
        dir_children.setdefault(parent, set()).add(child)


def _folder_norm(logical_path: str) -> str:
    if "/" not in logical_path:
        return ""
    return logical_path.rsplit("/", 1)[0]


def _int_or_zero(value: object) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0


def _remember_row_slot(
    row_to_slot: list[int] | None,
    *,
    row_indices: list[int],
    row_count: int,
    row_idx: int,
    slot: int,
) -> list[int] | None:
    if row_to_slot is None:
        if row_idx == slot:
            return None
        row_to_slot = [-1] * row_count
        for previous_slot, previous_row_idx in enumerate(row_indices):
            row_to_slot[previous_row_idx] = previous_slot
    row_to_slot[row_idx] = slot
    return row_to_slot


def _finish_row_store(
    *,
    row_count: int,
    row_indices: list[int],
    paths: list[str],
    sources: list[str],
    names: list[str],
    mimes: list[ImageMime],
    widths: list[int],
    heights: list[int],
    sizes: list[int],
    mtimes: list[float],
    urls: list[str | None],
    path_to_row: dict[str, int],
    row_to_path: list[str | None],
    row_to_slot: list[int] | None,
    folder_rows: dict[str, list[int]],
    dir_children: dict[str, set[str]],
    row_dimensions: list[tuple[int, int] | None],
) -> TableRowStore:
    folder_rows.setdefault("", [])
    sorted_pairs = sorted(zip(paths, row_indices), key=lambda pair: pair[0])
    return TableRowStore(
        row_count=row_count,
        paths=tuple(paths),
        sources=tuple(sources),
        names=tuple(names),
        mimes=tuple(mimes),
        widths=tuple(widths),
        heights=tuple(heights),
        sizes=tuple(sizes),
        mtimes=tuple(mtimes),
        urls=tuple(urls),
        sorted_paths=tuple(path for path, _row_idx in sorted_pairs),
        sorted_rows=tuple(row_idx for _path, row_idx in sorted_pairs),
        path_to_row=path_to_row,
        row_to_path=row_to_path,
        row_to_slot=row_to_slot,
        folder_rows={key: tuple(value) for key, value in folder_rows.items()},
        folder_children={key: tuple(sorted(value)) for key, value in dir_children.items()},
        row_dimensions=row_dimensions,
    )


def build_table_row_store(
    context: TableIndexInput,
    columns: IndexColumns,
) -> TableRowStoreBuildResult:
    if _can_scan_uniform_http_rows(context, columns):
        return _build_uniform_http_row_store(context, columns)

    table = context.table
    policy = context.policy
    seen_paths: set[str] = set()
    skipped = LocalSkipCounts()
    remote_tasks: list[TableRowRemoteDimensionTask] = []

    row_indices: list[int] = []
    paths: list[str] = []
    sources: list[str] = []
    names: list[str] = []
    mimes: list[ImageMime] = []
    widths: list[int] = []
    heights: list[int] = []
    sizes: list[int] = []
    mtimes: list[float] = []
    urls: list[str | None] = []
    path_to_row: dict[str, int] = {}
    row_to_path: list[str | None] = [None] * table.row_count
    row_to_slot: list[int] | None = None
    row_dimensions: list[tuple[int, int] | None] = [None] * table.row_count
    folder_rows: dict[str, list[int]] = {}
    dir_children: dict[str, set[str]] = {}
    seen_folders: set[str] = set()

    progress = ProgressTicker(
        total=table.row_count,
        label=f"table:{table.source_column}",
        emit=context.progress,
    )

    for row_idx in range(table.row_count):
        identity = _resolve_row_identity(context, columns, row_idx, seen_paths)
        if identity is None:
            progress.step()
            continue

        local_source = (
            _resolve_local_source(context, identity.source)
            if identity.is_local
            else LocalSourceResolution(resolved_path=None)
        )
        if skipped.record(local_source.skip_reason):
            progress.step()
            continue

        size, mtime, width, height, discovered_dims = _resolve_row_media_fields(
            context,
            columns,
            row_idx,
            identity,
            local_source,
        )
        slot = len(row_indices)
        folder_norm = _folder_norm(identity.logical_path)
        row_to_slot = _remember_row_slot(
            row_to_slot,
            row_indices=row_indices,
            row_count=table.row_count,
            row_idx=row_idx,
            slot=slot,
        )

        row_indices.append(row_idx)
        paths.append(identity.logical_path)
        sources.append(identity.source)
        names.append(identity.name)
        mimes.append(identity.mime)
        widths.append(width)
        heights.append(height)
        sizes.append(size)
        mtimes.append(mtime or 0.0)
        urls.append(identity.source if identity.is_http else None)
        path_to_row[identity.logical_path] = row_idx
        row_to_path[row_idx] = identity.logical_path
        row_dimensions[row_idx] = discovered_dims or (width, height)
        folder_rows.setdefault(folder_norm, []).append(row_idx)
        _record_folder_children(
            folder_norm,
            seen_folders=seen_folders,
            dir_children=dir_children,
        )
        if (identity.is_s3 or identity.is_http) and (width == 0 or height == 0) and not policy.skip_dimension_probe:
            remote_tasks.append(
                TableRowRemoteDimensionTask(
                    row_idx=row_idx,
                    path=identity.logical_path,
                    source=identity.source,
                    name=identity.name,
                )
            )
        progress.step()

    progress.finish()
    store = _finish_row_store(
        row_count=table.row_count,
        row_indices=row_indices,
        paths=paths,
        sources=sources,
        names=names,
        mimes=mimes,
        widths=widths,
        heights=heights,
        sizes=sizes,
        mtimes=mtimes,
        urls=urls,
        path_to_row=path_to_row,
        row_to_path=row_to_path,
        row_to_slot=row_to_slot,
        folder_rows=folder_rows,
        dir_children=dir_children,
        row_dimensions=row_dimensions,
    )
    return TableRowStoreBuildResult(
        store=store,
        remote_tasks=remote_tasks,
        skipped_local_disabled=skipped.disabled,
        skipped_local_outside_root=skipped.outside_root,
        skipped_local_resolved_outside_root=skipped.resolved_outside_root,
        skipped_local_missing=skipped.missing,
    )


def _build_uniform_http_row_store(
    context: TableIndexInput,
    columns: IndexColumns,
) -> TableRowStoreBuildResult:
    table = context.table
    policy = context.policy
    row_count = table.row_count
    seen_paths: set[str] = set()
    remote_tasks: list[TableRowRemoteDimensionTask] = []

    row_indices: list[int] = []
    paths: list[str] = []
    sources: list[str] = []
    names: list[str] = []
    mimes: list[ImageMime] = []
    widths: list[int] = []
    heights: list[int] = []
    sizes: list[int] = []
    mtimes: list[float] = []
    urls: list[str | None] = []
    path_to_row: dict[str, int] = {}
    row_to_path: list[str | None] = [None] * row_count
    row_to_slot: list[int] | None = None
    row_dimensions: list[tuple[int, int] | None] = [None] * row_count
    folder_rows: dict[str, list[int]] = {}
    dir_children: dict[str, set[str]] = {}
    seen_folders: set[str] = set()

    source_values = columns.source_values
    path_values = columns.path_values
    name_values = columns.name_values
    mime_values = columns.mime_values
    width_values = columns.width_values
    height_values = columns.height_values
    size_values = columns.size_values
    mtime_values = columns.mtime_values
    has_path_column = table.path_column is not None
    has_name_column = table.name_column is not None
    has_mime_column = table.mime_column is not None
    has_size_column = table.size_column is not None
    has_mtime_column = table.mtime_column is not None
    has_width_column = table.width_column is not None
    has_height_column = table.height_column is not None

    progress = ProgressTicker(
        total=row_count,
        label=f"table:{table.source_column}",
        emit=context.progress,
    )
    progress_batch_size = 2048

    for row_idx in range(row_count):
        if (row_idx + 1) % progress_batch_size == 0:
            progress.step(progress_batch_size)

        source = _fast_text(source_values[row_idx])
        if not source or not is_http_url(source):
            continue

        if has_path_column:
            logical_value = _fast_text(path_values[row_idx]) or source
            if is_http_url(logical_value):
                logical_path = normalize_item_path(derive_http_logical_path(logical_value))
                folder_norm, fallback_name = _fast_path_folder_and_name(logical_path) if logical_path else ("", "")
            elif is_s3_uri(logical_value):
                logical_path = normalize_item_path(
                    derive_logical_path(
                        logical_value,
                        root=table.root,
                        local_prefix=table.local_prefix,
                        s3_prefixes=table.s3_prefixes,
                        s3_use_bucket=table.s3_use_bucket,
                    )
                )
                folder_norm, fallback_name = (
                    _fast_path_folder_and_name(logical_path) if logical_path else ("", extract_name(source))
                )
            else:
                logical_path = normalize_item_path(logical_value)
                folder_norm, _path_name = _fast_path_folder_and_name(logical_path)
                fallback_name = extract_name(source)
        else:
            logical_path = derive_http_logical_path(source)
            folder_norm, fallback_name = _fast_path_folder_and_name(logical_path) if logical_path else ("", "")
        if not logical_path:
            continue

        explicit_name = _fast_text(name_values[row_idx]) if has_name_column else ""
        image_name = explicit_name or fallback_name or extract_name(logical_path) or "image"

        if logical_path in seen_paths:
            logical_path = dedupe_path(logical_path, seen_paths)
        seen_paths.add(logical_path)

        mime = normalize_image_mime(mime_values[row_idx], image_name) if has_mime_column else context.source_resolver.guess_mime(image_name)
        size = (coerce_int(size_values[row_idx]) or 0) if has_size_column else 0
        mtime = (coerce_timestamp(mtime_values[row_idx]) or 0.0) if has_mtime_column else 0.0
        width = _int_or_zero(width_values[row_idx]) if has_width_column else 0
        height = _int_or_zero(height_values[row_idx]) if has_height_column else 0
        cached_dims = None
        if width <= 0 or height <= 0:
            cached_dims = _cached_dimensions_for_row(context.table, row_idx, source, logical_path)
            if cached_dims is not None:
                width, height = cached_dims

        slot = len(row_indices)
        row_to_slot = _remember_row_slot(
            row_to_slot,
            row_indices=row_indices,
            row_count=row_count,
            row_idx=row_idx,
            slot=slot,
        )
        row_indices.append(row_idx)
        paths.append(logical_path)
        sources.append(source)
        names.append(image_name)
        mimes.append(mime)
        widths.append(width)
        heights.append(height)
        sizes.append(size)
        mtimes.append(mtime)
        urls.append(source)
        path_to_row[logical_path] = row_idx
        row_to_path[row_idx] = logical_path
        row_dimensions[row_idx] = cached_dims or (width, height)
        folder_rows.setdefault(folder_norm, []).append(row_idx)
        _record_folder_children(
            folder_norm,
            seen_folders=seen_folders,
            dir_children=dir_children,
        )
        if (width == 0 or height == 0) and not policy.skip_dimension_probe:
            remote_tasks.append(
                TableRowRemoteDimensionTask(
                    row_idx=row_idx,
                    path=logical_path,
                    source=source,
                    name=image_name,
                )
            )

    remainder = row_count % progress_batch_size
    if remainder:
        progress.step(remainder)
    progress.finish()
    store = _finish_row_store(
        row_count=row_count,
        row_indices=row_indices,
        paths=paths,
        sources=sources,
        names=names,
        mimes=mimes,
        widths=widths,
        heights=heights,
        sizes=sizes,
        mtimes=mtimes,
        urls=urls,
        path_to_row=path_to_row,
        row_to_path=row_to_path,
        row_to_slot=row_to_slot,
        folder_rows=folder_rows,
        dir_children=dir_children,
        row_dimensions=row_dimensions,
    )
    return TableRowStoreBuildResult(
        store=store,
        remote_tasks=remote_tasks,
        skipped_local_disabled=0,
        skipped_local_outside_root=0,
        skipped_local_resolved_outside_root=0,
        skipped_local_missing=0,
    )


@dataclass(slots=True)
class TableRowSourceAdapter:
    """Row-native source/media lookup without a dense item map."""

    row_store: TableRowStore
    media_reads: MediaReadService

    @classmethod
    def from_services(
        cls,
        row_store: TableRowStore,
        *,
        config: SourceBackedConfig,
        services: SourceBackedServices,
    ) -> TableRowSourceAdapter:
        return cls(
            row_store=row_store,
            media_reads=MediaReadService(
                remote_header_bytes=config.remote_header_bytes,
                resolve_local_source=services.resolve_local_source,
                is_s3_uri=services.is_s3_uri,
                is_http_url=services.is_http_url,
                read_dimensions_from_bytes=services.read_dimensions_from_bytes,
            ),
        )

    def exists(self, path: str) -> bool:
        return self.row_store.exists(path)

    def get_source_path(self, logical_path: str) -> str:
        return self.row_store.source_for_path(logical_path)

    def read_bytes(self, path: str) -> bytes:
        source = self.get_source_path(path)
        return self.media_reads.read_bytes(path, source)

    def size(self, path: str) -> int:
        return self.row_store.size_for_path(path)

    def get_dimensions(self, path: str) -> tuple[int, int]:
        return self.row_store.dimensions_for_path(path)

    def row_index_for_path(self, path: str) -> int | None:
        return self.row_store.row_index_for_path(path)

    def etag(self, path: str) -> str | None:
        row_idx = self.row_index_for_path(path)
        if row_idx is None:
            return None
        return f"{int(self.row_store.mtime_for_row(row_idx))}-{self.row_store.size_for_row(row_idx)}"
