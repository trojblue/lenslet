from __future__ import annotations

import logging
import os
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeAlias

from .categoricals import (
    CATEGORICAL_MAX_UNIQUE_VALUES,
    arrow_array_has_low_cardinality,
    is_categorical_identifier_column,
)
from ...embeddings.config import EmbeddingConfig
from .display import is_internal_metric_key
from .dimension_cache import (
    TableDimensionCacheRow,
    load_dimension_cache,
    table_dimension_cache_identity,
    write_dimension_cache,
)
from .index import is_formula_metric_column_name
from .launch_sources import (
    detect_source_column,
    is_safe_auto_root,
    local_source_layout,
    path_is_within_root,
    source_column_score,
)
from .pyarrow_runtime import pyarrow_exception_types, require_pyarrow, require_pyarrow_parquet
from .schema import resolve_column, resolve_named_column, resolve_path_column

if TYPE_CHECKING:
    from ...embeddings.detect import EmbeddingDetection as EmbeddingDetectionType
    from .storage import TableStorage, TableStorageOptions

else:
    EmbeddingDetectionType: TypeAlias = Any

PyArrowTable: TypeAlias = Any

logger = logging.getLogger(__name__)

_DIMENSION_VALUE_ERRORS = (OverflowError, TypeError, ValueError)
_LOGICAL_PATH_COLUMNS = (
    "path",
    "logical_path",
    "rel_path",
    "relative_path",
    "display_path",
)
_NAME_COLUMNS = ("name", "filename", "file_name")
_MIME_COLUMNS = ("mime", "mime_type")
_WIDTH_COLUMNS = ("width", "w")
_HEIGHT_COLUMNS = ("height", "h")
_SIZE_COLUMNS = ("size", "bytes")
_MTIME_COLUMNS = ("mtime", "modified", "modified_at")


def _table_schema_errors() -> tuple[type[BaseException], ...]:
    return pyarrow_exception_types() + (
        AttributeError,
        ImportError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
    )


def _parquet_row_field_read_errors() -> tuple[type[BaseException], ...]:
    return pyarrow_exception_types() + (
        IndexError,
        KeyError,
        OSError,
        ValueError,
    )


class _LazyTableStorage:
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        from .storage import TableStorage as RealTableStorage

        return RealTableStorage(*args, **kwargs)


class _LazyTableStorageOptions:
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        from .storage import TableStorageOptions as RealTableStorageOptions

        return RealTableStorageOptions(*args, **kwargs)


if not TYPE_CHECKING:
    TableStorage = _LazyTableStorage()
    TableStorageOptions = _LazyTableStorageOptions()


def load_parquet_table(path: str, columns: list[str] | None = None) -> Any:
    from .storage import load_parquet_table as real_load_parquet_table

    return real_load_parquet_table(path, columns=columns)


def load_parquet_schema(path: str) -> Any:
    from .storage import load_parquet_schema as real_load_parquet_schema

    return real_load_parquet_schema(path)


@dataclass(frozen=True, slots=True)
class TableLaunchNotice:
    kind: str
    message: str


