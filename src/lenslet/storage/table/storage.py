from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import gc
import hashlib
import os
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from io import BytesIO
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import urlparse

if TYPE_CHECKING:
    import pyarrow as pa

from ...media_errors import MediaDecodeError, MediaReadError
from ..base import join_storage_path
from ..progress import ProgressBar
from ..sidecar_state import default_sidecar_state
from ..source.backed import SourceBackedConfig, SourceBackedServices, SourceBackedStorageBase
from ..source.state import SourceBackedIndexState, SourceRowIndexState
from .display import (
    is_internal_metric_key,
    normalize_display_value,
    normalize_metrics_display_value,
)
from .index import (
    build_index_columns,
    extract_row_display_fields,
    is_metric_column_name,
)
from .index_types import (
    TableIndexData,
    TableIndexInput,
    TableIndexPolicy,
    TableSourceResolver,
)
from .input import (
    TableInput,
    TableRow,
    TableRows,
    is_table_input,
    table_input_columns,
    table_input_length,
    table_to_columns,
    validate_table_input,
)
from ..image_media import (
    ImageMime,
    make_webp_thumbnail,
    read_dimensions_from_bytes,
)
from ..source.paths import (
    canonical_sidecar_key,
    compute_local_prefix,
    compute_s3_prefixes,
    derive_http_logical_path,
    extract_name,
    is_http_url,
    is_s3_uri,
    is_supported_image,
    normalize_item_path,
    normalize_path,
    resolve_local_source,
    resolve_local_source_lexical,
)
from .schema import (
    coerce_float,
    iter_sample,
    resolve_named_column,
    resolve_path_column,
    resolve_source_column,
)
from .pyarrow_runtime import require_pyarrow_parquet
from .row_store import (
    TableRowRemoteDimensionTask,
    TableRowStore,
    TableRowStoreBuildResult,
    TableRowViewItem,
    build_table_row_store,
)
from ..search_text import normalize_search_path


TABLE_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
GC_DISABLE_ROW_THRESHOLD = 100_000


MetricProvider = Callable[[int], dict[str, float]]


@contextmanager
def _bulk_table_gc_pause(row_count: int):
    if row_count < GC_DISABLE_ROW_THRESHOLD or not gc.isenabled():
        yield
        return
    gc.disable()
    try:
        yield
    finally:
        gc.enable()


@dataclass(init=False, slots=True)
class TableBrowseItem:
    """In-memory cached browse facts for an image loaded from a table."""
    path: str
    name: str
    mime: ImageMime
    width: int
    height: int
    size: int
    mtime: float
    url: str | None = None
    source: str | None = None
    metric_labels: dict[str, str] = field(default_factory=dict)
    row_idx: int = -1
    _metrics: dict[str, float] | None = field(default=None, repr=False)
    _metrics_provider: MetricProvider | None = field(default=None, repr=False)

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
        url: str | None = None,
        source: str | None = None,
        metrics: dict[str, float] | None = None,
        metric_labels: dict[str, str] | None = None,
        row_idx: int = -1,
        metrics_provider: MetricProvider | None = None,
    ) -> None:
        self.path = path
        self.name = name
        self.mime = mime
        self.width = width
        self.height = height
        self.size = size
        self.mtime = mtime
        self.url = url
        self.source = source
        self.metric_labels = metric_labels or {}
        self.row_idx = row_idx
        self._metrics = metrics
        self._metrics_provider = metrics_provider

    @property
    def metrics(self) -> dict[str, float]:
        metrics = self._metrics
        if metrics is None:
            if self._metrics_provider is None or self.row_idx < 0:
                metrics = {}
            else:
                metrics = self._metrics_provider(self.row_idx)
            self._metrics = metrics
        return metrics

    @metrics.setter
    def metrics(self, value: dict[str, float]) -> None:
        self._metrics = value

    @classmethod
    def from_fast_row(
        cls,
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
        metrics_provider: MetricProvider,
    ) -> "TableBrowseItem":
        item = cls.__new__(cls)
        item.path = path
        item.name = name
        item.mime = mime
        item.width = width
        item.height = height
        item.size = size
        item.mtime = mtime
        item.url = url
        item.source = source
        item.metric_labels = {}
        item.row_idx = row_idx
        item._metrics = None
        item._metrics_provider = metrics_provider
        return item


@dataclass(slots=True)
class TableBrowseIndex:
    """In-memory cached folder index."""
    path: str
    generated_at: str
    dirs: list[str] = field(default_factory=list)
    total_items: int = 0
    _item_rows: tuple[int, ...] = ()
    _item_loader: Callable[[tuple[int, ...]], list[TableRowViewItem]] | None = field(default=None, repr=False)
    _items: list[TableRowViewItem] | None = field(default=None, repr=False)

    @property
    def items(self) -> list[TableRowViewItem]:
        items = self._items
        if items is None:
            if self._item_loader is None:
                items = []
            else:
                items = self._item_loader(self._item_rows)
            self._items = items
        return items


