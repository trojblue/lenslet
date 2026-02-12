from __future__ import annotations

import os
from threading import Lock
from dataclasses import dataclass, field
from typing import Any

from .progress import ProgressBar
from .table_facade import (
    get_dimensions as storage_get_dimensions,
    get_metadata as storage_get_metadata,
    get_presigned_url as storage_get_presigned_url,
    get_s3_client as storage_get_s3_client,
    get_thumbnail as storage_get_thumbnail,
    guess_mime as storage_guess_mime,
    make_thumbnail as storage_make_thumbnail,
    read_bytes as storage_read_bytes,
    search_items as storage_search_items,
    set_metadata as storage_set_metadata,
    table_to_columns,
)
from .table_index import (
    build_table_indexes,
    extract_row_metrics,
    extract_row_metrics_map,
)
from .table_media import (
    read_dimensions_fast,
    read_dimensions_from_bytes,
    read_jpeg_dimensions,
    read_png_dimensions,
    read_webp_dimensions,
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
)
from .table_schema import (
    coerce_float,
    coerce_int,
    coerce_timestamp,
    iter_sample,
    loadable_score,
    resolve_column,
    resolve_named_column,
    resolve_path_column,
    resolve_source_column,
)
from .table_probe import (
    effective_remote_workers,
    get_remote_header_bytes,
    get_remote_header_info,
    parse_content_range,
    probe_remote_dimensions,
)

# S0/T1 seam anchors (see docs/dev_notes/20260211_s0_t1_seam_map.md):
# - T9 schema/path extraction: _resolve_source_column/_compute_s3_prefixes/_compute_local_prefix.
# - T10 index pipeline extraction: _build_indexes + metric extraction helpers.
# - T11 probe/media extraction: _probe_remote_dimensions/_read_dimensions_from_bytes/_read_dimensions_fast.
# - T12 facade compatibility: keep TableStorage public methods + load_parquet_table/load_parquet_schema.


@dataclass
class CachedItem:
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
class CachedIndex:
    """In-memory cached folder index."""
    path: str
    generated_at: str
    items: list[CachedItem] = field(default_factory=list)
    dirs: list[str] = field(default_factory=list)


