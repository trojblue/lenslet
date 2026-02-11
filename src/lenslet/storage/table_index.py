from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable


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
    skipped_local: int


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
    storage: Any,
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
    if scan.skipped_local:
        print(f"[lenslet] Skipped {scan.skipped_local} local path(s) (local sources disabled or invalid).")


def build_index_columns(storage: Any) -> IndexColumns:
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


def collect_metric_columns(storage: Any, none_values: list[Any]) -> tuple[tuple[str, list[Any]], ...]:
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
        metric_columns.append((column, storage._data.get(column, none_values)))
    return tuple(metric_columns)


def scan_rows(storage: Any, columns: IndexColumns, *, item_factory: Callable[..., Any]) -> ScanResult:
    row_count = storage._row_count
    seen_paths: set[str] = set()
    rows: list[ScannedRow] = []
    remote_tasks: list[tuple[str, Any, str, str]] = []
    skipped_local = 0

    progress = ProgressTicker(
        total=row_count,
        label=f"table:{storage._source_column}",
        emit=storage._progress,
    )

    source_values = columns.source_values
    path_values = columns.path_values
    name_values = columns.name_values
    mime_values = columns.mime_values
    width_values = columns.width_values
    height_values = columns.height_values
    size_values = columns.size_values
    mtime_values = columns.mtime_values
    metrics_values = columns.metrics_values

    has_path_column = storage._path_column is not None
    local_prefix = storage._local_prefix
    allow_local = storage._allow_local
    skip_indexing = storage._skip_indexing

    extract_name = storage._extract_name
    is_supported_image = storage._is_supported_image
    is_s3_uri = storage._is_s3_uri
    is_http_url = storage._is_http_url
    derive_logical_path = storage._derive_logical_path
    normalize_item_path = storage._normalize_item_path
    normalize_path = storage._normalize_path
    dedupe_path = storage._dedupe_path
    guess_mime = storage._guess_mime
    coerce_int = storage._coerce_int
    coerce_timestamp = storage._coerce_timestamp
    coerce_float = storage._coerce_float
    resolve_local_source = storage._resolve_local_source
    read_dimensions_fast = storage._read_dimensions_fast

    metric_columns = columns.metric_columns
    has_metrics_column = storage._metrics_column is not None

    for idx in range(row_count):
        source_value = source_values[idx]
        if source_value is None:
            progress.step()
            continue
        if isinstance(source_value, os.PathLike):
            source_value = os.fspath(source_value)
        if not isinstance(source_value, str):
            progress.step()
            continue

        source = source_value.strip()
        if not source:
            progress.step()
            continue

        fallback_name = extract_name(source)
        name_value = name_values[idx]
        name = str(name_value).strip() if name_value else fallback_name
        if not is_supported_image(name):
            if is_supported_image(fallback_name):
                name = fallback_name
            else:
                progress.step()
                continue

        logical_value = None
        if has_path_column and not is_s3_uri(source):
            logical_value = path_values[idx]
        logical_path = str(logical_value).strip() if logical_value else derive_logical_path(source)
        if logical_path and os.path.isabs(logical_path) and local_prefix:
            try:
                rel = os.path.relpath(logical_path, local_prefix)
                if not rel.startswith(".."):
                    logical_path = rel
            except ValueError:
                pass

        logical_path = normalize_item_path(logical_path)
        if not logical_path:
            progress.step()
            continue

        logical_path = dedupe_path(logical_path, seen_paths)
        seen_paths.add(logical_path)

        mime_value = mime_values[idx]
        mime = str(mime_value).strip() if mime_value else guess_mime(name or fallback_name or source)

        size = coerce_int(size_values[idx])
        mtime = coerce_timestamp(mtime_values[idx])
        width = coerce_int(width_values[idx])
        height = coerce_int(height_values[idx])

        is_s3 = is_s3_uri(source)
        is_http = is_http_url(source)
        is_local = not is_s3 and not is_http
        resolved_local_source: str | None = None

        if is_local:
            if not allow_local:
                skipped_local += 1
                progress.step()
                continue
            try:
                resolved_local_source = resolve_local_source(source)
            except ValueError:
                skipped_local += 1
                progress.step()
                continue
            if not os.path.exists(resolved_local_source):
                print(f"[lenslet] Warning: File not found: {resolved_local_source}")
                progress.step()
                continue
            if size is None:
                try:
                    size = os.path.getsize(resolved_local_source)
                except Exception:
                    size = 0

        if size is None:
            size = 0

        if mtime is None:
            if is_local:
                try:
                    local_source = resolved_local_source or resolve_local_source(source)
                    mtime = os.path.getmtime(local_source)
                except Exception:
                    mtime = time.time()
            else:
                mtime = time.time()

        discovered_dims = None
        w = width or 0
        h = height or 0
        if (w == 0 or h == 0) and is_local and not skip_indexing:
            try:
                local_source = resolved_local_source or resolve_local_source(source)
                dims = read_dimensions_fast(local_source)
                if dims:
                    w, h = dims
                    discovered_dims = dims
            except Exception:
                pass

        metrics: dict[str, float] = {}
        for metric_key, metric_values in metric_columns:
            num = coerce_float(metric_values[idx])
            if num is None:
                continue
            metrics[metric_key] = num

        if has_metrics_column:
            raw_metrics = metrics_values[idx]
            if isinstance(raw_metrics, dict):
                for raw_key, raw_value in raw_metrics.items():
                    num = coerce_float(raw_value)
                    if num is None:
                        continue
                    metrics[str(raw_key)] = num

        item = item_factory(
            path=logical_path,
            name=name,
            mime=mime,
            width=w,
            height=h,
            size=size,
            mtime=mtime or 0.0,
            url=source if is_http else None,
            source=source,
            metrics=metrics,
        )

        folder = os.path.dirname(logical_path).replace("\\", "/")
        folder_norm = normalize_path(folder)

        rows.append(
            ScannedRow(
                row_idx=idx,
                logical_path=logical_path,
                source=source,
                folder_norm=folder_norm,
                item=item,
                discovered_dims=discovered_dims,
            )
        )

        if (is_s3 or is_http) and (w == 0 or h == 0) and not skip_indexing:
            remote_tasks.append((logical_path, item, source, name))

        progress.step()

    progress.finish()
    return ScanResult(rows=rows, remote_tasks=remote_tasks, skipped_local=skipped_local)


def assemble_indexes(
    storage: Any,
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


def extract_row_metrics(storage: Any, row_idx: int) -> dict[str, float]:
    none_values: list[Any] = [None] * storage._row_count
    metric_columns = collect_metric_columns(storage, none_values)

    metrics: dict[str, float] = {}
    for column, values in metric_columns:
        num = storage._coerce_float(values[row_idx])
        if num is None:
            continue
        metrics[column] = num
    return metrics


def extract_row_metrics_map(storage: Any, row_idx: int) -> dict[str, float]:
    if not storage._metrics_column:
        return {}

    raw = storage._data.get(storage._metrics_column, [None] * storage._row_count)[row_idx]
    if not isinstance(raw, dict):
        return {}

    result: dict[str, float] = {}
    for key, value in raw.items():
        num = storage._coerce_float(value)
        if num is None:
            continue
        result[str(key)] = num
    return result