@dataclass(frozen=True, slots=True)
class TableStorageOptions:
    root: str | None = None
    thumb_size: int = 256
    thumb_quality: int = 70
    source_column: str | None = None
    path_column: str | None = None
    sample_size: int = 50
    loadable_threshold: float = 0.7
    include_source_in_search: bool = True
    skip_dimension_probe: bool = False
    allow_local: bool = True
    skip_local_realpath_validation: bool = False
    row_field_provider: Callable[[int], dict[str, Any]] | None = None
    table_field_columns: tuple[str, ...] = ()
    browse_signature_seed: str = ""


@dataclass(frozen=True, slots=True)
class _RowRemoteProbeResult:
    row_idx: int
    path: str
    dims: tuple[int, int] | None
    total_size: int | None


def _is_supported_table_image(name: str) -> bool:
    return is_supported_image(name, TABLE_IMAGE_EXTS)


def _sample_source_kind(values: list[Any], *, sample_size: int = 1024) -> str | None:
    kind: str | None = None
    checked = 0
    for raw in values:
        if raw is None:
            continue
        if isinstance(raw, os.PathLike):
            raw = os.fspath(raw)
        if not isinstance(raw, str):
            continue
        source = raw.strip()
        if not source:
            continue
        current = "s3" if is_s3_uri(source) else "http" if is_http_url(source) else "local"
        if kind is None:
            kind = current
        elif kind != current:
            return "mixed"
        checked += 1
        if checked >= sample_size:
            return kind
    return kind


