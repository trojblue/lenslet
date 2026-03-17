from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Protocol, TypeAlias


RemoteDimensionTask: TypeAlias = tuple[str, Any, str, str]


class TableIndexScanHost(Protocol):
    root: str | None
    RESERVED_COLUMNS: set[str]

    _row_count: int
    _data: dict[str, list[Any]]
    _columns: list[str]
    _source_column: str
    _path_column: str | None
    _name_column: str | None
    _mime_column: str | None
    _width_column: str | None
    _height_column: str | None
    _size_column: str | None
    _mtime_column: str | None
    _metrics_column: str | None
    _local_prefix: str | None
    _allow_local: bool
    _skip_indexing: bool
    _skip_local_realpath_validation: bool

    _progress: Callable[[int, int, str], None]
    _extract_name: Callable[[str], str]
    _is_supported_image: Callable[[str], bool]
    _is_s3_uri: Callable[[str], bool]
    _is_http_url: Callable[[str], bool]
    _derive_logical_path: Callable[[str], str]
    _normalize_item_path: Callable[[str], str]
    _normalize_path: Callable[[str], str]
    _dedupe_path: Callable[[str, set[str]], str]
    _guess_mime: Callable[[str], str]
    _coerce_int: Callable[[Any], int | None]
    _coerce_timestamp: Callable[[Any], float | None]
    _coerce_float: Callable[[Any], float | None]
    _resolve_local_source: Callable[[str], str]
    _resolve_local_source_lexical: Callable[[str], str]
    _read_dimensions_fast: Callable[[str], tuple[int, int] | None]


class TableIndexStoreHost(TableIndexScanHost, Protocol):
    _indexes: dict[str, Any]
    _items: dict[str, Any]
    _source_paths: dict[str, str]
    _row_dimensions: list[tuple[int, int] | None]
    _path_to_row: dict[str, int]
    _row_to_path: dict[int, str]
    _dimensions: dict[str, tuple[int, int]]

    _probe_remote_dimensions: Callable[[list[RemoteDimensionTask]], None]


@dataclass(frozen=True)
class IndexColumns:
    source_values: list[Any]
    path_values: list[Any]
    name_values: list[Any]
    mime_values: list[Any]
    width_values: list[Any]
    height_values: list[Any]
    size_values: list[Any]
    mtime_values: list[Any]
    metrics_values: list[Any]
    metric_columns: tuple[tuple[str, list[Any]], ...]


@dataclass
class ScannedRow:
    row_idx: int
    logical_path: str
    source: str
    folder_norm: str
    item: Any
    discovered_dims: tuple[int, int] | None = None


@dataclass
class ScanResult:
    rows: list[ScannedRow]
    remote_tasks: list[tuple[str, Any, str, str]]
    skipped_local_disabled: int
    skipped_local_outside_root: int
    skipped_local_missing: int


@dataclass(frozen=True)
class RowIdentity:
    source: str
    name: str
    logical_path: str
    mime: str
    is_s3: bool
    is_http: bool

    @property
    def is_local(self) -> bool:
        return not self.is_s3 and not self.is_http


@dataclass(frozen=True)
class LocalSourceResolution:
    resolved_path: str | None
    skip_reason: str | None = None


def _is_internal_metric_key(raw_key: Any) -> bool:
    key = str(raw_key).strip()
    if not key.startswith("__index_level_") or not key.endswith("__"):
        return False
    return key[len("__index_level_"):-2].isdigit()


class ProgressTicker:
    def __init__(self, *, total: int, label: str, emit: Callable[[int, int, str], None]) -> None:
        self.total = total
        self.label = label
        self.emit = emit
        self.done = 0
        self.last_print = 0.0

    def step(self) -> None:
        self.done += 1
        now = time.monotonic()
        if now - self.last_print > 0.1 or self.done == self.total:
            self.emit(self.done, self.total, self.label)
            self.last_print = now

    def finish(self) -> None:
        if self.done < self.total:
            self.emit(self.total, self.total, self.label)


def build_table_indexes(
    storage: TableIndexStoreHost,
    *,
    item_factory: Callable[..., Any],
    index_factory: Callable[..., Any],
) -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    columns = build_index_columns(storage)
    scan = scan_rows(storage, columns, item_factory=item_factory)
    assemble_indexes(storage, scan.rows, generated_at=generated_at, index_factory=index_factory)

    if scan.remote_tasks:
        storage._probe_remote_dimensions(scan.remote_tasks)
    if scan.skipped_local_disabled:
        print(f"[lenslet] Skipped {scan.skipped_local_disabled} local path(s): local sources are disabled.")
    if scan.skipped_local_outside_root:
        boundary = storage.root or "(unset)"
        print(
            f"[lenslet] Skipped {scan.skipped_local_outside_root} local path(s) outside "
            f"base_dir boundary: {boundary}"
        )
    if scan.skipped_local_missing:
        print(f"[lenslet] Skipped {scan.skipped_local_missing} missing local path(s).")


