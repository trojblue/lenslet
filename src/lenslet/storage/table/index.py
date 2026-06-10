from __future__ import annotations

import math
import numbers
from typing import Any, TypeAlias

from .display import (
    is_internal_metric_key,
    normalize_display_value,
    normalize_metrics_display_value,
)
from .row_scan import IndexColumns
from .index_types import (
    ProgressCallback,
    TableIndexData,
    TableIndexInput,
    TableIndexPolicy,
    TableSourceResolver,
)
from ...metrics import coerce_finite_metric_value
from .schema import coerce_float

FORMULA_METRIC_EXACT_EXCLUSIONS = frozenset(
    {
        "bytes",
        "created",
        "created_at",
        "date",
        "display_path",
        "file_name",
        "filename",
        "h",
        "height",
        "id",
        "idx",
        "image_id",
        "image_path",
        "index",
        "local_path",
        "logical_path",
        "mime",
        "mime_type",
        "modified",
        "modified_at",
        "mtime",
        "name",
        "path",
        "pending_gpt_q4_value_view",
        "rel_path",
        "relative_path",
        "row_id",
        "row_idx",
        "row_index",
        "row_number",
        "s3",
        "s3_uri",
        "s3uri",
        "size",
        "source",
        "src",
        "time",
        "timestamp",
        "updated",
        "updated_at",
        "uri",
        "url",
        "w",
        "width",
    }
)
FORMULA_METRIC_BOOKKEEPING_SUFFIXES = (
    "_bytes",
    "_count",
    "_date",
    "_filename",
    "_height",
    "_id",
    "_idx",
    "_index",
    "_mime",
    "_mime_type",
    "_name",
    "_num",
    "_number",
    "_path",
    "_size",
    "_source",
    "_src",
    "_time",
    "_timestamp",
    "_total",
    "_uri",
    "_url",
    "_width",
)
FORMULA_METRIC_BOOKKEEPING_PREFIXES = (
    "count_",
    "has_",
    "is_",
    "num_",
    "total_",
    "was_",
)

__all__ = [
    "IndexColumns",
    "ProgressCallback",
    "TableIndexData",
    "TableIndexInput",
    "TableIndexPolicy",
    "TableSourceResolver",
    "build_index_columns",
    "collect_metric_columns",
    "extract_row_display_fields",
    "extract_row_metrics",
    "extract_row_metrics_map",
    "is_formula_metric_column_name",
    "is_metric_column_name",
]


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


def _metric_candidate_columns(context: TableIndexInput) -> list[str]:
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

    candidates: list[str] = []
    for column in table.columns:
        if column in used_columns:
            continue
        if column.lower() in table.reserved_columns:
            continue
        if is_internal_metric_key(column):
            continue
        if not is_formula_metric_column_name(column):
            continue
        values = table.column_values.get(column)
        if not _column_values_are_numeric_metric(
            values
        ) and not _q_style_metric_values_are_numeric_or_missing(column, values):
            continue
        candidates.append(column)
    return candidates


def _metric_column_leaf(column: str) -> str:
    return column.rsplit("__", 1)[-1].strip().lower()


def is_metric_column_name(column: str) -> bool:
    return is_formula_metric_column_name(column)


def is_formula_metric_column_name(column: str) -> bool:
    normalized = column.strip().lower()
    leaf = _metric_column_leaf(column)
    if is_internal_metric_key(column):
        return False
    if normalized in FORMULA_METRIC_EXACT_EXCLUSIONS or leaf in FORMULA_METRIC_EXACT_EXCLUSIONS:
        return False
    if normalized.startswith("__") and normalized.endswith("__"):
        return False
    if leaf.startswith(FORMULA_METRIC_BOOKKEEPING_PREFIXES):
        return False
    if leaf.endswith(FORMULA_METRIC_BOOKKEEPING_SUFFIXES):
        return False
    return True


def _is_q_style_metric_column_name(column: str) -> bool:
    leaf = _metric_column_leaf(column)
    return len(leaf) > 1 and leaf.startswith("q") and leaf[1].isdigit()


def _coerce_scalar(value: object) -> object:
    if hasattr(value, "as_py"):
        try:
            return value.as_py()
        except Exception:
            return value
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    return value


def _column_values_are_numeric_metric(values: Any, *, sample_size: int = 256) -> bool:
    if values is None:
        return False
    typed = _typed_values_are_numeric_metric(values)
    if typed is not None:
        return typed

    saw_numeric = False
    checked = 0
    try:
        iterator = iter(values)
    except TypeError:
        return False
    for raw_value in iterator:
        value = _coerce_scalar(raw_value)
        if value is None:
            continue
        if isinstance(value, float) and math.isnan(value):
            saw_numeric = True
            checked += 1
        elif isinstance(value, bool) or not isinstance(value, numbers.Real):
            return False
        else:
            saw_numeric = True
            checked += 1
        if checked >= sample_size:
            break
    return saw_numeric


def _q_style_metric_values_are_numeric_or_missing(
    column: str,
    values: Any,
    *,
    sample_size: int = 256,
) -> bool:
    if values is None or not _is_q_style_metric_column_name(column):
        return False
    saw_value = False
    checked = 0
    try:
        iterator = iter(values)
    except TypeError:
        return False
    for raw_value in iterator:
        saw_value = True
        value = _coerce_scalar(raw_value)
        if value is not None and coerce_finite_metric_value(value) is None:
            return False
        checked += 1
        if checked >= sample_size:
            break
    return saw_value


def _typed_values_are_numeric_metric(values: Any) -> bool | None:
    dtype = getattr(values, "dtype", None)
    dtype_kind = getattr(dtype, "kind", None)
    if isinstance(dtype_kind, str):
        if dtype_kind == "b":
            return False
        if dtype_kind in {"i", "u", "f"}:
            return True

    type_text = str(getattr(values, "type", "")).lower()
    if not type_text:
        return None
    if type_text.startswith("bool"):
        return False
    if type_text.startswith(("int", "uint", "float", "double", "halffloat", "decimal")):
        return True
    return None


def _column_values_are_boolean_only(values: Any, *, sample_size: int = 128) -> bool:
    if values is None:
        return False
    checked = 0
    try:
        iterator = iter(values)
    except TypeError:
        return False
    for raw_value in iterator:
        value = _coerce_scalar(raw_value)
        if value is None:
            continue
        if not isinstance(value, bool):
            return False
        checked += 1
        if checked >= sample_size:
            break
    return checked > 0


def collect_metric_columns(
    context: TableIndexInput,
    none_values: list[Any],
) -> tuple[tuple[str, list[Any]], ...]:
    table = context.table
    metric_columns: list[tuple[str, list[Any]]] = []
    for column in _metric_candidate_columns(context):
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
        num = coerce_finite_metric_value(values[row_idx])
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
        num = coerce_finite_metric_value(value)
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
