from __future__ import annotations

import math
import os
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from .display import is_internal_metric_key

CATEGORICAL_MAX_UNIQUE_VALUES = 60
CATEGORICAL_MAX_VALUE_LENGTH = 256

_CATEGORICAL_IDENTIFIER_LEAVES = {
    "id",
    "key",
    "hash",
    "sha",
    "source",
    "src",
    "url",
    "uri",
    "path",
    "s3key",
    "local_path",
    "image_path",
    "logical_path",
    "rel_path",
    "relative_path",
    "display_path",
    "name",
    "filename",
    "file_name",
    "mime",
    "mime_type",
}
_CATEGORICAL_LONG_TEXT_LEAVES = {
    "caption",
    "captions",
    "comment",
    "comments",
    "description",
    "explanation",
    "notes",
    "prompt",
    "prompts",
    "reason",
    "reasoning",
    "text",
}


def is_categorical_identifier_column(column: str) -> bool:
    lower = column.strip().lower()
    if not lower:
        return True
    leaf = lower.rsplit("__", 1)[-1]
    if lower in _CATEGORICAL_IDENTIFIER_LEAVES or leaf in _CATEGORICAL_IDENTIFIER_LEAVES:
        return True
    if leaf in _CATEGORICAL_LONG_TEXT_LEAVES:
        return True
    return leaf.endswith((
        "_id",
        "_key",
        "_hash",
        "_url",
        "_uri",
        "_path",
        "_caption",
        "_comment",
        "_description",
        "_explanation",
        "_notes",
        "_prompt",
        "_reason",
        "_reasoning",
        "_text",
    ))


def normalize_categorical_value(value: object) -> str | None:
    value = _as_python_scalar(value)
    if _is_null_scalar(value):
        return None
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) > CATEGORICAL_MAX_VALUE_LENGTH:
        return None
    return text


def categorical_value_too_long(value: object) -> bool:
    value = _as_python_scalar(value)
    if _is_null_scalar(value):
        return False
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
    return isinstance(value, str) and len(value.strip()) > CATEGORICAL_MAX_VALUE_LENGTH


def arrow_array_has_low_cardinality(
    values: Any,
    compute: Any,
    *,
    max_unique_values: int = CATEGORICAL_MAX_UNIQUE_VALUES,
    error_types: tuple[type[BaseException], ...] = (
        AttributeError,
        ImportError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    ),
) -> bool:
    unique_values: set[str] = set()
    try:
        unique = compute.unique(values)
        if len(unique) > max_unique_values + 2:
            return False
        raw_values = unique.to_pylist()
    except error_types:
        return False

    for raw_value in raw_values:
        value = normalize_categorical_value(raw_value)
        if value is None:
            if categorical_value_too_long(raw_value):
                return False
            continue
        unique_values.add(value)
        if len(unique_values) >= max_unique_values:
            return False
    return 0 < len(unique_values) < max_unique_values


def infer_categorical_columns(
    *,
    columns: Sequence[str],
    data: Mapping[str, Any],
    source_column: str | None,
    path_column: str | None,
    name_column: str | None,
    mime_column: str | None,
    width_column: str | None,
    height_column: str | None,
    size_column: str | None,
    mtime_column: str | None,
    metrics_column: str | None,
    max_unique_values: int = CATEGORICAL_MAX_UNIQUE_VALUES,
) -> tuple[str, ...]:
    display_columns = {
        column
        for column in (
            source_column,
            path_column,
            name_column,
            mime_column,
            width_column,
            height_column,
            size_column,
            mtime_column,
            metrics_column,
        )
        if column
    }
    selected: list[str] = []
    for column in columns:
        if column in display_columns:
            continue
        if is_internal_metric_key(column):
            continue
        if is_categorical_identifier_column(column):
            continue
        if _column_has_low_cardinality_strings(
            data.get(column),
            max_unique_values=max_unique_values,
        ):
            selected.append(column)
    return tuple(selected)


def _column_has_low_cardinality_strings(
    values: Any,
    *,
    max_unique_values: int,
) -> bool:
    unique_values: set[str] = set()
    for raw_value in _iter_values(values):
        value = normalize_categorical_value(raw_value)
        if value is None:
            if categorical_value_too_long(raw_value):
                return False
            if _is_null_or_blank_string(raw_value):
                continue
            return False
        unique_values.add(value)
        if len(unique_values) >= max_unique_values:
            return False
    return 0 < len(unique_values) < max_unique_values


def _iter_values(values: Any) -> Iterator[Any]:
    if values is None:
        return
    try:
        iterator = iter(values)
    except TypeError:
        return
    yield from iterator


def _is_null_or_blank_string(value: object) -> bool:
    value = _as_python_scalar(value)
    if _is_null_scalar(value):
        return True
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
    return isinstance(value, str) and not value.strip()


def _as_python_scalar(value: object) -> object:
    for method_name in ("as_py", "item"):
        method = getattr(value, method_name, None)
        if not callable(method):
            continue
        try:
            converted = method()
        except Exception:
            continue
        if converted is not value:
            return converted
    return value


def _is_null_scalar(value: object) -> bool:
    if value is None:
        return True
    if value.__class__.__name__ in {"NAType", "NaTType"}:
        return True
    if isinstance(value, float):
        return math.isnan(value)
    return False