def build_index_columns(storage: TableIndexScanHost) -> IndexColumns:
    row_count = storage._row_count
    none_values: list[Any] = [None] * row_count

    def values_for(column: str | None) -> list[Any]:
        if not column:
            return none_values
        return storage._data.get(column, none_values)

    return IndexColumns(
        source_values=values_for(storage._source_column),
        path_values=values_for(storage._path_column),
        name_values=values_for(storage._name_column),
        mime_values=values_for(storage._mime_column),
        width_values=values_for(storage._width_column),
        height_values=values_for(storage._height_column),
        size_values=values_for(storage._size_column),
        mtime_values=values_for(storage._mtime_column),
        metrics_values=values_for(storage._metrics_column),
        metric_columns=collect_metric_columns(storage, none_values),
    )


def collect_metric_columns(
    storage: TableIndexScanHost,
    none_values: list[Any],
) -> tuple[tuple[str, list[Any]], ...]:
    used_columns = {
        storage._source_column,
        storage._path_column,
        storage._name_column,
        storage._mime_column,
        storage._width_column,
        storage._height_column,
        storage._size_column,
        storage._mtime_column,
    }

    metric_columns: list[tuple[str, list[Any]]] = []
    for column in storage._columns:
        if column in used_columns:
            continue
        if column.lower() in storage.RESERVED_COLUMNS:
            continue
        if _is_internal_metric_key(column):
            continue
        metric_columns.append((column, storage._data.get(column, none_values)))
    return tuple(metric_columns)


def _duplicate_display_columns(storage: TableIndexScanHost) -> set[str]:
    return {
        column
        for column in (
            storage._source_column,
            storage._path_column,
            storage._name_column,
            storage._mime_column,
            storage._width_column,
            storage._height_column,
            storage._size_column,
            storage._mtime_column,
        )
        if column
    }


def _normalize_display_value(value: Any, *, depth: int = 0) -> Any | None:
    if depth > 8 or value is None:
        return None

    as_py = getattr(value, "as_py", None)
    if callable(as_py):
        try:
            converted = as_py()
        except Exception:
            converted = value
        if converted is not value:
            return _normalize_display_value(converted, depth=depth + 1)

    item = getattr(value, "item", None)
    if callable(item):
        try:
            converted = item()
        except Exception:
            converted = value
        if converted is not value:
            return _normalize_display_value(converted, depth=depth + 1)

    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value
    if isinstance(value, str):
        return value if value.strip() else None
    if isinstance(value, os.PathLike):
        return os.fspath(value)
    if isinstance(value, bytes):
        try:
            text = value.decode("utf-8")
        except UnicodeDecodeError:
            return None
        return text if text.strip() else None
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            display_value = _normalize_display_value(raw_value, depth=depth + 1)
            if display_value is None:
                continue
            normalized[str(raw_key)] = display_value
        return normalized or None
    if isinstance(value, (list, tuple, set)):
        normalized_items = []
        for entry in value:
            display_value = _normalize_display_value(entry, depth=depth + 1)
            if display_value is None:
                continue
            normalized_items.append(display_value)
        return normalized_items or None

    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        try:
            text = isoformat()
        except Exception:
            text = None
        if isinstance(text, str) and text.strip():
            return text

    text = str(value)
    if not text.strip() or text in {"<NA>", "NaT"}:
        return None
    return text


def _normalize_metrics_display_value(storage: TableIndexScanHost, value: Any) -> Any | None:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            if _is_internal_metric_key(raw_key):
                continue
            if storage._coerce_float(raw_value) is not None:
                continue
            display_value = _normalize_display_value(raw_value, depth=1)
            if display_value is None:
                continue
            normalized[str(raw_key)] = display_value
        return normalized or None
    if storage._coerce_float(value) is not None:
        return None
    return _normalize_display_value(value)


def _coerce_source_value(source_value: Any) -> str | None:
    if source_value is None:
        return None
    if isinstance(source_value, os.PathLike):
        source_value = os.fspath(source_value)
    if not isinstance(source_value, str):
        return None
    source = source_value.strip()
    return source or None


