from __future__ import annotations

import hashlib
import os
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    import pyarrow as pa

from ..base import join_storage_path
from ..progress import ProgressBar
from ..source.backed import SourceBackedConfig, SourceBackedServices, SourceBackedStorageBase
from ..source.state import SourceBackedIndexState, SourceRowIndexState
from ..index_assembly import IndexAssemblyResult
from .index import (
    build_table_indexes,
    extract_row_display_fields,
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
    table_input_length,
    table_to_columns,
    validate_table_input,
)
from ..image_media import (
    ImageMime,
    read_dimensions_from_bytes,
)
from ..source.paths import (
    canonical_sidecar_key,
    compute_local_prefix,
    compute_s3_prefixes,
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
    iter_sample,
    resolve_named_column,
    resolve_path_column,
    resolve_source_column,
)
from .pyarrow_runtime import require_pyarrow_parquet
from ..search_text import normalize_search_path


TABLE_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")


@dataclass
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
    metrics: dict[str, float] = field(default_factory=dict)
    metric_labels: dict[str, str] = field(default_factory=dict)


@dataclass
class TableBrowseIndex:
    """In-memory cached folder index."""
    path: str
    generated_at: str
    items: list[TableBrowseItem] = field(default_factory=list)
    dirs: list[str] = field(default_factory=list)


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


def _is_supported_table_image(name: str) -> bool:
    return is_supported_image(name, TABLE_IMAGE_EXTS)


class TableStorage(SourceBackedStorageBase[TableBrowseItem]):
    """
    In-memory storage backed by a single table (DataFrame or Parquet).
    Supports local paths, S3 URIs, and HTTP/HTTPS URLs as sources.
    """

    IMAGE_EXTS = TABLE_IMAGE_EXTS
    EXTENSIONLESS_IMAGE_SOURCE_COLUMNS = frozenset({"s3key"})
    REMOTE_HEADER_BYTES = 65536
    REMOTE_DIM_WORKERS = 16  # baseline concurrency for remote header probing
    REMOTE_DIM_WORKERS_MAX = 128  # avoid unbounded thread creation on huge hosts

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
        self._progress_bar = ProgressBar()

        self._indexes: dict[str, TableBrowseIndex] = {}
        self._sorted_paths: list[str] = []
        self._sorted_items: list[TableBrowseItem] = []

        columns, data, row_count = table_to_columns(validate_table_input(table))
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
        index_result = build_table_indexes(
            self._index_context,
            item_factory=TableBrowseItem,
            index_factory=TableBrowseIndex,
        )
        self._apply_index_result(index_result)
        if index_result.remote_tasks:
            self._probe_remote_dimensions(index_result.remote_tasks)
        self._build_path_index()
        self._browse_signature = self._compute_browse_signature()

    def _build_index_context(self) -> TableIndexInput:
        return TableIndexInput(
            table=TableIndexData(
                root=self.root,
                row_count=self._row_count,
                column_values=self._data,
                columns=self._columns,
                source_column=self._source_column,
                path_column=self._path_column,
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

    def _apply_index_result(self, result: IndexAssemblyResult) -> None:
        self._indexes = result.indexes
        self._bind_source_state(
            SourceBackedIndexState(
                items=result.items,
                source_paths=result.source_paths,
                dimensions=result.dimensions,
            )
        )
        self._bind_row_index_state(
            SourceRowIndexState(
                row_dimensions=result.row_dimensions,
                path_to_row=result.path_to_row,
                row_to_path=result.row_to_path,
            )
        )

    def _compute_browse_signature(self) -> str:
        digest = hashlib.sha256()
        digest.update(str(self.root or "").encode("utf-8"))
        digest.update(str(self._row_count).encode("utf-8"))
        for path in self._items.keys():
            digest.update(path.encode("utf-8"))
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
        paths = sorted(self._items.keys())
        self._sorted_paths = paths
        self._sorted_items = [self._items[path] for path in paths]

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

    def load_index(self, path: str) -> TableBrowseIndex | None:
        norm = normalize_path(path)
        if norm in self._indexes:
            return self._indexes[norm]
        return None

    def load_recursive_index(self, path: str) -> TableBrowseIndex | None:
        return self.load_index(path)

    def validate_image_path(self, path: str) -> None:
        if not path:
            raise ValueError("empty path")
        norm = normalize_item_path(path)
        if norm not in self._items:
            raise FileNotFoundError(path)

    def join(self, *parts: str) -> str:
        return join_storage_path(*parts)

    def recursive_items_hard_limit(self) -> int | None:
        return None

    def items_in_scope(self, path: str) -> list[TableBrowseItem]:
        scope_norm = normalize_search_path(path)
        if not scope_norm:
            return list(self._sorted_items)
        prefix = f"{scope_norm}/"
        start = bisect_left(self._sorted_paths, prefix)
        end = bisect_right(self._sorted_paths, prefix + "\uffff")
        return list(self._sorted_items[start:end])

    def count_in_scope(self, path: str) -> int:
        scope_norm = normalize_search_path(path)
        if not scope_norm:
            return len(self._sorted_items)
        prefix = f"{scope_norm}/"
        start = bisect_left(self._sorted_paths, prefix)
        end = bisect_right(self._sorted_paths, prefix + "\uffff")
        return max(0, end - start)

    def row_dimensions(self) -> list[tuple[int, int] | None]:
        return list(self._row_dimensions)

    def path_for_row_index(self, index: int) -> str | None:
        return self._row_to_path.get(index)

    def sidecar_enrichment_for_path(self, path: str) -> dict[str, Any]:
        row_idx = self.row_index_for_path(path)
        if row_idx is None:
            return {}
        table_fields = extract_row_display_fields(self._index_context, row_idx)
        if not table_fields:
            return {}
        return {"table_fields": table_fields}

    def row_index_map(self) -> dict[int, str]:
        return dict(self._row_to_path)

    def s3_client_creations(self) -> int:
        return self._media_reads.s3_client_creations


def load_parquet_table(path: str, columns: list[str] | None = None) -> pa.Table:
    parquet = require_pyarrow_parquet()
    return parquet.read_table(path, columns=columns)


def load_parquet_schema(path: str) -> pa.Schema:
    parquet = require_pyarrow_parquet()
    return parquet.read_schema(path)
