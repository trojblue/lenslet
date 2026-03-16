from __future__ import annotations

import hashlib
import os
from bisect import bisect_left, bisect_right
from threading import Lock
from dataclasses import dataclass, field
from typing import Any

from .base import join_storage_path
from .progress import ProgressBar
from .source_backed import SourceBackedStorageMixin
from .table_index import (
    build_table_indexes,
    extract_row_display_fields,
)
from .table_media import (
    read_dimensions_fast,
    read_dimensions_from_bytes,
)
from .table_paths import (
    canonical_meta_key,
    compute_local_prefix,
    compute_s3_prefixes,
    dedupe_path,
    derive_logical_path,
    extract_name,
    is_http_url,
    is_s3_uri,
    is_supported_image,
    normalize_item_path,
    normalize_path,
    resolve_local_source,
    resolve_local_source_lexical,
)
from .table_schema import (
    coerce_float,
    coerce_int,
    coerce_timestamp,
    resolve_named_column,
    resolve_path_column,
    resolve_source_column,
)
from .table_probe import probe_remote_dimensions
from .search_text import normalize_search_path

# S0/T1 seam anchors (see docs/dev_notes/20260211_s0_t1_seam_map.md):
# - T9 schema/path extraction: _resolve_source_column/_compute_s3_prefixes/_compute_local_prefix.
# - T10 index pipeline extraction: _build_indexes + metric extraction helpers.
# - T11 probe/media extraction: _probe_remote_dimensions/_read_dimensions_from_bytes/_read_dimensions_fast.
# - T12 facade compatibility: keep TableStorage public methods + load_parquet_table/load_parquet_schema.


@dataclass
class TableBrowseItem:
    """In-memory cached metadata for an image loaded from a table."""
    path: str
    name: str
    mime: str
    width: int
    height: int
    size: int
    mtime: float
    url: str | None = None
    source: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class TableBrowseIndex:
    """In-memory cached folder index."""
    path: str
    generated_at: str
    items: list[TableBrowseItem] = field(default_factory=list)
    dirs: list[str] = field(default_factory=list)


def _table_to_columns(table: Any) -> tuple[list[str], dict[str, list[Any]], int]:
    if hasattr(table, "to_pydict"):
        data = table.to_pydict()
        columns = list(getattr(table, "schema", None).names if hasattr(table, "schema") else data.keys())
    elif hasattr(table, "columns") and hasattr(table, "to_dict"):
        columns = list(table.columns)
        data = {col: table[col].tolist() for col in columns}
    elif isinstance(table, list):
        if not table:
            return [], {}, 0
        if not all(isinstance(row, dict) for row in table):
            raise ValueError("table list must contain dict rows")
        columns = list(table[0].keys())
        for row in table[1:]:
            for key in row.keys():
                if key not in columns:
                    columns.append(key)
        data = {col: [] for col in columns}
        for row in table:
            for col in columns:
                data[col].append(row.get(col))
    else:
        raise TypeError("table must be a pandas DataFrame, pyarrow.Table, or list of dicts")

    row_count = len(data.get(columns[0], [])) if columns else 0
    return columns, data, row_count