@dataclass(frozen=True, slots=True)
class TableLaunchResult:
    storage: TableStorage
    effective_root: str | None
    default_root: str
    embedding_detection: EmbeddingDetectionType | None = None
    notices: tuple[TableLaunchNotice, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class TableLaunchRequest:
    parquet_path: Path
    base_dir: str | None
    source_column: str | None
    cache_dimensions: bool
    skip_dimension_probe: bool
    path_column: str | None = None
    dimension_cache_dir: Path | None = None
    embedding_config: EmbeddingConfig | None = None
    auto_detect_root: bool = False
    thumb_size: int = 256
    thumb_quality: int = 70


@dataclass(frozen=True, slots=True)
class EmbeddingColumnSelection:
    columns: list[str] | None
    detection: EmbeddingDetectionType | None = None
    schema: Any | None = None
    notices: tuple[TableLaunchNotice, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class BrowseColumnSelection:
    columns: list[str] | None
    source_column: str | None
    path_column: str | None
    table_field_columns: tuple[str, ...]
    categorical_columns: tuple[str, ...]
    is_projected: bool


@dataclass(frozen=True, slots=True)
class TableDimensionState:
    width_name: str | None
    height_name: str | None
    missing_count: int


@dataclass(frozen=True, slots=True)
class TableDimensionProbePolicy:
    skip_dimension_probe: bool
    notices: tuple[TableLaunchNotice, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class TableRootResolution:
    effective_root: str | None
    default_root: str
    notices: tuple[TableLaunchNotice, ...] = field(default_factory=tuple)


def prepare_table_launch(request: TableLaunchRequest) -> TableLaunchResult:
    parquet_path = request.parquet_path
    column_selection = select_embedding_columns(parquet_path, request.embedding_config)
    schema = column_selection.schema or load_parquet_schema(str(parquet_path))
    browse_columns = select_browse_columns(
        parquet_path=parquet_path,
        request=request,
        schema=schema,
        readable_columns=column_selection.columns,
    )
    table = load_parquet_table(str(parquet_path), columns=browse_columns.columns)
    workspace_dimension_cache_enabled = request.dimension_cache_dir is not None
    dimensions = inspect_table_dimensions(
        table,
        count_missing=request.cache_dimensions or workspace_dimension_cache_enabled,
    )
    dimension_probe_policy = resolve_dimension_probe_policy(
        cache_dimensions=request.cache_dimensions or workspace_dimension_cache_enabled,
        skip_dimension_probe=request.skip_dimension_probe,
        missing_dimensions=dimensions.missing_count,
    )
    root_resolution = resolve_launch_root(
        parquet_path=parquet_path,
        table=table,
        source_column=browse_columns.source_column or request.source_column,
        base_dir=request.base_dir,
        auto_detect_root=request.auto_detect_root,
    )
    dimension_cache_identity = (
        table_dimension_cache_identity(
            parquet_path=parquet_path,
            schema=schema,
            row_count=table.num_rows,
            source_column=browse_columns.source_column or request.source_column,
            path_column=browse_columns.path_column,
            root=root_resolution.effective_root,
            base_dir=request.base_dir,
            workspace_cache_dir=request.dimension_cache_dir,
        )
        if request.dimension_cache_dir is not None
        else None
    )
    dimension_overrides = load_dimension_cache(
        request.dimension_cache_dir,
        dimension_cache_identity,
    )
    row_field_provider = (
        ParquetRowFieldProvider(parquet_path, browse_columns.table_field_columns)
        if browse_columns.is_projected and browse_columns.table_field_columns
        else None
    )
    categorical_row_provider = (
        ArrowTableRowFieldProvider(
            load_parquet_table(str(parquet_path), columns=list(browse_columns.categorical_columns))
        )
        if browse_columns.categorical_columns
        else None
    )
    storage = TableStorage(
        table=table,
        options=TableStorageOptions(
            root=root_resolution.effective_root,
            thumb_size=request.thumb_size,
            thumb_quality=request.thumb_quality,
            source_column=browse_columns.source_column or request.source_column,
            path_column=request.path_column,
            skip_dimension_probe=dimension_probe_policy.skip_dimension_probe,
            row_field_provider=row_field_provider,
            table_field_columns=browse_columns.table_field_columns,
            categorical_columns=browse_columns.categorical_columns,
            categorical_row_provider=categorical_row_provider,
            browse_signature_seed=parquet_browse_signature_seed(parquet_path),
            dimension_overrides=dimension_overrides,
        ),
    )

    notices = [
        *column_selection.notices,
        *dimension_probe_policy.notices,
        *root_resolution.notices,
        *cache_missing_dimensions(
            cache_dimensions=request.cache_dimensions,
            parquet_path=parquet_path,
            table=table,
            table_is_projected=browse_columns.is_projected,
            dimensions=dimensions,
            row_dims=storage.row_dimensions(),
        ),
        *cache_workspace_dimensions(
            dimension_cache_dir=request.dimension_cache_dir,
            dimension_cache_identity=dimension_cache_identity,
            rows=storage.dimension_cache_rows(),
        ),
    ]

    return TableLaunchResult(
        storage=storage,
        effective_root=root_resolution.effective_root,
        default_root=root_resolution.default_root,
        embedding_detection=column_selection.detection,
        notices=tuple(notices),
    )


def select_embedding_columns(
    parquet_path: Path,
    embedding_config: EmbeddingConfig | None,
) -> EmbeddingColumnSelection:
    if embedding_config is None:
        return EmbeddingColumnSelection(columns=None)

    try:
        from ...embeddings.detect import columns_without_embeddings, detect_embeddings

        schema = load_parquet_schema(str(parquet_path))
        detection = detect_embeddings(schema, embedding_config)
        return EmbeddingColumnSelection(
            columns=columns_without_embeddings(schema, detection),
            detection=detection,
            schema=schema,
        )
    except _table_schema_errors() as exc:
        return EmbeddingColumnSelection(
            columns=None,
            notices=(
                TableLaunchNotice(
                    kind="embedding_detection_degraded",
                    message=f"failed to detect embedding columns: {exc}",
                ),
            ),
        )


def select_browse_columns(
    *,
    parquet_path: Path,
    request: TableLaunchRequest,
    schema: Any,
    readable_columns: list[str] | None,
) -> BrowseColumnSelection:
    schema_names = list(schema.names)
    readable = set(readable_columns) if readable_columns is not None else set(schema_names)
    source_column = resolve_launch_source_column(parquet_path, request, schema_names)
    if source_column is None:
        return BrowseColumnSelection(
            columns=readable_columns,
            source_column=None,
            path_column=request.path_column,
            table_field_columns=(),
            categorical_columns=(),
            is_projected=readable_columns is not None,
        )

    path_column = resolve_path_column(
        schema_names,
        request.path_column,
        logical_path_columns=_LOGICAL_PATH_COLUMNS,
    )
    selected: list[str] = []

    def add(column: str | None) -> None:
        if column is None or column not in readable or column in selected:
            return
        selected.append(column)

    add(source_column)
    add(path_column)
    for candidates in (
        _NAME_COLUMNS,
        _MIME_COLUMNS,
        _WIDTH_COLUMNS,
        _HEIGHT_COLUMNS,
        _SIZE_COLUMNS,
        _MTIME_COLUMNS,
    ):
        add(resolve_named_column(schema_names, candidates))
    metrics_column = next((name for name in schema_names if name.lower() == "metrics"), None)
    add(metrics_column)
    for column in select_source_candidate_columns(
        parquet_path=parquet_path,
        request=request,
        schema=schema,
        readable=readable,
        source_column=source_column,
    ):
        add(column)
    for column in schema_names:
        if column not in readable:
            continue
        if not is_formula_metric_browse_column(schema, column):
            continue
        add(column)

    table_field_columns = select_table_field_columns(
        schema=schema,
        readable=readable,
        source_column=source_column,
        path_column=path_column,
    )
    categorical_columns = select_categorical_columns(
        parquet_path=parquet_path,
        schema=schema,
        readable=readable,
        source_column=source_column,
        path_column=path_column,
        table_field_columns=tuple(table_field_columns),
    )

    return BrowseColumnSelection(
        columns=selected,
        source_column=source_column,
        path_column=path_column,
        table_field_columns=tuple(table_field_columns),
        categorical_columns=tuple(categorical_columns),
        is_projected=set(selected) != readable,
    )


def resolve_launch_source_column(
    parquet_path: Path,
    request: TableLaunchRequest,
    schema_names: list[str],
) -> str | None:
    if request.source_column:
        resolved = resolve_column(schema_names, request.source_column)
        if resolved is None:
            raise ValueError(f"source column '{request.source_column}' not found")
        return resolved
    default_root = os.path.abspath(str(parquet_path.parent))
    return detect_source_column(str(parquet_path), request.base_dir or default_root)


def select_source_candidate_columns(
    *,
    parquet_path: Path,
    request: TableLaunchRequest,
    schema: Any,
    readable: set[str],
    source_column: str,
    sample_size: int = 50,
) -> tuple[str, ...]:
    candidate_columns = [
        column
        for column in schema.names
        if (
            column != source_column
            and column in readable
            and is_string_browse_column(schema, column)
            and is_browse_scalar_column(schema, column)
        )
    ]
    if not candidate_columns:
        return ()
    try:
        parquet = require_pyarrow_parquet()
        parquet_file = parquet.ParquetFile(str(parquet_path))
        batch = next(
            parquet_file.iter_batches(batch_size=sample_size, columns=candidate_columns),
            None,
        )
    except _table_schema_errors():
        return ()
    if batch is None or getattr(batch, "num_rows", 0) == 0:
        return ()

    default_root = os.path.abspath(str(parquet_path.parent))
    base_dir = request.base_dir or default_root
    candidates: list[tuple[float, str]] = []
    for column in candidate_columns:
        score = source_column_score(column, batch, base_dir)
        if score is None:
            continue
        candidates.append((score.score, column))
    return tuple(column for _score, column in sorted(candidates, reverse=True))


def is_browse_scalar_column(schema: Any, column: str) -> bool:
    try:
        pyarrow, _parquet = require_pyarrow()
        dtype = schema.field(column).type
        return not (
            pyarrow.types.is_list(dtype)
            or pyarrow.types.is_large_list(dtype)
            or pyarrow.types.is_fixed_size_list(dtype)
        )
    except _table_schema_errors():
        return True


def is_numeric_browse_column(schema: Any, column: str) -> bool:
    try:
        pyarrow, _parquet = require_pyarrow()
        dtype = schema.field(column).type
        return (
            pyarrow.types.is_integer(dtype)
            or pyarrow.types.is_floating(dtype)
            or pyarrow.types.is_decimal(dtype)
        )
    except _table_schema_errors():
        return False


def is_boolean_browse_column(schema: Any, column: str) -> bool:
    try:
        pyarrow, _parquet = require_pyarrow()
        dtype = schema.field(column).type
        return pyarrow.types.is_boolean(dtype)
    except _table_schema_errors():
        return False


def is_formula_metric_browse_column(schema: Any, column: str) -> bool:
    if not is_formula_metric_column_name(column):
        return False
    if not is_numeric_browse_column(schema, column):
        return False
    if is_boolean_browse_column(schema, column):
        return False
    return is_browse_scalar_column(schema, column)


def is_string_browse_column(schema: Any, column: str) -> bool:
    try:
        pyarrow, _parquet = require_pyarrow()
        dtype = schema.field(column).type
        if pyarrow.types.is_string(dtype) or pyarrow.types.is_large_string(dtype):
            return True
        if pyarrow.types.is_dictionary(dtype):
            value_type = dtype.value_type
            return pyarrow.types.is_string(value_type) or pyarrow.types.is_large_string(value_type)
        return False
    except _table_schema_errors():
        return False


def _duplicate_display_columns(
    *,
    source_column: str,
    path_column: str | None,
    schema_names: list[str],
) -> set[str]:
    return {
        column
        for column in (
            source_column,
            path_column,
            resolve_named_column(schema_names, _NAME_COLUMNS),
            resolve_named_column(schema_names, _MIME_COLUMNS),
            resolve_named_column(schema_names, _WIDTH_COLUMNS),
            resolve_named_column(schema_names, _HEIGHT_COLUMNS),
            resolve_named_column(schema_names, _SIZE_COLUMNS),
            resolve_named_column(schema_names, _MTIME_COLUMNS),
        )
        if column
    }


def select_table_field_columns(
    *,
    schema: Any,
    readable: set[str],
    source_column: str,
    path_column: str | None,
) -> list[str]:
    schema_names = list(schema.names)
    duplicates = _duplicate_display_columns(
        source_column=source_column,
        path_column=path_column,
        schema_names=schema_names,
    )
    fields: list[str] = []
    for column in schema_names:
        if column not in readable:
            continue
        if column in duplicates:
            continue
        if is_internal_metric_key(column):
            continue
        if column.lower() != "metrics" and is_formula_metric_browse_column(schema, column):
            continue
        if not is_browse_scalar_column(schema, column):
            continue
        fields.append(column)
    return fields


def select_categorical_columns(
    *,
    parquet_path: Path,
    schema: Any,
    readable: set[str],
    source_column: str,
    path_column: str | None,
    table_field_columns: tuple[str, ...],
    max_unique_values: int = CATEGORICAL_MAX_UNIQUE_VALUES,
) -> tuple[str, ...]:
    candidates = [
        column
        for column in table_field_columns
        if (
            column in readable
            and not is_categorical_identifier_column(column)
            and column not in _duplicate_display_columns(
                source_column=source_column,
                path_column=path_column,
                schema_names=list(schema.names),
            )
            and is_string_browse_column(schema, column)
            and is_browse_scalar_column(schema, column)
        )
    ]
    if not candidates:
        return ()

    try:
        _pyarrow, parquet = require_pyarrow()
        import pyarrow.compute as compute

        categorical_table = parquet.read_table(str(parquet_path), columns=candidates)
    except _table_schema_errors():
        return ()

    selected: list[str] = []
    for column in candidates:
        if arrow_array_has_low_cardinality(
            categorical_table[column],
            compute,
            max_unique_values=max_unique_values,
            error_types=_table_schema_errors(),
        ):
            selected.append(column)
    return tuple(selected)


def parquet_browse_signature_seed(parquet_path: Path) -> str:
    try:
        stat = parquet_path.stat()
    except OSError:
        return str(parquet_path)
    return f"{parquet_path.resolve()}:{stat.st_mtime_ns}:{stat.st_size}"


def inspect_table_dimensions(table: PyArrowTable, *, count_missing: bool = True) -> TableDimensionState:
    width_name = find_dimension_column(table, "width")
    height_name = find_dimension_column(table, "height")
    if not count_missing:
        missing_count = 0 if width_name and height_name else table.num_rows
    else:
        missing_count = count_missing_dimensions(table, width_name, height_name)
    return TableDimensionState(
        width_name=width_name,
        height_name=height_name,
        missing_count=missing_count,
    )


def resolve_dimension_probe_policy(
    *,
    cache_dimensions: bool,
    skip_dimension_probe: bool,
    missing_dimensions: int,
) -> TableDimensionProbePolicy:
    if not (cache_dimensions and skip_dimension_probe and missing_dimensions > 0):
        return TableDimensionProbePolicy(skip_dimension_probe=skip_dimension_probe)

    return TableDimensionProbePolicy(
        skip_dimension_probe=False,
        notices=(
            TableLaunchNotice(
                kind="dimension_cache_requires_probe",
                message="[lenslet] dimension caching enabled; missing width/height -> probing dimensions.",
            ),
        ),
    )


def resolve_launch_root(
    *,
    parquet_path: Path,
    table: PyArrowTable,
    source_column: str | None,
    base_dir: str | None,
    auto_detect_root: bool,
) -> TableRootResolution:
    effective_root = resolve_table_root(
        parquet_path=parquet_path,
        table=table,
        source_column=source_column,
        base_dir=base_dir,
        auto_detect_root=auto_detect_root,
    )
    default_root = os.path.abspath(str(parquet_path.parent))
    notices: tuple[TableLaunchNotice, ...] = ()
    if auto_detect_root and base_dir is None and effective_root and effective_root != default_root:
        notices = (
            TableLaunchNotice(
                kind="auto_detected_root",
                message=f"[lenslet] Auto-detected local source root: {effective_root}",
            ),
        )
    return TableRootResolution(
        effective_root=effective_root,
        default_root=default_root,
        notices=notices,
    )


def cache_missing_dimensions(
    *,
    cache_dimensions: bool,
    parquet_path: Path,
    table: PyArrowTable,
    table_is_projected: bool,
    dimensions: TableDimensionState,
    row_dims: list[tuple[int, int] | None],
) -> tuple[TableLaunchNotice, ...]:
    if not cache_dimensions:
        return ()
    if dimensions.missing_count <= 0 and dimensions.width_name and dimensions.height_name:
        return ()

    updated = write_missing_dimensions(
        parquet_path=parquet_path,
        table=load_parquet_table(str(parquet_path)) if table_is_projected else table,
        width_name=dimensions.width_name,
        height_name=dimensions.height_name,
        row_dims=row_dims,
    )
    if not updated:
        return ()
    return (
        TableLaunchNotice(
            kind="dimensions_cached",
            message=f"[lenslet] Cached width/height into {parquet_path}",
        ),
    )


def cache_workspace_dimensions(
    *,
    dimension_cache_dir: Path | None,
    dimension_cache_identity: dict[str, Any] | None,
    rows: list[tuple[int, Any]],
) -> tuple[TableLaunchNotice, ...]:
    cached = write_dimension_cache(
        dimension_cache_dir,
        dimension_cache_identity,
        (
            TableDimensionCacheRow(row_idx=row_idx, dimensions=dimensions)
            for row_idx, dimensions in rows
        ),
    )
    if cached <= 0:
        return ()
    return (
        TableLaunchNotice(
            kind="workspace_dimensions_cached",
            message=f"[lenslet] Cached width/height for {cached} row(s) in the workspace dimension cache.",
        ),
    )


def resolve_table_root(
    *,
    parquet_path: Path,
    table: PyArrowTable,
    source_column: str | None,
    base_dir: str | None,
    auto_detect_root: bool,
) -> str | None:
    if base_dir:
        return os.path.abspath(base_dir)

    default_root = os.path.abspath(str(parquet_path.parent))
    if not auto_detect_root:
        return default_root

    detected_source = source_column or detect_source_column(str(parquet_path), default_root)
    if not detected_source:
        return default_root

    absolute_local_sources, has_relative_local_sources = local_source_layout(table, detected_source)
    if not absolute_local_sources or has_relative_local_sources:
        return default_root

    if all(path_is_within_root(source, default_root) for source in absolute_local_sources):
        return default_root

    try:
        common_root = os.path.commonpath(absolute_local_sources)
    except ValueError:
        return default_root

    common_root = os.path.abspath(common_root)
    if not common_root or common_root == os.path.sep:
        return default_root
    if not is_safe_auto_root(common_root):
        return default_root
    return common_root


def find_dimension_column(table: PyArrowTable, target: str) -> str | None:
    target_lower = target.lower()
    for name in table.schema.names:
        if name.lower() == target_lower:
            return name
    return None


def count_missing_dimensions(table: PyArrowTable, width_name: str | None, height_name: str | None) -> int:
    if width_name is None or height_name is None:
        return table.num_rows
    width = table[width_name].to_pylist()
    height = table[height_name].to_pylist()
    missing = 0
    for w, h in zip(width, height):
        if not valid_dimension(w) or not valid_dimension(h):
            missing += 1
    return missing


def valid_dimension(value: object) -> bool:
    try:
        return value is not None and int(value) > 0
    except _DIMENSION_VALUE_ERRORS:
        return False


def merged_dimension_value(existing_value: object, dims: tuple[int, int] | None, index: int) -> tuple[object, bool]:
    if valid_dimension(existing_value):
        return existing_value, False
    if dims and dims[index] > 0:
        return dims[index], True
    return existing_value, False


def existing_dimension_values(table: PyArrowTable, column_name: str | None) -> list[Any]:
    return table[column_name].to_pylist() if column_name else [None] * table.num_rows


def merged_dimension_arrays(
    table: PyArrowTable,
    width_name: str | None,
    height_name: str | None,
    row_dims: list[tuple[int, int] | None],
) -> tuple[list[object], list[object], bool]:
    widths: list[object] = []
    heights: list[object] = []
    existing_width = existing_dimension_values(table, width_name)
    existing_height = existing_dimension_values(table, height_name)

    changed = False
    for idx in range(table.num_rows):
        dims = row_dims[idx] if idx < len(row_dims) else None
        w_existing = existing_width[idx] if idx < len(existing_width) else None
        h_existing = existing_height[idx] if idx < len(existing_height) else None
        w_final, width_changed = merged_dimension_value(w_existing, dims, 0)
        h_final, height_changed = merged_dimension_value(h_existing, dims, 1)
        changed = changed or width_changed or height_changed
        widths.append(w_final)
        heights.append(h_final)
    return widths, heights, changed


def upsert_dimension_column(
    table: PyArrowTable,
    column_name: str | None,
    fallback_name: str,
    values: object,
) -> tuple[PyArrowTable, str]:
    resolved_name = column_name or fallback_name
    if column_name is None:
        return table.append_column(resolved_name, values), resolved_name
    idx = table.schema.get_field_index(column_name)
    return table.set_column(idx, resolved_name, values), resolved_name


def write_missing_dimensions(
    parquet_path: Path,
    table: PyArrowTable,
    width_name: str | None,
    height_name: str | None,
    row_dims: list[tuple[int, int] | None],
) -> bool:
    pyarrow, parquet = require_pyarrow()
    widths, heights, changed = merged_dimension_arrays(table, width_name, height_name, row_dims)

    if not changed and width_name and height_name:
        return False

    width_arr = pyarrow.array(widths, type=pyarrow.int64())
    height_arr = pyarrow.array(heights, type=pyarrow.int64())

    table_out = table
    table_out, width_name = upsert_dimension_column(table_out, width_name, "width", width_arr)
    table_out, height_name = upsert_dimension_column(table_out, height_name, "height", height_arr)

    parquet.write_table(table_out, str(parquet_path))
    return True


class ParquetRowFieldProvider:
    def __init__(self, parquet_path: Path, columns: tuple[str, ...]) -> None:
        _pyarrow, parquet = require_pyarrow()
        self._parquet_path = parquet_path
        self._parquet_file = parquet.ParquetFile(str(parquet_path))
        self._columns = list(columns)
        self._row_group_starts = self._build_row_group_starts()
        self._cached_row_group: int | None = None
        self._cached_columns: dict[str, list[Any]] = {}
        self._failed_row_groups: set[int] = set()

    def _build_row_group_starts(self) -> list[int]:
        starts: list[int] = []
        total = 0
        metadata = self._parquet_file.metadata
        if metadata is None:
            return [0]
        for idx in range(metadata.num_row_groups):
            starts.append(total)
            total += metadata.row_group(idx).num_rows
        return starts or [0]

    def __call__(self, row_idx: int) -> dict[str, Any]:
        row_group = max(0, bisect_right(self._row_group_starts, row_idx) - 1)
        local_idx = row_idx - self._row_group_starts[row_group]
        if row_group in self._failed_row_groups:
            return {}
        if self._cached_row_group != row_group:
            try:
                table = self._parquet_file.read_row_group(row_group, columns=self._columns)
                cached_columns = table.to_pydict()
            except _parquet_row_field_read_errors() as exc:
                self._failed_row_groups.add(row_group)
                self._cached_row_group = None
                self._cached_columns = {}
                logger.warning(
                    "table field enrichment skipped for parquet row group %s in %s: %s",
                    row_group,
                    self._parquet_path,
                    exc,
                )
                return {}
            self._cached_columns = cached_columns
            self._cached_row_group = row_group
        return {
            column: values[local_idx]
            for column, values in self._cached_columns.items()
            if local_idx < len(values)
        }


class ArrowTableRowFieldProvider:
    def __init__(self, table: PyArrowTable) -> None:
        self._columns = {
            column: table[column]
            for column in table.schema.names
        }
        self._row_count = table.num_rows

    def __call__(self, row_idx: int) -> dict[str, Any]:
        if row_idx < 0 or row_idx >= self._row_count:
            return {}
        return {
            column: values[row_idx].as_py()
            for column, values in self._columns.items()
        }