def _resolve_row_identity(
    storage: TableIndexScanHost,
    columns: IndexColumns,
    idx: int,
    seen_paths: set[str],
) -> RowIdentity | None:
    source = _coerce_source_value(columns.source_values[idx])
    if source is None:
        return None

    fallback_name = storage._extract_name(source)
    name_value = columns.name_values[idx]
    name = str(name_value).strip() if name_value else fallback_name
    if not storage._is_supported_image(name):
        if storage._is_supported_image(fallback_name):
            name = fallback_name
        else:
            return None

    logical_value = columns.path_values[idx] if storage._path_column is not None else None
    logical_path = str(logical_value).strip() if logical_value else storage._derive_logical_path(source)
    if logical_path and os.path.isabs(logical_path) and storage._local_prefix:
        try:
            rel = os.path.relpath(logical_path, storage._local_prefix)
            if not rel.startswith(".."):
                logical_path = rel
        except ValueError:
            pass

    logical_path = storage._normalize_item_path(logical_path)
    if not logical_path:
        return None

    logical_path = storage._dedupe_path(logical_path, seen_paths)
    seen_paths.add(logical_path)

    mime_value = columns.mime_values[idx]
    mime = str(mime_value).strip() if mime_value else storage._guess_mime(name or fallback_name or source)
    is_s3 = storage._is_s3_uri(source)
    is_http = storage._is_http_url(source)
    return RowIdentity(
        source=source,
        name=name,
        logical_path=logical_path,
        mime=mime,
        is_s3=is_s3,
        is_http=is_http,
    )


def _resolve_local_source(
    storage: TableIndexScanHost,
    source: str,
) -> LocalSourceResolution:
    if not storage._allow_local:
        return LocalSourceResolution(resolved_path=None, skip_reason="disabled")
    try:
        if storage._skip_local_realpath_validation:
            resolved = storage._resolve_local_source_lexical(source)
        else:
            resolved = storage._resolve_local_source(source)
    except ValueError:
        return LocalSourceResolution(resolved_path=None, skip_reason="outside_root")
    if (not storage._skip_local_realpath_validation) and (not os.path.exists(resolved)):
        return LocalSourceResolution(resolved_path=None, skip_reason="missing")
    return LocalSourceResolution(resolved_path=resolved)


def _resolve_row_media_fields(
    storage: TableIndexScanHost,
    columns: IndexColumns,
    idx: int,
    identity: RowIdentity,
    local_source: LocalSourceResolution,
) -> tuple[int, float, int, int, tuple[int, int] | None]:
    size = storage._coerce_int(columns.size_values[idx])
    if size is None:
        if local_source.resolved_path is not None:
            try:
                size = os.path.getsize(local_source.resolved_path)
            except Exception:
                size = 0
        else:
            size = 0

    mtime = storage._coerce_timestamp(columns.mtime_values[idx])
    if mtime is None:
        if local_source.resolved_path is not None:
            try:
                mtime = os.path.getmtime(local_source.resolved_path)
            except Exception:
                mtime = time.time()
        else:
            mtime = time.time()

    width = storage._coerce_int(columns.width_values[idx]) or 0
    height = storage._coerce_int(columns.height_values[idx]) or 0
    discovered_dims = None
    if (width == 0 or height == 0) and identity.is_local and not storage._skip_indexing:
        local_path = local_source.resolved_path
        if local_path is not None:
            try:
                dims = storage._read_dimensions_fast(local_path)
                if dims:
                    width, height = dims
                    discovered_dims = dims
            except Exception:
                pass

    return size, mtime, width, height, discovered_dims


def _collect_row_metrics(
    storage: TableIndexScanHost,
    columns: IndexColumns,
    idx: int,
) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for metric_key, metric_values in columns.metric_columns:
        num = storage._coerce_float(metric_values[idx])
        if num is None:
            continue
        metrics[metric_key] = num

    if storage._metrics_column is None:
        return metrics

    raw_metrics = columns.metrics_values[idx]
    if not isinstance(raw_metrics, dict):
        return metrics
    for raw_key, raw_value in raw_metrics.items():
        if _is_internal_metric_key(raw_key):
            continue
        num = storage._coerce_float(raw_value)
        if num is None:
            continue
        metrics[str(raw_key)] = num
    return metrics


