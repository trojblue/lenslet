from __future__ import annotations

import math
import os
from datetime import datetime
from typing import Any, Callable, Iterable


def resolve_named_column(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    candidates_lower = {candidate.lower() for candidate in candidates}
    for column in columns:
        if column.lower() in candidates_lower:
            return column
    return None


def resolve_column(columns: list[str], name: str) -> str | None:
    for column in columns:
        if column == name:
            return column
    name_lower = name.lower()
    for column in columns:
        if column.lower() == name_lower:
            return column
    return None


def iter_sample(values: list[Any]) -> Iterable[str]:
    for value in values:
        if value is None:
            continue
        if isinstance(value, float) and math.isnan(value):
            continue
        if isinstance(value, os.PathLike):
            value = os.fspath(value)
        if not isinstance(value, str):
            continue
        cleaned = value.strip()
        if not cleaned:
            continue
        yield cleaned


def loadable_score(
    values: list[Any],
    *,
    sample_size: int,
    is_loadable_value: Callable[[str], bool],
) -> tuple[int, int]:
    total = 0
    matches = 0
    for value in iter_sample(values):
        total += 1
        if is_loadable_value(value):
            matches += 1
        if total >= sample_size:
            break
    return total, matches


def resolve_source_column(
    columns: list[str],
    data: dict[str, list[Any]],
    source_column: str | None,
    *,
    loadable_threshold: float,
    sample_size: int,
    allow_local: bool,
    is_loadable_value: Callable[[str], bool],
) -> str:
    if source_column:
        resolved = resolve_column(columns, source_column)
        if resolved is None:
            raise ValueError(f"source column '{source_column}' not found")
        return resolved

    for column in columns:
        total, matches = loadable_score(
            data.get(column, []),
            sample_size=sample_size,
            is_loadable_value=is_loadable_value,
        )
        if total == 0:
            continue
        if matches / total >= loadable_threshold:
            return column

    if not allow_local:
        raise ValueError(
            "No loadable column found. Local file sources are disabled; provide an S3/HTTP column."
        )
    raise ValueError(
        "No loadable column found. Pass source_column explicitly or provide a base_dir for local paths."
    )


def resolve_path_column(
    columns: list[str],
    path_column: str | None,
    *,
    logical_path_columns: tuple[str, ...],
) -> str | None:
    if path_column:
        resolved = resolve_column(columns, path_column)
        if resolved is None:
            raise ValueError(f"path column '{path_column}' not found")
        return resolved
    return resolve_named_column(columns, logical_path_columns)


def coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def coerce_timestamp(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        return float(value.timestamp())
    if hasattr(value, "timestamp"):
        try:
            return float(value.timestamp())
        except Exception:
            return None
    return coerce_float(value)
