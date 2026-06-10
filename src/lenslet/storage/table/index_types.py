from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeAlias

from ..image_media import ImageMime

ProgressCallback: TypeAlias = Callable[[int, int, str], None]


@dataclass(frozen=True, slots=True)
class TableCachedRowDimensions:
    """Workspace-cached dimensions validated against row source identity."""

    source: str
    logical_path: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class TableIndexData:
    """Immutable table data and resolved schema choices used by the indexer."""

    root: str | None
    row_count: int
    column_values: dict[str, list[Any]]
    columns: list[str]
    source_column: str
    path_column: str | None
    name_column: str | None
    mime_column: str | None
    width_column: str | None
    height_column: str | None
    size_column: str | None
    mtime_column: str | None
    metrics_column: str | None
    categorical_columns: tuple[str, ...]
    reserved_columns: set[str]
    local_prefix: str | None
    s3_prefixes: dict[str, str]
    s3_use_bucket: bool
    image_exts: tuple[str, ...]
    source_kind: str | None = None
    extensionless_source_all_trusted: bool = False
    dimension_overrides: Mapping[int, TableCachedRowDimensions] | None = None


@dataclass(frozen=True, slots=True)
class TableIndexPolicy:
    """Table index switches that affect source validation and dimension probing."""

    allow_local: bool
    skip_dimension_probe: bool
    skip_local_realpath_validation: bool


@dataclass(frozen=True, slots=True)
class TableSourceResolver:
    """Storage-specific source behavior needed by the pure table indexer."""

    guess_mime: Callable[[str], ImageMime]
    allows_extensionless_source_image: Callable[[str], bool]
    resolve_local_source: Callable[[str], str]
    resolve_local_source_lexical: Callable[[str], str]


@dataclass(frozen=True, slots=True)
class TableIndexInput:
    """Explicit table-indexing boundary supplied by TableStorage."""

    table: TableIndexData
    policy: TableIndexPolicy
    source_resolver: TableSourceResolver
    progress: ProgressCallback