class TableStorage(SourceBackedStorageBase[TableRowViewItem]):
    """
    In-memory storage backed by a single table (DataFrame or Parquet).
    Supports local paths, S3 URIs, and HTTP/HTTPS URLs as sources.
    """

    IMAGE_EXTS = TABLE_IMAGE_EXTS
    EXTENSIONLESS_IMAGE_SOURCE_COLUMNS = frozenset({"s3key"})
    REMOTE_HEADER_BYTES = 65536
    REMOTE_DIM_WORKERS = 16  # baseline concurrency for remote header probing
    REMOTE_DIM_WORKERS_MAX = 128  # avoid unbounded thread creation on huge hosts
    RECURSIVE_ITEMS_HARD_LIMIT = 10_000
    BROWSE_SIGNATURE_SAMPLE_SIZE = 128

    LOGICAL_PATH_COLUMNS = (
        "path",
        "logical_path",
        "rel_path",
        "relative_path",
        "display_path",
    )

    NAME_COLUMNS = (
        "name",
        "filename",
        "file_name",
    )

    MIME_COLUMNS = (
        "mime",
        "mime_type",
    )

    WIDTH_COLUMNS = (
        "width",
        "w",
    )

    HEIGHT_COLUMNS = (
        "height",
        "h",
    )

    SIZE_COLUMNS = (
        "size",
        "bytes",
    )

    MTIME_COLUMNS = (
        "mtime",
        "modified",
        "modified_at",
    )

    RESERVED_COLUMNS = {
        "image_id",
        "source",
        "src",
        "url",
        "s3",
        "s3_uri",
        "s3uri",
        "path",
        "logical_path",
        "rel_path",
        "relative_path",
        "display_path",
        "local_path",
        "image_path",
        "name",
        "filename",
        "file_name",
        "mime",
        "mime_type",
        "width",
        "w",
        "height",
        "h",
        "size",
        "bytes",
        "mtime",
        "modified",
        "modified_at",
        "star",
        "tags",
        "notes",
        "comment",
        "comments",
        "dataset",
        "collection",
        "metrics",
    }

    def __init__(
        self,
        table: TableInput,
        *,
        options: TableStorageOptions | None = None,
    ):
        options = options or TableStorageOptions()
        self.root = os.path.abspath(options.root) if options.root else None
        self._root_real = os.path.realpath(self.root) if self.root else None
        self._allow_local = options.allow_local
        self._skip_local_realpath_validation = bool(options.skip_local_realpath_validation)
        self._initialize_source_backed_state(
            config=SourceBackedConfig(
                thumb_size=options.thumb_size,
                thumb_quality=options.thumb_quality,
                include_source_in_search=options.include_source_in_search,
                remote_header_bytes=self.REMOTE_HEADER_BYTES,
                remote_dim_workers=self.REMOTE_DIM_WORKERS,
                remote_dim_workers_max=self.REMOTE_DIM_WORKERS_MAX,
            ),
            services=SourceBackedServices(
                normalize_item_path=normalize_item_path,
                canonical_sidecar_key=canonical_sidecar_key,
                is_s3_uri=is_s3_uri,
                is_http_url=is_http_url,
                resolve_local_source=self._resolve_local_source,
                read_dimensions_from_bytes=read_dimensions_from_bytes,
                progress=self._progress,
            ),
        )
        self.sample_size = options.sample_size
        self.loadable_threshold = options.loadable_threshold
        self._skip_dimension_probe = options.skip_dimension_probe
        self._row_field_provider = options.row_field_provider
        self._table_field_columns = tuple(options.table_field_columns)
        self._browse_signature_seed = options.browse_signature_seed
        self._progress_bar = ProgressBar()

        self._indexes: dict[str, TableBrowseIndex] = {}
        self._row_store: TableRowStore | None = None
        self._generated_at = datetime.now(timezone.utc).isoformat()
        self._search_paths_lower: list[str] | None = None
        self._search_names_lower: list[str] | None = None
        self._search_sources_lower: list[str] | None = None
        self._path_column_aliases_source = False

        validated_table = validate_table_input(table)
        initial_columns = table_input_columns(validated_table)
        python_columns = self._startup_python_columns(validated_table, initial_columns, options)
        columns, data, row_count = table_to_columns(validated_table, python_columns=python_columns)
        if row_count == 0:
            raise ValueError("table is empty")

        self._columns = columns
        self._data = data
        self._row_count = row_count
        self._source_column_was_explicit = options.source_column is not None

        self._source_column = resolve_source_column(
            columns,
            data,
            options.source_column,
            loadable_threshold=self.loadable_threshold,
            sample_size=self.sample_size,
            allow_local=self._allow_local,
            is_loadable_value=self._is_loadable_value,
        )
        source_values = data.get(self._source_column, [])
        self._source_kind = _sample_source_kind(source_values)
        if self._source_kind == "http":
            self._s3_prefixes, self._s3_use_bucket = {}, False
            self._local_prefix = None
        elif self._source_kind == "s3":
            self._s3_prefixes, self._s3_use_bucket = compute_s3_prefixes(source_values)
            self._local_prefix = None
        else:
            self._s3_prefixes, self._s3_use_bucket = compute_s3_prefixes(source_values)
            self._local_prefix = compute_local_prefix(source_values) if self._allow_local else None
        self._path_column = resolve_path_column(
            columns,
            options.path_column,
            logical_path_columns=self.LOGICAL_PATH_COLUMNS,
        )
        self._name_column = resolve_named_column(columns, self.NAME_COLUMNS)
        self._mime_column = resolve_named_column(columns, self.MIME_COLUMNS)
        self._width_column = resolve_named_column(columns, self.WIDTH_COLUMNS)
        self._height_column = resolve_named_column(columns, self.HEIGHT_COLUMNS)
        self._size_column = resolve_named_column(columns, self.SIZE_COLUMNS)
        self._mtime_column = resolve_named_column(columns, self.MTIME_COLUMNS)
        self._metrics_column = None
        for col in columns:
            if col.lower() == "metrics":
                self._metrics_column = col
                break

        self._extensionless_source_trust_scope = self._selected_extensionless_source_trust_scope()

        self._index_context = self._build_index_context()
        self._index_columns = build_index_columns(self._index_context)
        with _bulk_table_gc_pause(row_count):
            row_store_result = build_table_row_store(
                self._index_context,
                columns=self._index_columns,
            )
            self._apply_row_store_result(row_store_result)
        if row_store_result.remote_tasks:
            self._probe_row_remote_dimensions(row_store_result.remote_tasks)
        with _bulk_table_gc_pause(row_count):
            self._browse_signature = self._compute_browse_signature()

    def _startup_python_columns(
        self,
        table: TableInput,
        columns: list[str],
        options: TableStorageOptions,
    ) -> set[str] | None:
        if options.source_column is None:
            return None

        source_column = resolve_source_column(
            columns,
            {},
            options.source_column,
            loadable_threshold=self.loadable_threshold,
            sample_size=self.sample_size,
            allow_local=self._allow_local,
            is_loadable_value=self._is_loadable_value,
        )
        path_column = resolve_path_column(
            columns,
            options.path_column,
            logical_path_columns=self.LOGICAL_PATH_COLUMNS,
        )
        path_column_aliases_source = self._auto_path_column_aliases_source(
            table,
            source_column=source_column,
            path_column=path_column,
            path_column_was_explicit=options.path_column is not None,
        )
        self._path_column_aliases_source = path_column_aliases_source
        selected = {
            source_column,
            None if path_column_aliases_source else path_column,
            resolve_named_column(columns, self.NAME_COLUMNS),
            resolve_named_column(columns, self.MIME_COLUMNS),
            resolve_named_column(columns, self.WIDTH_COLUMNS),
            resolve_named_column(columns, self.HEIGHT_COLUMNS),
            resolve_named_column(columns, self.SIZE_COLUMNS),
            resolve_named_column(columns, self.MTIME_COLUMNS),
        }
        for column in columns:
            if column.lower() == "metrics":
                selected.add(column)
                break
        return {column for column in selected if column}

    @staticmethod
    def _sample_pyarrow_strings(table: TableInput, column: str, sample_size: int = 1024) -> list[str] | None:
        if not hasattr(table, "__getitem__"):
            return None
        try:
            values = table[column]  # type: ignore[index]
            if hasattr(values, "slice"):
                values = values.slice(0, sample_size)
            if not hasattr(values, "to_pylist"):
                return None
            sampled = values.to_pylist()
        except Exception:
            return None
        result: list[str] = []
        for raw in sampled:
            if raw is None:
                continue
            if isinstance(raw, os.PathLike):
                raw = os.fspath(raw)
            if not isinstance(raw, str):
                return None
            value = raw.strip()
            if value:
                result.append(value)
        return result

    def _auto_path_column_aliases_source(
        self,
        table: TableInput,
        *,
        source_column: str,
        path_column: str | None,
        path_column_was_explicit: bool,
    ) -> bool:
        if path_column is None or path_column_was_explicit or path_column == source_column:
            return False
        source_values = self._sample_pyarrow_strings(table, source_column)
        path_values = self._sample_pyarrow_strings(table, path_column)
        if not source_values or not path_values or len(source_values) != len(path_values):
            return False
        source_matches_path = True
        http_source_matches_path = True
        for source, path in zip(source_values, path_values):
            if source != path:
                source_matches_path = False
            if not is_http_url(source) or normalize_item_path(derive_http_logical_path(source)) != normalize_item_path(path):
                http_source_matches_path = False
            if not source_matches_path and not http_source_matches_path:
                return False
        return True

    def _build_index_context(self) -> TableIndexInput:
        index_path_column = None if self._path_column_aliases_source else self._path_column
        return TableIndexInput(
            table=TableIndexData(
                root=self.root,
                row_count=self._row_count,
                column_values=self._data,
                columns=self._columns,
                source_column=self._source_column,
                path_column=index_path_column,
                name_column=self._name_column,
                mime_column=self._mime_column,
                width_column=self._width_column,
                height_column=self._height_column,
                size_column=self._size_column,
                mtime_column=self._mtime_column,
                metrics_column=self._metrics_column,
                reserved_columns=self.RESERVED_COLUMNS,
                local_prefix=self._local_prefix,
                s3_prefixes=self._s3_prefixes,
                s3_use_bucket=self._s3_use_bucket,
                image_exts=self.IMAGE_EXTS,
                source_kind=self._source_kind,
                extensionless_source_all_trusted=self._extensionless_source_trust_scope == "*",
            ),
            policy=TableIndexPolicy(
                allow_local=self._allow_local,
                skip_dimension_probe=self._skip_dimension_probe,
                skip_local_realpath_validation=self._skip_local_realpath_validation,
            ),
            source_resolver=TableSourceResolver(
                guess_mime=self._guess_mime,
                allows_extensionless_source_image=self._allows_extensionless_source_image,
                resolve_local_source=self._resolve_local_source,
                resolve_local_source_lexical=self._resolve_local_source_lexical,
            ),
            progress=self._progress,
        )

    def _apply_row_store_result(self, result: TableRowStoreBuildResult) -> None:
        self._indexes = {}
        self._row_store = result.store
        self._bind_source_state(
            SourceBackedIndexState(
                items={},
                source_paths={},
                dimensions=result.store.dimensions,
            )
        )
        self._bind_row_index_state(
            SourceRowIndexState(
                row_dimensions=result.store.row_dimensions,
                path_to_row=result.store.path_to_row,
                row_to_path=result.store.row_to_path,
            )
        )
        self._report_row_store_skips(result)

    def _report_row_store_skips(self, result: TableRowStoreBuildResult) -> None:
        if result.skipped_local_disabled:
            print(f"[lenslet] Skipped {result.skipped_local_disabled} local path(s): local sources are disabled.")
        if result.skipped_local_outside_root:
            boundary = self.root or "(unset)"
            print(
                f"[lenslet] Skipped {result.skipped_local_outside_root} local path(s) outside "
                f"base_dir boundary: {boundary}"
            )
        if result.skipped_local_resolved_outside_root:
            boundary = self.root or "(unset)"
            print(
                f"[lenslet] Skipped {result.skipped_local_resolved_outside_root} local path(s) that are "
                f"inside base_dir but resolve outside it: {boundary}. "
                "This commonly means symlinks point outside the launched directory."
            )
        if result.skipped_local_missing:
            print(f"[lenslet] Skipped {result.skipped_local_missing} missing local path(s).")

    def _require_row_store(self) -> TableRowStore:
        if self._row_store is None:
            raise RuntimeError("table row store is not initialized")
        return self._row_store

    def _probe_row_remote_dimensions(self, tasks: list[TableRowRemoteDimensionTask]) -> None:
        total = len(tasks)
        if total == 0:
            return
        workers = self._effective_remote_workers(total)
        if workers <= 0:
            return
        done = 0
        last_print = 0.0
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(self._probe_row_remote_dimension, task) for task in tasks]
            for future in as_completed(futures):
                self._apply_row_remote_probe_result(future.result())
                done += 1
                now = time.monotonic()
                if now - last_print > 0.1 or done == total:
                    self._progress(done, total, "remote headers")
                    last_print = now

    def _probe_row_remote_dimension(self, task: TableRowRemoteDimensionTask) -> _RowRemoteProbeResult:
        source = task.source
        if is_s3_uri(source):
            try:
                source = self._get_presigned_url(source)
            except (ImportError, RuntimeError, ValueError):
                return _RowRemoteProbeResult(task.row_idx, task.path, None, None)
        dims, total_size = self._get_remote_header_info(source, task.name)
        return _RowRemoteProbeResult(task.row_idx, task.path, dims, total_size)

    def _apply_row_remote_probe_result(self, result: _RowRemoteProbeResult) -> None:
        row_store = self._require_row_store()
        if result.dims:
            row_store.update_dimensions(result.path, result.dims, size=result.total_size)
        elif result.total_size:
            row_store.update_size(result.path, result.total_size)

    def _metrics_for_row(self, row_idx: int) -> dict[str, float]:
        metrics: dict[str, float] = {}
        for column, values in self._index_columns.metric_columns:
            num = coerce_float(values[row_idx])
            if num is not None:
                metrics[column] = num
        if self._metrics_column is None:
            return metrics
        raw_metrics = self._index_columns.metrics_values[row_idx]
        if not isinstance(raw_metrics, dict):
            return metrics
        for raw_key, raw_value in raw_metrics.items():
            if is_internal_metric_key(raw_key):
                continue
            num = coerce_float(raw_value)
            if num is not None:
                metrics[str(raw_key)] = num
        return metrics

    @staticmethod
    def _signature_value(value: Any) -> Any:
        if hasattr(value, "as_py"):
            try:
                return value.as_py()
            except Exception:
                return value
        return value

    def _signature_metric_items(self, row_idx: int) -> list[tuple[str, float]]:
        metrics: list[tuple[str, float]] = []
        for column, values in self._index_columns.metric_columns:
            num = coerce_float(self._signature_value(values[row_idx]))
            if num is not None:
                metrics.append((column, num))
        if self._metrics_column is None:
            return metrics
        raw_metrics = self._signature_value(self._index_columns.metrics_values[row_idx])
        if not isinstance(raw_metrics, dict):
            return metrics
        for raw_key, raw_value in raw_metrics.items():
            if is_internal_metric_key(raw_key):
                continue
            num = coerce_float(self._signature_value(raw_value))
            if num is not None:
                metrics.append((str(raw_key), num))
        return sorted(metrics)

    def _compute_browse_signature(self) -> str:
        digest = hashlib.sha256()
        digest.update(b"table-browse-v3")
        digest.update(str(self.root or "").encode("utf-8"))
        digest.update(self._browse_signature_seed.encode("utf-8"))
        digest.update(str(self._row_count).encode("utf-8"))
        for column in self._columns:
            digest.update(repr(column).encode("utf-8"))
        for column in (
            self._source_column,
            self._path_column,
            self._name_column,
            self._mime_column,
            self._width_column,
            self._height_column,
            self._size_column,
            self._mtime_column,
            self._metrics_column,
        ):
            digest.update(repr(column).encode("utf-8"))
        sample_size = self.BROWSE_SIGNATURE_SAMPLE_SIZE
        row_store = self._require_row_store()
        sorted_paths = row_store.sorted_paths
        if len(sorted_paths) <= sample_size * 2:
            sampled_paths = sorted_paths
        else:
            sampled_paths = [
                *sorted_paths[:sample_size],
                *sorted_paths[-sample_size:],
            ]
        for path in sampled_paths:
            row_idx = row_store.row_index_for_path(path)
            if row_idx is None:
                continue
            (
                _path,
                name,
                mime,
                width,
                height,
                size,
                mtime,
                url,
                source,
            ) = row_store.item_fields_for_row(row_idx)
            for value in (
                path,
                name,
                mime,
                width,
                height,
                size,
                mtime,
                url,
                source,
            ):
                digest.update(repr(value).encode("utf-8"))
            for key, value in self._signature_metric_items(row_idx):
                digest.update(repr((key, value)).encode("utf-8"))
        return digest.hexdigest()

    def _is_loadable_value(self, value: str) -> bool:
        if is_s3_uri(value) or is_http_url(value):
            return True
        if not self._allow_local:
            return False
        if os.path.isabs(value):
            return os.path.exists(value)
        if self.root:
            try:
                resolved = self._resolve_local_source(value)
            except ValueError:
                return False
            return os.path.exists(resolved)
        return False

    def _selected_extensionless_source_trust_scope(self) -> str | None:
        if self._source_column.lower() in self.EXTENSIONLESS_IMAGE_SOURCE_COLUMNS:
            return "*"
        return self._probe_extensionless_source_scope()

    def _allows_extensionless_source_image(self, source: str) -> bool:
        scope = self._extensionless_source_trust_scope
        if scope == "*":
            return True
        return scope is not None and scope == self._extensionless_source_scope(source)

    def _probe_extensionless_source_scope(self) -> str | None:
        for source in iter_sample(self._data.get(self._source_column, [])):
            if _is_supported_table_image(extract_name(source)):
                continue
            if self._source_header_is_image(source):
                return self._extensionless_source_scope(source)
            return None
        return None

    def _extensionless_source_scope(self, source: str) -> str | None:
        if is_s3_uri(source):
            parsed = urlparse(source)
            return f"s3://{parsed.netloc.lower()}" if parsed.netloc else None
        if is_http_url(source):
            parsed = urlparse(source)
            if parsed.username or parsed.password or not parsed.hostname:
                return None
            if parsed.port not in {None, 80, 443}:
                return None
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            return f"{parsed.scheme}://{parsed.hostname.lower()}:{port}"
        return "local"

    def _source_header_is_image(self, source: str) -> bool:
        name = extract_name(source)
        if is_s3_uri(source):
            try:
                url = self._get_presigned_url(source)
            except (ImportError, RuntimeError, ValueError):
                return False
            dims, _total = self._get_safe_remote_header_info(url, name)
            return dims is not None

        if is_http_url(source):
            dims, _total = self._get_safe_remote_header_info(source, name)
            return dims is not None

        if not self._allow_local:
            return False
        try:
            if self._skip_local_realpath_validation:
                resolved = self._resolve_local_source_lexical(source)
            else:
                resolved = self._resolve_local_source(source)
        except ValueError:
            return False
        try:
            with open(resolved, "rb") as handle:
                header = handle.read(self.REMOTE_HEADER_BYTES)
        except OSError:
            return False
        return read_dimensions_from_bytes(header, None) is not None

    def _build_path_index(self) -> None:
        self._search_paths_lower = None
        self._search_names_lower = None
        self._search_sources_lower = None

    def _ensure_search_paths_lower(self) -> list[str]:
        search_paths = self._search_paths_lower
        if search_paths is None:
            search_paths = [path.lower() for path in self._require_row_store().sorted_paths]
            self._search_paths_lower = search_paths
        return search_paths

    def _ensure_search_names_lower(self) -> list[str]:
        search_names = self._search_names_lower
        if search_names is None:
            row_store = self._require_row_store()
            search_names = [
                row_store.name_for_row(row_idx).lower() for row_idx in row_store.sorted_rows
            ]
            self._search_names_lower = search_names
        return search_names

    def _ensure_search_sources_lower(self) -> list[str]:
        search_sources = self._search_sources_lower
        if search_sources is None:
            values: list[str] = []
            row_store = self._require_row_store()
            for row_idx in row_store.sorted_rows:
                source = row_store.source_for_row(row_idx)
                url = row_store.url_for_row(row_idx) or ""
                if url and url != source:
                    source = f"{source} {url}" if source else url
                values.append(source.lower())
            search_sources = values
            self._search_sources_lower = search_sources
        return search_sources

    def _sidecar_search_text(self, path: str) -> str:
        sidecar = self._sidecars.get(self._canonical_source_sidecar_key(path))
        if not sidecar:
            return ""
        tags = sidecar.get("tags", [])
        notes = sidecar.get("notes", "")
        parts: list[str] = []
        if isinstance(tags, list):
            parts.append(" ".join(str(tag) for tag in tags if tag is not None))
        if isinstance(notes, str):
            parts.append(notes)
        return " ".join(part for part in parts if part).lower()

    def _source_search_covered_by_path(self) -> bool:
        return self._source_kind == "http" and (
            self._path_column is None
            or self._path_column == self._source_column
            or self._path_column_aliases_source
        )

    def _name_search_covered_by_path(self) -> bool:
        return self._name_column is None and self._source_search_covered_by_path()

    @staticmethod
    def _path_search_needle(needle: str, *, source_search_covered_by_path: bool) -> str:
        if not source_search_covered_by_path or "://" not in needle:
            return needle
        return normalize_item_path(derive_http_logical_path(needle))

    def _materialize_row_item(self, row_idx: int) -> TableRowViewItem:
        return self._require_row_store().materialize_item(
            row_idx,
            metrics_provider=self._metrics_for_row,
        )

    def _lookup_item(self, norm: str) -> TableRowViewItem | None:
        row_idx = self._require_row_store().row_index_for_path(norm)
        if row_idx is None:
            return None
        return self._materialize_row_item(row_idx)

    def _materialize_rows(self, rows: tuple[int, ...]) -> list[TableRowViewItem]:
        return [self._materialize_row_item(row_idx) for row_idx in rows]

    def search(self, query: str = "", path: str = "/", limit: int = 100) -> list[TableRowViewItem]:
        if limit <= 0:
            return []
        row_store = self._require_row_store()
        start, end = row_store.scope_bounds(path)
        if start >= end:
            return []

        needle = (query or "").lower()
        if not needle:
            return self._materialize_rows(row_store.sorted_rows[start:min(end, start + limit)])

        results: list[TableRowViewItem] = []
        has_sidecars = bool(self._sidecars)
        search_paths = self._ensure_search_paths_lower()
        source_search_covered_by_path = self._source_search_covered_by_path()
        name_search_covered_by_path = self._name_search_covered_by_path()
        path_needle = self._path_search_needle(
            needle,
            source_search_covered_by_path=source_search_covered_by_path,
        )
        if not path_needle:
            return self._materialize_rows(row_store.sorted_rows[start:min(end, start + limit)])
        search_sources: list[str] | None = None
        search_names = None if name_search_covered_by_path else self._ensure_search_names_lower()
        for idx in range(start, end):
            row_idx = row_store.sorted_rows[idx]
            base_match = path_needle in search_paths[idx]
            if not base_match and search_names is not None:
                base_match = path_needle in search_names[idx]
            if (
                not base_match
                and self._include_source_in_search
                and not source_search_covered_by_path
            ):
                if search_sources is None:
                    search_sources = self._ensure_search_sources_lower()
                base_match = needle in search_sources[idx]
            if base_match:
                results.append(self._materialize_row_item(row_idx))
                if len(results) >= limit:
                    break
                continue
            if has_sidecars and needle in self._sidecar_search_text(
                row_store.path_for_row_index(row_idx) or ""
            ):
                results.append(self._materialize_row_item(row_idx))
                if len(results) >= limit:
                    break
        return results

    def _resolve_local_source(self, source: str) -> str:
        return resolve_local_source(
            source,
            root=self.root,
            root_real=self._root_real,
            allow_local=self._allow_local,
        )

    def _resolve_local_source_lexical(self, source: str) -> str:
        return resolve_local_source_lexical(
            source,
            root=self.root,
            allow_local=self._allow_local,
        )

    def exists(self, path: str) -> bool:
        return self._require_row_store().exists(path)

    def size(self, path: str) -> int:
        return self._require_row_store().size_for_path(path)

    def etag(self, path: str) -> str | None:
        row_store = self._require_row_store()
        row_idx = row_store.row_index_for_path(path)
        if row_idx is None:
            return None
        return f"{int(row_store.mtime_for_row(row_idx))}-{row_store.size_for_row(row_idx)}"

    def get_source_path(self, logical_path: str) -> str:
        return self._require_row_store().source_for_path(logical_path)

    def read_bytes(self, path: str) -> bytes:
        source = self.get_source_path(path)
        return self._media_reads.read_bytes(path, source)

    def get_or_build_thumbnail(self, path: str) -> bytes:
        norm = normalize_item_path(path)
        if norm in self._thumbnails:
            return self._thumbnails[norm]

        try:
            raw = self.read_bytes(norm)
        except FileNotFoundError:
            raise
        except MediaReadError:
            raise
        except Exception as exc:
            raise MediaReadError.from_exception(path, exc) from exc
        try:
            thumb, dims = make_webp_thumbnail(
                raw,
                thumb_size=self.thumb_size,
                thumb_quality=self.thumb_quality,
            )
        except Exception as exc:
            raise MediaDecodeError.from_exception(path, exc) from exc
        self._thumbnails[norm] = thumb
        if dims:
            self._require_row_store().update_dimensions(norm, dims, size=len(raw))
        return thumb

    def get_dimensions(self, path: str) -> tuple[int, int]:
        return self._require_row_store().dimensions_for_path(path)

    def load_dimensions(self, path: str) -> tuple[int, int]:
        norm = normalize_item_path(path)
        row_store = self._require_row_store()
        row_idx = row_store.row_index_for_path(norm)
        if row_idx is None:
            raise FileNotFoundError(path)
        width, height = row_store.dimensions_for_row(row_idx)
        if width > 0 and height > 0:
            row_store.update_dimensions(norm, (width, height))
            return width, height

        source = row_store.source_for_row(row_idx)
        name = row_store.name_for_row(row_idx)
        if self._source_is_s3_uri(source) or self._source_is_http_url(source):
            dims, total = self._media_reads.remote_header_info(source, name)
            if total:
                row_store.update_size(norm, total)
            if dims:
                row_store.update_dimensions(norm, dims, size=total)
                return dims

        try:
            raw = self.read_bytes(norm)
        except FileNotFoundError:
            raise
        except MediaReadError:
            raise
        except (OSError, ValueError) as exc:
            raise MediaReadError.from_exception(path, exc) from exc

        try:
            from PIL import Image

            with Image.open(BytesIO(raw)) as image:
                dims = image.size
        except (OSError, ValueError) as exc:
            raise MediaDecodeError.from_exception(path, exc) from exc

        row_store.update_dimensions(norm, dims, size=len(raw))
        return dims

    def _default_sidecar(self, norm: str):
        try:
            width, height = self._require_row_store().dimensions_for_path(norm)
        except FileNotFoundError:
            width, height = 0, 0
        return default_sidecar_state(width=width, height=height)

    def thumbnail_cache_key(self, path: str) -> str | None:
        try:
            source = self.get_source_path(path)
        except FileNotFoundError:
            return None
        parts = [source, str(self.thumb_size), str(self.thumb_quality)]
        if not (self._source_is_s3_uri(source) or self._source_is_http_url(source)):
            try:
                etag = self.etag(path)
            except Exception:
                etag = None
            if etag:
                parts.append(str(etag))
        return "|".join(parts)

    def resolve_local_file_path(self, path: str) -> str | None:
        try:
            source = self.get_source_path(path)
        except FileNotFoundError:
            return None
        if self._source_is_s3_uri(source) or self._source_is_http_url(source):
            return None
        try:
            return self._source_services.resolve_local_source(source)
        except ValueError:
            return None

    def load_index(self, path: str) -> TableBrowseIndex | None:
        norm = normalize_path(path)
        row_store = self._require_row_store()
        rows = row_store.direct_rows(norm)
        dirs = list(row_store.folder_dirs(norm))
        if not rows and not dirs and norm:
            return None
        return TableBrowseIndex(
            path="/" + norm if norm else "/",
            generated_at=self._generated_at,
            dirs=dirs,
            total_items=len(rows),
            _item_rows=rows,
            _item_loader=self._materialize_rows,
        )

    def load_recursive_index(self, path: str) -> TableBrowseIndex | None:
        return self.load_index(path)

    def validate_image_path(self, path: str) -> None:
        if not path:
            raise ValueError("empty path")
        if not self._require_row_store().exists(path):
            raise FileNotFoundError(path)

    def join(self, *parts: str) -> str:
        return join_storage_path(*parts)

    def recursive_items_hard_limit(self) -> int | None:
        return self.RECURSIVE_ITEMS_HARD_LIMIT

    def _scope_bounds(self, path: str) -> tuple[int, int]:
        return self._require_row_store().scope_bounds(path)

    def items_in_scope(self, path: str) -> list[TableRowViewItem]:
        return self._materialize_rows(self._require_row_store().rows_in_scope(path))

    def items_in_scope_window(self, path: str, offset: int, limit: int) -> list[TableRowViewItem]:
        return self._materialize_rows(self._require_row_store().rows_in_scope_window(path, offset, limit))

    def count_in_scope(self, path: str) -> int:
        return self._require_row_store().count_in_scope(path)

    def row_dimensions(self) -> list[tuple[int, int] | None]:
        return list(self._require_row_store().row_dimensions)

    def path_for_row_index(self, index: int) -> str | None:
        return self._require_row_store().path_for_row_index(index)

    def row_index_for_path(self, path: str) -> int | None:
        return self._require_row_store().row_index_for_path(path)

    def total_items(self) -> int:
        return self._require_row_store().total_rows()

    def sidecar_enrichment_for_path(self, path: str) -> dict[str, Any]:
        row_idx = self.row_index_for_path(path)
        if row_idx is None:
            return {}
        if self._row_field_provider is None:
            table_fields = extract_row_display_fields(self._index_context, row_idx)
        else:
            table_fields = self._extract_table_fields_from_row(
                self._row_field_provider(row_idx)
            )
        if not table_fields:
            return {}
        return {"table_fields": table_fields}

    def _duplicate_display_columns(self) -> set[str]:
        return {
            column
            for column in (
                self._source_column,
                self._path_column,
                self._name_column,
                self._mime_column,
                self._width_column,
                self._height_column,
                self._size_column,
                self._mtime_column,
            )
            if column
        }

    def _extract_table_fields_from_row(self, row_values: dict[str, Any]) -> dict[str, Any]:
        duplicate_columns = self._duplicate_display_columns()
        display_fields: dict[str, Any] = {}
        for column in self._table_field_columns:
            if column in duplicate_columns:
                continue
            if is_internal_metric_key(column):
                continue
            raw_value = row_values.get(column)
            if column == self._metrics_column:
                display_value = normalize_metrics_display_value(raw_value)
            else:
                if is_metric_column_name(column) and coerce_float(raw_value) is not None:
                    continue
                display_value = normalize_display_value(raw_value)
            if display_value is None:
                continue
            display_fields[column] = display_value
        return display_fields

    def row_index_map(self) -> dict[int, str]:
        return {
            row_idx: path
            for row_idx, path in enumerate(self._require_row_store().row_to_path)
            if path is not None
        }

    def s3_client_creations(self) -> int:
        return self._media_reads.s3_client_creations


def load_parquet_table(path: str, columns: list[str] | None = None) -> pa.Table:
    parquet = require_pyarrow_parquet()
    return parquet.read_table(path, columns=columns)


def load_parquet_schema(path: str) -> pa.Schema:
    parquet = require_pyarrow_parquet()
    return parquet.read_schema(path)
