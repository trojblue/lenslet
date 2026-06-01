from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path

from .pyarrow_runtime import pyarrow_exception_types, require_pyarrow_parquet

_SOURCE_MATCH_THRESHOLD = 0.7


@dataclass(frozen=True, slots=True)
class SourceColumnScore:
    name: str
    score: float
    total: int


def _table_value_errors() -> tuple[type[BaseException], ...]:
    return pyarrow_exception_types() + (AttributeError, KeyError, TypeError, ValueError)


def local_source_layout(table, column_name: str) -> tuple[list[str], bool]:
    try:
        values = table[column_name].to_pylist()
    except _table_value_errors():
        return [], False

    absolute_local_sources: list[str] = []
    has_relative_local_sources = False
    for value in values:
        candidate = normalized_source_text(value)
        if candidate is None or is_remote_source(candidate):
            continue
        if os.path.isabs(candidate):
            absolute_local_sources.append(os.path.abspath(candidate))
            continue
        has_relative_local_sources = True

    return absolute_local_sources, has_relative_local_sources


def path_is_within_root(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([root, path]) == root
    except ValueError:
        return False


def is_safe_auto_root(root: str) -> bool:
    segments = [segment for segment in Path(root).parts if segment not in {"", os.path.sep}]
    return len(segments) >= 2


def first_batch(parquet_file, sample_size: int):
    for candidate in parquet_file.iter_batches(batch_size=sample_size):
        return candidate
    return None


def normalized_source_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    return candidate or None


def is_remote_source(value: str) -> bool:
    return value.startswith("s3://") or value.startswith("http://") or value.startswith("https://")


def source_loadability_score(values: list[object], base_dir: str | None) -> tuple[int, int]:
    total = 0
    matches = 0
    for raw_value in values:
        value = normalized_source_text(raw_value)
        if value is None:
            continue
        total += 1
        if is_loadable_value(value, base_dir):
            matches += 1
    return total, matches


def source_column_score(name: str, batch, base_dir: str | None) -> SourceColumnScore | None:
    values = batch.column(name).to_pylist()
    total, matches = source_loadability_score(values, base_dir)
    if total == 0:
        return None
    score = matches / total
    if score < _SOURCE_MATCH_THRESHOLD:
        return None
    return SourceColumnScore(name=name, score=score, total=total)


def better_source_column(candidate: SourceColumnScore, current: SourceColumnScore | None) -> bool:
    if current is None:
        return True
    return candidate.score > current.score or (candidate.score == current.score and candidate.total > current.total)


def best_source_column(columns: list[str], batch, base_dir: str | None) -> str | None:
    best: SourceColumnScore | None = None
    for name in columns:
        score = source_column_score(name, batch, base_dir)
        if score is not None and better_source_column(score, best):
            best = score
    return best.name if best is not None else None


def detect_source_column(parquet_path: str, base_dir: str | None, sample_size: int = 50) -> str | None:
    parquet = require_pyarrow_parquet()
    parquet_file = parquet.ParquetFile(parquet_path)
    if parquet_file.metadata is not None and parquet_file.metadata.num_rows == 0:
        return None

    columns = parquet_file.schema_arrow.names
    if not columns:
        return None

    batch = first_batch(parquet_file, sample_size)
    if batch is None or batch.num_rows == 0:
        return None

    return best_source_column(columns, batch, base_dir)


def is_loadable_value(value: str, base_dir: str | None) -> bool:
    if is_remote_source(value):
        return True
    if os.path.isabs(value):
        return os.path.exists(value)
    if base_dir:
        return os.path.exists(os.path.join(base_dir, value))
    return False
