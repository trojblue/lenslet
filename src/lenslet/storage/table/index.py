from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, TypeAlias

from .display import (
    is_internal_metric_key,
    normalize_display_value,
    normalize_metrics_display_value,
)
from ..index_assembly import IndexAssemblyResult, assemble_indexes
from .row_scan import IndexColumns, RemoteDimensionTask, ScanResult, scan_rows
from .index_types import (
    ProgressCallback,
    TableIndexData,
    TableIndexInput,
    TableIndexPolicy,
    TableSourceResolver,
)
from .schema import coerce_float

__all__ = [
    "IndexColumns",
    "ProgressCallback",
    "RemoteDimensionTask",
    "ScanResult",
    "TableIndexData",
    "TableIndexInput",
    "TableIndexPolicy",
    "TableSourceResolver",
    "build_index_columns",
    "build_table_indexes",
    "collect_metric_columns",
    "extract_row_display_fields",
    "extract_row_metrics",
    "extract_row_metrics_map",
    "scan_rows",
]


def build_table_indexes(
    context: TableIndexInput,
    *,
    item_factory: Callable[..., Any],
    index_factory: Callable[..., Any],
) -> IndexAssemblyResult:
    generated_at = datetime.now(timezone.utc).isoformat()
    columns = build_index_columns(context)
    scan = scan_rows(context, columns, item_factory=item_factory)
    result = assemble_indexes(
        scan.rows,
        generated_at=generated_at,
        row_count=context.table.row_count,
        index_factory=index_factory,
    )
    result.remote_tasks = scan.remote_tasks
    result.skipped_local_disabled = scan.skipped_local_disabled
    result.skipped_local_outside_root = scan.skipped_local_outside_root
    result.skipped_local_resolved_outside_root = scan.skipped_local_resolved_outside_root
    result.skipped_local_missing = scan.skipped_local_missing

    if scan.skipped_local_disabled:
        print(f"[lenslet] Skipped {scan.skipped_local_disabled} local path(s): local sources are disabled.")
    if scan.skipped_local_outside_root:
        boundary = context.table.root or "(unset)"
        print(
            f"[lenslet] Skipped {scan.skipped_local_outside_root} local path(s) outside "
            f"base_dir boundary: {boundary}"
        )
    if scan.skipped_local_resolved_outside_root:
        boundary = context.table.root or "(unset)"
        print(
            f"[lenslet] Skipped {scan.skipped_local_resolved_outside_root} local path(s) that are "
            f"inside base_dir but resolve outside it: {boundary}. "
            "This commonly means symlinks point outside the launched directory."
        )
    if scan.skipped_local_missing:
        print(f"[lenslet] Skipped {scan.skipped_local_missing} missing local path(s).")
    return result


def build_index_columns(context: TableIndexInput) -> IndexColumns:
    table = context.table
    row_count = table.row_count
    none_values: list[Any] = [None] * row_count

    def values_for(column: str | None) -> list[Any]:
        if not column:
            return none_values
        return table.column_values.get(column, none_values)

    return IndexColumns(
        source_values=values_for(table.source_column),
        path_values=values_for(table.path_column),
        name_values=values_for(table.name_column),
        mime_values=values_for(table.mime_column),
        width_values=values_for(table.width_column),
        height_values=values_for(table.height_column),
        size_values=values_for(table.size_column),
        mtime_values=values_for(table.mtime_column),
        metrics_values=values_for(table.metrics_column),
        metric_columns=collect_metric_columns(context, none_values),
    )


def collect_metric_columns(
    context: TableIndexInput,
    none_values: list[Any],
) -> tuple[tuple[str, list[Any]], ...]:
    table = context.table
    used_columns = {
        table.source_column,
        table.path_column,
        table.name_column,
        table.mime_column,
        table.width_column,
        table.height_column,
        table.size_column,
        table.mtime_column,
    }

    metric_columns: list[tuple[str, list[Any]]] = []
    for column in table.columns:
        if column in used_columns:
            continue
        if column.lower() in table.reserved_columns:
            continue
        if is_internal_metric_key(column):
            continue
        metric_columns.append((column, table.column_values.get(column, none_values)))
    return tuple(metric_columns)


def _duplicate_display_columns(context: TableIndexInput) -> set[str]:
    table = context.table
    return {
        column
        for column in (
            table.source_column,
            table.path_column,
            table.name_column,
            table.mime_column,
            table.width_column,
            table.height_column,
            table.size_column,
            table.mtime_column,
        )
        if column
    }


def extract_row_metrics(context: TableIndexInput, row_idx: int) -> dict[str, float]:
    table = context.table
    none_values: list[Any] = [None] * table.row_count
    metric_columns = collect_metric_columns(context, none_values)

    metrics: dict[str, float] = {}
    for column, values in metric_columns:
        num = coerce_float(values[row_idx])
        if num is None:
            continue
        metrics[column] = num
    return metrics


def extract_row_metrics_map(context: TableIndexInput, row_idx: int) -> dict[str, float]:
    table = context.table
    if not table.metrics_column:
        return {}

    raw = table.column_values.get(table.metrics_column, [None] * table.row_count)[row_idx]
    if not isinstance(raw, dict):
        return {}

    result: dict[str, float] = {}
    for key, value in raw.items():
        if is_internal_metric_key(key):
            continue
        num = coerce_float(value)
        if num is None:
            continue
        result[str(key)] = num
    return result


def extract_row_display_fields(context: TableIndexInput, row_idx: int) -> dict[str, Any]:
    table = context.table
    none_values: list[Any] = [None] * table.row_count
    metric_columns = {
        column
        for column, _values in collect_metric_columns(context, none_values)
    }
    duplicate_columns = _duplicate_display_columns(context)

    display_fields: dict[str, Any] = {}
    for column in table.columns:
        if is_internal_metric_key(column):
            continue
        if column in duplicate_columns:
            continue

        raw_value = table.column_values.get(column, none_values)[row_idx]
        if column == table.metrics_column:
            display_value = normalize_metrics_display_value(raw_value)
        else:
            if column in metric_columns and coerce_float(raw_value) is not None:
                continue
            display_value = normalize_display_value(raw_value)
        if display_value is None:
            continue
        display_fields[column] = display_value

    return display_fields