def scan_rows(
    storage: TableIndexScanHost,
    columns: IndexColumns,
    *,
    item_factory: Callable[..., Any],
) -> ScanResult:
    row_count = storage._row_count
    seen_paths: set[str] = set()
    rows: list[ScannedRow] = []
    remote_tasks: list[RemoteDimensionTask] = []
    skipped_local_disabled = 0
    skipped_local_outside_root = 0
    skipped_local_missing = 0

    progress = ProgressTicker(
        total=row_count,
        label=f"table:{storage._source_column}",
        emit=storage._progress,
    )

    for idx in range(row_count):
        identity = _resolve_row_identity(storage, columns, idx, seen_paths)
        if identity is None:
            progress.step()
            continue
        local_source = (
            _resolve_local_source(storage, identity.source)
            if identity.is_local
            else LocalSourceResolution(resolved_path=None)
        )
        if local_source.skip_reason == "disabled":
            skipped_local_disabled += 1
            progress.step()
            continue
        if local_source.skip_reason == "outside_root":
            skipped_local_outside_root += 1
            progress.step()
            continue
        if local_source.skip_reason == "missing":
            skipped_local_missing += 1
            progress.step()
            continue

        size, mtime, width, height, discovered_dims = _resolve_row_media_fields(
            storage,
            columns,
            idx,
            identity,
            local_source,
        )
        metrics = _collect_row_metrics(storage, columns, idx)

        item = item_factory(
            path=identity.logical_path,
            name=identity.name,
            mime=identity.mime,
            width=width,
            height=height,
            size=size,
            mtime=mtime or 0.0,
            url=identity.source if identity.is_http else None,
            source=identity.source,
            metrics=metrics,
        )

        folder = os.path.dirname(identity.logical_path).replace("\\", "/")
        folder_norm = storage._normalize_path(folder)

        rows.append(
            ScannedRow(
                row_idx=idx,
                logical_path=identity.logical_path,
                source=identity.source,
                folder_norm=folder_norm,
                item=item,
                discovered_dims=discovered_dims,
            )
        )

        if (identity.is_s3 or identity.is_http) and (width == 0 or height == 0) and not storage._skip_indexing:
            remote_tasks.append((identity.logical_path, item, identity.source, identity.name))

        progress.step()

    progress.finish()
    return ScanResult(
        rows=rows,
        remote_tasks=remote_tasks,
        skipped_local_disabled=skipped_local_disabled,
        skipped_local_outside_root=skipped_local_outside_root,
        skipped_local_missing=skipped_local_missing,
    )


def assemble_indexes(
    storage: TableIndexStoreHost,
    rows: list[ScannedRow],
    *,
    generated_at: str,
    index_factory: Callable[..., Any],
) -> None:
    dir_children: dict[str, set[str]] = {}

    for row in rows:
        storage._items[row.logical_path] = row.item
        storage._source_paths[row.logical_path] = row.source
        storage._row_dimensions[row.row_idx] = (row.item.width, row.item.height)
        storage._path_to_row[row.logical_path] = row.row_idx
        storage._row_to_path[row.row_idx] = row.logical_path

        if row.discovered_dims:
            storage._dimensions[row.logical_path] = row.discovered_dims

        storage._indexes.setdefault(
            row.folder_norm,
            index_factory(
                path="/" + row.folder_norm if row.folder_norm else "/",
                generated_at=generated_at,
                items=[],
                dirs=[],
            ),
        ).items.append(row.item)

        parts = row.folder_norm.split("/") if row.folder_norm else []
        for depth in range(len(parts)):
            parent = "/".join(parts[:depth])
            child = parts[depth]
            dir_children.setdefault(parent, set()).add(child)

    storage._indexes.setdefault(
        "",
        index_factory(path="/", generated_at=generated_at, items=[], dirs=[]),
    )

    for parent, children in dir_children.items():
        index = storage._indexes.setdefault(
            parent,
            index_factory(
                path="/" + parent if parent else "/",
                generated_at=generated_at,
                items=[],
                dirs=[],
            ),
        )
        index.dirs = sorted(children)


def extract_row_metrics(storage: TableIndexScanHost, row_idx: int) -> dict[str, float]:
    none_values: list[Any] = [None] * storage._row_count
    metric_columns = collect_metric_columns(storage, none_values)

    metrics: dict[str, float] = {}
    for column, values in metric_columns:
        num = storage._coerce_float(values[row_idx])
        if num is None:
            continue
        metrics[column] = num
    return metrics


def extract_row_metrics_map(storage: TableIndexScanHost, row_idx: int) -> dict[str, float]:
    if not storage._metrics_column:
        return {}

    raw = storage._data.get(storage._metrics_column, [None] * storage._row_count)[row_idx]
    if not isinstance(raw, dict):
        return {}

    result: dict[str, float] = {}
    for key, value in raw.items():
        if _is_internal_metric_key(key):
            continue
        num = storage._coerce_float(value)
        if num is None:
            continue
        result[str(key)] = num
    return result


def extract_row_display_fields(storage: TableIndexScanHost, row_idx: int) -> dict[str, Any]:
    none_values: list[Any] = [None] * storage._row_count
    metric_columns = {
        column
        for column, _values in collect_metric_columns(storage, none_values)
    }
    duplicate_columns = _duplicate_display_columns(storage)

    display_fields: dict[str, Any] = {}
    for column in storage._columns:
        if _is_internal_metric_key(column):
            continue
        if column in duplicate_columns:
            continue

        raw_value = storage._data.get(column, none_values)[row_idx]
        if column == storage._metrics_column:
            display_value = _normalize_metrics_display_value(storage, raw_value)
        else:
            if column in metric_columns and storage._coerce_float(raw_value) is not None:
                continue
            display_value = _normalize_display_value(raw_value)
        if display_value is None:
            continue
        display_fields[column] = display_value

    return display_fields