class TableStorage(SourceBackedStorageMixin[TableBrowseItem]):
    """
    In-memory storage backed by a single table (DataFrame or Parquet).
    Supports local paths, S3 URIs, and HTTP/HTTPS URLs as sources.
    """

    IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
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
    _is_s3_uri = staticmethod(is_s3_uri)
    _is_http_url = staticmethod(is_http_url)
    _extract_name = staticmethod(extract_name)
    _normalize_path = staticmethod(normalize_path)
    _normalize_item_path = staticmethod(normalize_item_path)
    _canonical_meta_key = staticmethod(canonical_meta_key)
    _dedupe_path = staticmethod(dedupe_path)
    _coerce_float = staticmethod(coerce_float)
    _coerce_int = staticmethod(coerce_int)
    _coerce_timestamp = staticmethod(coerce_timestamp)
    _read_dimensions_from_bytes = staticmethod(read_dimensions_from_bytes)
    _read_dimensions_fast = staticmethod(read_dimensions_fast)
    _probe_remote_dimensions = probe_remote_dimensions

    def __init__(
        self,
        table: Any,
        root: str | None = None,
        thumb_size: int = 256,
        thumb_quality: int = 70,
        source_column: str | None = None,
        path_column: str | None = None,
        sample_size: int = 50,
        loadable_threshold: float = 0.7,
        include_source_in_search: bool = True,
        skip_indexing: bool = False,
        allow_local: bool = True,
        skip_local_realpath_validation: bool = False,
    ):
        self.root = os.path.abspath(root) if root else None
        self._root_real = os.path.realpath(self.root) if self.root else None
        self._allow_local = allow_local
        self._skip_local_realpath_validation = bool(skip_local_realpath_validation)
        self.thumb_size = thumb_size
        self.thumb_quality = thumb_quality
        self.sample_size = sample_size
        self.loadable_threshold = loadable_threshold
        self._include_source_in_search = include_source_in_search
        self._skip_indexing = skip_indexing
        self._progress_bar = ProgressBar()

        self._indexes: dict[str, TableBrowseIndex] = {}
        self._items: dict[str, TableBrowseItem] = {}
        self._thumbnails: dict[str, bytes] = {}
        self._metadata: dict[str, dict] = {}
        self._dimensions: dict[str, tuple[int, int]] = {}
        self._source_paths: dict[str, str] = {}
        self._row_dimensions: list[tuple[int, int] | None] = []
        self._path_to_row: dict[str, int] = {}
        self._row_to_path: dict[int, str] = {}
        self._s3_client_lock = Lock()
        self._s3_session: Any | None = None
        self._s3_client: Any | None = None
        self._s3_client_creations = 0
        self._sorted_paths: list[str] = []
        self._sorted_items: list[TableBrowseItem] = []

        columns, data, row_count = _table_to_columns(table)
        if row_count == 0:
            raise ValueError("table is empty")

        self._columns = columns
        self._data = data
        self._row_count = row_count
        self._row_dimensions = [None] * row_count

        self._source_column = self._resolve_source_column(
            columns,
            data,
            source_column,
        )
        self._s3_prefixes, self._s3_use_bucket = self._compute_s3_prefixes()
        self._local_prefix = self._compute_local_prefix()
        self._path_column = resolve_path_column(
            columns,
            path_column,
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

        build_table_indexes(self, item_factory=TableBrowseItem, index_factory=TableBrowseIndex)
        self._build_path_index()
        self._browse_signature = self._compute_browse_signature()

    def _compute_browse_signature(self) -> str:
        digest = hashlib.sha256()
        digest.update(str(self.root or "").encode("utf-8"))
        digest.update(str(self._row_count).encode("utf-8"))
        for path in self._items.keys():
            digest.update(path.encode("utf-8"))
        return digest.hexdigest()

    def _resolve_source_column(
        self,
        columns: list[str],
        data: dict[str, list[Any]],
        source_column: str | None,
    ) -> str:
        return resolve_source_column(
            columns,
            data,
            source_column,
            loadable_threshold=self.loadable_threshold,
            sample_size=self.sample_size,
            allow_local=self._allow_local,
            is_loadable_value=self._is_loadable_value,
        )

    def _compute_s3_prefixes(self) -> tuple[dict[str, str], bool]:
        values = self._data.get(self._source_column, []) if hasattr(self, "_data") else []
        return compute_s3_prefixes(values)

    def _compute_local_prefix(self) -> str | None:
        if not self._allow_local:
            return None
        values = self._data.get(self._source_column, []) if hasattr(self, "_data") else []
        return compute_local_prefix(values)

    def _is_loadable_value(self, value: str) -> bool:
        if self._is_s3_uri(value) or self._is_http_url(value):
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

    def _is_supported_image(self, name: str) -> bool:
        return is_supported_image(name, self.IMAGE_EXTS)

    def _derive_logical_path(self, source: str) -> str:
        return derive_logical_path(
            source,
            root=self.root,
            local_prefix=self._local_prefix,
            s3_prefixes=self._s3_prefixes if hasattr(self, "_s3_prefixes") else {},
            s3_use_bucket=self._s3_use_bucket if hasattr(self, "_s3_use_bucket") else False,
        )

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

    def get_index(self, path: str) -> TableBrowseIndex | None:
        norm = self._normalize_path(path)
        if norm in self._indexes:
            return self._indexes[norm]
        return None

    def validate_image_path(self, path: str) -> None:
        if not path:
            raise ValueError("empty path")
        norm = self._normalize_item_path(path)
        if norm not in self._items:
            raise FileNotFoundError(path)

    def exists(self, path: str) -> bool:
        norm = self._normalize_item_path(path)
        return norm in self._items

    def size(self, path: str) -> int:
        norm = self._normalize_item_path(path)
        item = self._items.get(norm)
        if item is None:
            raise FileNotFoundError(path)
        return item.size

    def join(self, *parts: str) -> str:
        return join_storage_path(*parts)

    def etag(self, path: str) -> str | None:
        norm = self._normalize_item_path(path)
        item = self._items.get(norm)
        if not item:
            return None
        return f"{int(item.mtime)}-{item.size}"

    def _progress(self, done: int, total: int, label: str) -> None:
        self._progress_bar.update(done, total, label)

    def indexing_progress(self) -> dict[str, int | str | bool | None]:
        return self._progress_bar.snapshot()

    def browse_generation(self) -> int:
        return 0

    def browse_cache_signature(self) -> str:
        return self._browse_signature

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

    def row_index_for_path(self, path: str) -> int | None:
        norm = self._normalize_item_path(path)
        return self._path_to_row.get(norm)

    def path_for_row_index(self, index: int) -> str | None:
        return self._row_to_path.get(index)

    def table_fields_for_path(self, path: str) -> dict[str, Any]:
        row_idx = self.row_index_for_path(path)
        if row_idx is None:
            return {}
        return extract_row_display_fields(self, row_idx)

    def row_index_map(self) -> dict[int, str]:
        return dict(self._row_to_path)

    def s3_client_creations(self) -> int:
        return self._s3_client_creations


def load_parquet_table(path: str, columns: list[str] | None = None):
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(
            "pyarrow is required for Parquet datasets. Install with: pip install pyarrow"
        ) from exc
    return pq.read_table(path, columns=columns)


def load_parquet_schema(path: str):
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(
            "pyarrow is required for Parquet datasets. Install with: pip install pyarrow"
        ) from exc
    return pq.read_schema(path)