class TableStorage:
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
    ):
        self.root = os.path.abspath(root) if root else None
        self._root_real = os.path.realpath(self.root) if self.root else None
        self._allow_local = allow_local
        self.thumb_size = thumb_size
        self.thumb_quality = thumb_quality
        self.sample_size = sample_size
        self.loadable_threshold = loadable_threshold
        self._include_source_in_search = include_source_in_search
        self._skip_indexing = skip_indexing
        self._progress_bar = ProgressBar()

        self._indexes: dict[str, CachedIndex] = {}
        self._items: dict[str, CachedItem] = {}
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

        columns, data, row_count = self._table_to_columns(table)
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
        self._path_column = self._resolve_path_column(columns, path_column)
        self._name_column = self._resolve_named_column(columns, self.NAME_COLUMNS)
        self._mime_column = self._resolve_named_column(columns, self.MIME_COLUMNS)
        self._width_column = self._resolve_named_column(columns, self.WIDTH_COLUMNS)
        self._height_column = self._resolve_named_column(columns, self.HEIGHT_COLUMNS)
        self._size_column = self._resolve_named_column(columns, self.SIZE_COLUMNS)
        self._mtime_column = self._resolve_named_column(columns, self.MTIME_COLUMNS)
        self._metrics_column = None
        for col in columns:
            if col.lower() == "metrics":
                self._metrics_column = col
                break

        self._build_indexes()

    def _table_to_columns(self, table: Any) -> tuple[list[str], dict[str, list[Any]], int]:
        return table_to_columns(table)

    def _resolve_named_column(self, columns: list[str], candidates: tuple[str, ...]) -> str | None:
        return resolve_named_column(columns, candidates)

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

    def _resolve_path_column(self, columns: list[str], path_column: str | None) -> str | None:
        return resolve_path_column(
            columns,
            path_column,
            logical_path_columns=self.LOGICAL_PATH_COLUMNS,
        )

    def _resolve_column(self, columns: list[str], name: str) -> str | None:
        return resolve_column(columns, name)

    def _loadable_score(self, values: list[Any]) -> tuple[int, int]:
        return loadable_score(
            values,
            sample_size=self.sample_size,
            is_loadable_value=self._is_loadable_value,
        )

    def _iter_sample(self, values: list[Any]):
        return iter_sample(values)

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

    def _is_s3_uri(self, path: str) -> bool:
        return is_s3_uri(path)

    def _is_http_url(self, path: str) -> bool:
        return is_http_url(path)

    def _is_supported_image(self, name: str) -> bool:
        return is_supported_image(name, self.IMAGE_EXTS)

    def _extract_name(self, value: str) -> str:
        return extract_name(value)

    def _normalize_path(self, path: str) -> str:
        return normalize_path(path)

    def _normalize_item_path(self, path: str) -> str:
        return normalize_item_path(path)

    def _canonical_meta_key(self, path: str) -> str:
        return canonical_meta_key(path)

    def _dedupe_path(self, path: str, seen: set[str]) -> str:
        return dedupe_path(path, seen)

    def _derive_logical_path(self, source: str) -> str:
        return derive_logical_path(
            source,
            root=self.root,
            local_prefix=self._local_prefix,
            s3_prefixes=self._s3_prefixes if hasattr(self, "_s3_prefixes") else {},
            s3_use_bucket=self._s3_use_bucket if hasattr(self, "_s3_use_bucket") else False,
        )

    def _coerce_float(self, value: Any) -> float | None:
        return coerce_float(value)

    def _coerce_int(self, value: Any) -> int | None:
        return coerce_int(value)

    def _coerce_timestamp(self, value: Any) -> float | None:
        return coerce_timestamp(value)

    def _build_indexes(self) -> None:
        build_table_indexes(self, item_factory=CachedItem, index_factory=CachedIndex)

    def _extract_metrics(self, row_idx: int) -> dict[str, float]:
        return extract_row_metrics(self, row_idx)

    def _extract_metrics_map(self, row_idx: int) -> dict[str, float]:
        return extract_row_metrics_map(self, row_idx)

    def _resolve_local_source(self, source: str) -> str:
        return resolve_local_source(
            source,
            root=self.root,
            root_real=self._root_real,
            allow_local=self._allow_local,
        )

    def get_index(self, path: str) -> CachedIndex:
        norm = self._normalize_path(path)
        if norm in self._indexes:
            return self._indexes[norm]
        raise FileNotFoundError(path)

    def validate_image_path(self, path: str) -> None:
        if not path:
            raise ValueError("empty path")
        norm = self._normalize_item_path(path)
        if norm not in self._items:
            raise FileNotFoundError(path)

    def read_bytes(self, path: str) -> bytes:
        return storage_read_bytes(self, path)

    def exists(self, path: str) -> bool:
        norm = self._normalize_item_path(path)
        return norm in self._items

    def size(self, path: str) -> int:
        norm = self._normalize_item_path(path)
        item = self._items.get(norm)
        return item.size if item else 0

    def join(self, *parts: str) -> str:
        return "/".join([p.strip("/") for p in parts if p])

    def etag(self, path: str) -> str | None:
        norm = self._normalize_item_path(path)
        item = self._items.get(norm)
        if not item:
            return None
        return f"{int(item.mtime)}-{item.size}"

    def get_thumbnail(self, path: str) -> bytes | None:
        return storage_get_thumbnail(self, path)

    def _make_thumbnail(self, img_bytes: bytes) -> tuple[bytes, tuple[int, int] | None]:
        return storage_make_thumbnail(
            img_bytes,
            thumb_size=self.thumb_size,
            thumb_quality=self.thumb_quality,
        )

    def get_dimensions(self, path: str) -> tuple[int, int]:
        return storage_get_dimensions(self, path)

    def get_metadata(self, path: str) -> dict:
        return storage_get_metadata(self, path)

    def set_metadata(self, path: str, meta: dict) -> None:
        storage_set_metadata(self, path, meta)

    def search(self, query: str = "", path: str = "/", limit: int = 100) -> list[CachedItem]:
        return storage_search_items(self, query=query, path=path, limit=limit)

    def _probe_remote_dimensions(self, tasks: list[tuple[str, CachedItem, str, str]]) -> None:
        probe_remote_dimensions(self, tasks)

    def _progress(self, done: int, total: int, label: str) -> None:
        self._progress_bar.update(done, total, label)

    def indexing_progress(self) -> dict[str, int | str | bool | None]:
        return self._progress_bar.snapshot()

    def row_dimensions(self) -> list[tuple[int, int] | None]:
        return list(self._row_dimensions)

    def row_index_for_path(self, path: str) -> int | None:
        norm = self._normalize_item_path(path)
        return self._path_to_row.get(norm)

    def path_for_row_index(self, index: int) -> str | None:
        return self._row_to_path.get(index)

    def row_index_map(self) -> dict[int, str]:
        return dict(self._row_to_path)

    def _effective_remote_workers(self, total: int) -> int:
        return effective_remote_workers(
            total,
            baseline_workers=self.REMOTE_DIM_WORKERS,
            max_workers=self.REMOTE_DIM_WORKERS_MAX,
            cpu_count=os.cpu_count,
        )

    def _get_s3_client(self):
        return storage_get_s3_client(self)

    def s3_client_creations(self) -> int:
        return self._s3_client_creations

    def _get_presigned_url(self, s3_uri: str, expires_in: int = 3600) -> str:
        return storage_get_presigned_url(self, s3_uri, expires_in=expires_in)

    def _parse_content_range(self, header: str) -> int | None:
        return parse_content_range(header)

    def _get_remote_header_bytes(self, url: str, max_bytes: int | None = None) -> tuple[bytes | None, int | None]:
        return get_remote_header_bytes(
            url,
            max_bytes=max_bytes or self.REMOTE_HEADER_BYTES,
            parse_content_range_fn=self._parse_content_range,
        )

    def _get_remote_header_info(self, url: str, name: str) -> tuple[tuple[int, int] | None, int | None]:
        return get_remote_header_info(
            url,
            name,
            max_bytes=self.REMOTE_HEADER_BYTES,
            read_dimensions_from_bytes=self._read_dimensions_from_bytes,
            get_remote_header_bytes_fn=self._get_remote_header_bytes,
        )

    def _read_dimensions_from_bytes(self, data: bytes, ext: str | None) -> tuple[int, int] | None:
        return read_dimensions_from_bytes(data, ext)

    def _read_dimensions_fast(self, filepath: str) -> tuple[int, int] | None:
        return read_dimensions_fast(filepath)

    def _jpeg_dimensions(self, f) -> tuple[int, int] | None:
        return read_jpeg_dimensions(f)

    def _png_dimensions(self, f) -> tuple[int, int] | None:
        return read_png_dimensions(f)

    def _webp_dimensions(self, f) -> tuple[int, int] | None:
        return read_webp_dimensions(f)

    def _guess_mime(self, name: str) -> str:
        return storage_guess_mime(name)


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
