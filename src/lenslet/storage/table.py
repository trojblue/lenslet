from __future__ import annotations

import math
import os
import struct
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from urllib.parse import urlparse

from PIL import Image

from .progress import ProgressBar

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
    ):
        self.root = os.path.abspath(root) if root else None
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

        row_count = 0
        if columns:
            row_count = len(data.get(columns[0], []))
        return columns, data, row_count

    def _resolve_named_column(self, columns: list[str], candidates: tuple[str, ...]) -> str | None:
        candidates_lower = {c.lower() for c in candidates}
        for col in columns:
            if col.lower() in candidates_lower:
                return col
        return None

    def _resolve_source_column(
        self,
        columns: list[str],
        data: dict[str, list[Any]],
        source_column: str | None,
    ) -> str:
        if source_column:
            resolved = self._resolve_column(columns, source_column)
            if resolved is None:
                raise ValueError(f"source column '{source_column}' not found")
            return resolved

        for col in columns:
            total, matches = self._loadable_score(data.get(col, []))
            if total == 0:
                continue
            if matches / total >= self.loadable_threshold:
                return col

        raise ValueError(
            "No loadable column found. Pass source_column explicitly or provide a base_dir for local paths."
        )

    def _compute_s3_prefixes(self) -> tuple[dict[str, str], bool]:
        buckets: dict[str, list[list[str]]] = {}
        values = self._data.get(self._source_column, []) if hasattr(self, "_data") else []
        for raw in values:
            if raw is None:
                continue
            if isinstance(raw, os.PathLike):
                raw = os.fspath(raw)
            if not isinstance(raw, str):
                continue
            uri = raw.strip()
            if not uri.startswith("s3://"):
                continue
            parsed = urlparse(uri)
            bucket = parsed.netloc
            key = parsed.path.lstrip("/")
            if not bucket or not key:
                continue
            parts = [p for p in key.split("/") if p]
            if not parts:
                continue
            buckets.setdefault(bucket, []).append(parts)

        if not buckets:
            return {}, False

        prefixes: dict[str, str] = {}
        for bucket, paths in buckets.items():
            if not paths:
                continue
            common = paths[0]
            for parts in paths[1:]:
                max_len = min(len(common), len(parts))
                i = 0
                while i < max_len and common[i] == parts[i]:
                    i += 1
                common = common[:i]
                if not common:
                    break
            prefix = "/".join(common)
            if prefix:
                prefix = prefix.rstrip("/") + "/"
            prefixes[bucket] = prefix

        use_bucket = len(prefixes) > 1
        return prefixes, use_bucket

    def _compute_local_prefix(self) -> str | None:
        values = self._data.get(self._source_column, []) if hasattr(self, "_data") else []
        local_paths: list[str] = []
        for raw in values:
            if raw is None:
                continue
            if isinstance(raw, os.PathLike):
                raw = os.fspath(raw)
            if not isinstance(raw, str):
                continue
            value = raw.strip()
            if not value:
                continue
            if self._is_s3_uri(value) or self._is_http_url(value):
                continue
            if not os.path.isabs(value):
                continue
            local_paths.append(os.path.normpath(value))

        if not local_paths:
            return None

        try:
            common = os.path.commonpath(local_paths)
        except ValueError:
            return None

        if not common or common == os.path.sep:
            return common if common else None

        # If files sit directly under the common prefix, step up one level
        # so the prefix folder itself stays visible in the UI.
        if any(os.path.dirname(path) == common for path in local_paths):
            parent = os.path.dirname(common)
            if parent and parent != common:
                return parent
        return common

    def _resolve_path_column(self, columns: list[str], path_column: str | None) -> str | None:
        if path_column:
            resolved = self._resolve_column(columns, path_column)
            if resolved is None:
                raise ValueError(f"path column '{path_column}' not found")
            return resolved

        return self._resolve_named_column(columns, self.LOGICAL_PATH_COLUMNS)

    def _resolve_column(self, columns: list[str], name: str) -> str | None:
        for col in columns:
            if col == name:
                return col
        name_lower = name.lower()
        for col in columns:
            if col.lower() == name_lower:
                return col
        return None

    def _loadable_score(self, values: list[Any]) -> tuple[int, int]:
        total = 0
        matches = 0
        for value in self._iter_sample(values):
            total += 1
            if self._is_loadable_value(value):
                matches += 1
            if total >= self.sample_size:
                break
        return total, matches

    def _iter_sample(self, values: list[Any]):
        for value in values:
            if value is None:
                continue
            if isinstance(value, float) and math.isnan(value):
                continue
            if isinstance(value, os.PathLike):
                value = os.fspath(value)
            if not isinstance(value, str):
                continue
            value = value.strip()
            if not value:
                continue
            yield value

    def _is_loadable_value(self, value: str) -> bool:
        if self._is_s3_uri(value) or self._is_http_url(value):
            return True
        if os.path.isabs(value):
            return os.path.exists(value)
        if self.root:
            return os.path.exists(os.path.join(self.root, value))
        return False

    def _is_s3_uri(self, path: str) -> bool:
        return path.startswith("s3://")

    def _is_http_url(self, path: str) -> bool:
        return path.startswith("http://") or path.startswith("https://")

    def _is_supported_image(self, name: str) -> bool:
        return name.lower().endswith(self.IMAGE_EXTS)

    def _extract_name(self, value: str) -> str:
        if self._is_s3_uri(value) or self._is_http_url(value):
            parsed = urlparse(value)
            return os.path.basename(parsed.path)
        return os.path.basename(value)

    def _normalize_path(self, path: str) -> str:
        return path.strip("/") if path else ""

    def _normalize_item_path(self, path: str) -> str:
        p = (path or "").replace("\\", "/").lstrip("/")
        if p.startswith("./"):
            p = p[2:]
        return p.strip("/")

    def _canonical_meta_key(self, path: str) -> str:
        """Canonical key for metadata maps (leading slash, no trailing)."""
        p = (path or "").replace("\\", "/").strip()
        if not p:
            return "/"
        p = "/" + p.lstrip("/")
        if p != "/":
            p = p.rstrip("/")
        return p

    def _dedupe_path(self, path: str, seen: set[str]) -> str:
        if path not in seen:
            return path
        stem, ext = os.path.splitext(path)
        idx = 2
        while f"{stem}-{idx}{ext}" in seen:
            idx += 1
        return f"{stem}-{idx}{ext}"

    def _derive_logical_path(self, source: str) -> str:
        if self._is_s3_uri(source) or self._is_http_url(source):
            parsed = urlparse(source)
            host = parsed.netloc
            path = parsed.path.lstrip("/")
            if self._is_s3_uri(source):
                prefix = self._s3_prefixes.get(host, "") if hasattr(self, "_s3_prefixes") else ""
                trimmed = path[len(prefix):] if prefix and path.startswith(prefix) else path
                trimmed = trimmed.lstrip("/")
                if self._s3_use_bucket and host:
                    return f"{host}/{trimmed}" if trimmed else host
                return trimmed or os.path.basename(path)
            if host and path:
                return f"{host}/{path}"
            return host or path

        if os.path.isabs(source):
            if self._local_prefix:
                try:
                    rel = os.path.relpath(source, self._local_prefix)
                    if not rel.startswith(".."):
                        return rel
                except ValueError:
                    pass
            if self.root:
                try:
                    rel = os.path.relpath(source, self.root)
                    return rel
                except ValueError:
                    return os.path.basename(source)
            return os.path.basename(source)

        if self.root:
            return source
        return os.path.basename(source)

    def _coerce_float(self, value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _coerce_int(self, value: Any) -> int | None:
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

    def _coerce_timestamp(self, value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if hasattr(value, "timestamp"):
            try:
                return float(value.timestamp())
            except Exception:
                return None
        return self._coerce_float(value)

    def _build_indexes(self) -> None:
        generated_at = datetime.now(timezone.utc).isoformat()
        dir_children: dict[str, set[str]] = {}
        seen_paths: set[str] = set()
        remote_tasks: list[tuple[str, CachedItem, str, str]] = []
        total = self._row_count
        done = 0
        last_print = 0.0
        progress_label = f"table:{self._source_column}"

        for idx in range(self._row_count):
            source_value = self._data.get(self._source_column, [None] * self._row_count)[idx]
            if source_value is None:
                done += 1
                now = time.monotonic()
                if now - last_print > 0.1 or done == total:
                    self._progress(done, total, progress_label)
                    last_print = now
                continue
            if isinstance(source_value, os.PathLike):
                source_value = os.fspath(source_value)
            if not isinstance(source_value, str):
                done += 1
                now = time.monotonic()
                if now - last_print > 0.1 or done == total:
                    self._progress(done, total, progress_label)
                    last_print = now
                continue
            source = source_value.strip()
            if not source:
                done += 1
                now = time.monotonic()
                if now - last_print > 0.1 or done == total:
                    self._progress(done, total, progress_label)
                    last_print = now
                continue

            name_value = None
            if self._name_column:
                name_value = self._data.get(self._name_column, [None] * self._row_count)[idx]
            fallback_name = self._extract_name(source)
            name = str(name_value).strip() if name_value else fallback_name
            if not self._is_supported_image(name):
                if self._is_supported_image(fallback_name):
                    name = fallback_name
                else:
                    done += 1
                    now = time.monotonic()
                    if now - last_print > 0.1 or done == total:
                        self._progress(done, total, progress_label)
                        last_print = now
                    continue

            logical_value = None
            if self._path_column and not self._is_s3_uri(source):
                logical_value = self._data.get(self._path_column, [None] * self._row_count)[idx]
            logical_path = str(logical_value).strip() if logical_value else self._derive_logical_path(source)
            if logical_path and os.path.isabs(logical_path) and self._local_prefix:
                try:
                    rel = os.path.relpath(logical_path, self._local_prefix)
                    if not rel.startswith(".."):
                        logical_path = rel
                except ValueError:
                    pass
            logical_path = self._normalize_item_path(logical_path)
            if not logical_path:
                done += 1
                now = time.monotonic()
                if now - last_print > 0.1 or done == total:
                    self._progress(done, total, progress_label)
                    last_print = now
                continue
            logical_path = self._dedupe_path(logical_path, seen_paths)
            seen_paths.add(logical_path)

            mime_value = None
            if self._mime_column:
                mime_value = self._data.get(self._mime_column, [None] * self._row_count)[idx]
            mime = str(mime_value).strip() if mime_value else self._guess_mime(name or fallback_name or source)

            size = None
            if self._size_column:
                size = self._coerce_int(self._data.get(self._size_column, [None] * self._row_count)[idx])
            mtime = None
            if self._mtime_column:
                mtime = self._coerce_timestamp(self._data.get(self._mtime_column, [None] * self._row_count)[idx])
            width = None
            if self._width_column:
                width = self._coerce_int(self._data.get(self._width_column, [None] * self._row_count)[idx])
            height = None
            if self._height_column:
                height = self._coerce_int(self._data.get(self._height_column, [None] * self._row_count)[idx])

            is_s3 = self._is_s3_uri(source)
            is_http = self._is_http_url(source)

            if not is_s3 and not is_http:
                resolved = self._resolve_local_source(source)
                if not os.path.exists(resolved):
                    print(f"[lenslet] Warning: File not found: {resolved}")
                    done += 1
                    now = time.monotonic()
                    if now - last_print > 0.1 or done == total:
                        self._progress(done, total, progress_label)
                        last_print = now
                    continue
                if size is None:
                    try:
                        size = os.path.getsize(resolved)
                    except Exception:
                        size = 0
            if size is None:
                size = 0

            if mtime is None:
                if not is_s3 and not is_http:
                    try:
                        mtime = os.path.getmtime(self._resolve_local_source(source))
                    except Exception:
                        mtime = time.time()
                else:
                    mtime = time.time()

            w = width or 0
            h = height or 0
            if (w == 0 or h == 0) and not is_s3 and not is_http and not self._skip_indexing:
                try:
                    abs_path = self._resolve_local_source(source)
                    dims = self._read_dimensions_fast(abs_path)
                    if dims:
                        w, h = dims
                        self._dimensions[logical_path] = dims
                except Exception:
                    pass

            metrics = self._extract_metrics(idx)
            metrics_map = self._extract_metrics_map(idx)
            if metrics_map:
                metrics.update(metrics_map)

            url = source if is_http else None

            item = CachedItem(
                path=logical_path,
                name=name,
                mime=mime,
                width=w,
                height=h,
                size=size,
                mtime=mtime or 0.0,
                url=url,
                source=source,
                metrics=metrics,
            )

            self._items[logical_path] = item
            self._source_paths[logical_path] = source
            self._row_dimensions[idx] = (w, h)
            self._path_to_row[logical_path] = idx
            self._row_to_path[idx] = logical_path

            folder = os.path.dirname(logical_path).replace("\\", "/")
            folder_norm = self._normalize_path(folder)
            self._indexes.setdefault(folder_norm, CachedIndex(
                path="/" + folder_norm if folder_norm else "/",
                generated_at=generated_at,
                items=[],
                dirs=[],
            )).items.append(item)

            parts = folder_norm.split("/") if folder_norm else []
            for depth in range(len(parts)):
                parent = "/".join(parts[:depth])
                child = parts[depth]
                dir_children.setdefault(parent, set()).add(child)

            if (is_s3 or is_http) and (w == 0 or h == 0) and not self._skip_indexing:
                remote_tasks.append((logical_path, item, source, name))
            done += 1
            now = time.monotonic()
            if now - last_print > 0.1 or done == total:
                self._progress(done, total, progress_label)
                last_print = now

        self._indexes.setdefault("", CachedIndex(path="/", generated_at=generated_at, items=[], dirs=[]))
        for parent, children in dir_children.items():
            index = self._indexes.setdefault(parent, CachedIndex(
                path="/" + parent if parent else "/",
                generated_at=generated_at,
                items=[],
                dirs=[],
            ))
            index.dirs = sorted(children)

        if remote_tasks:
            self._probe_remote_dimensions(remote_tasks)

        if done < total:
            self._progress(total, total, progress_label)

    def _extract_metrics(self, row_idx: int) -> dict[str, float]:
        metrics: dict[str, float] = {}
        used_columns = {
            self._source_column,
            self._path_column,
            self._name_column,
            self._mime_column,
            self._width_column,
            self._height_column,
            self._size_column,
            self._mtime_column,
        }
        for col in self._columns:
            if col in used_columns:
                continue
            if col.lower() in self.RESERVED_COLUMNS:
                continue
            val = self._data.get(col, [None] * self._row_count)[row_idx]
            num = self._coerce_float(val)
            if num is None:
                continue
            metrics[col] = num
        return metrics

    def _extract_metrics_map(self, row_idx: int) -> dict[str, float]:
        if not self._metrics_column:
            return {}
        raw = self._data.get(self._metrics_column, [None] * self._row_count)[row_idx]
        if not isinstance(raw, dict):
            return {}
        result: dict[str, float] = {}
        for key, value in raw.items():
            num = self._coerce_float(value)
            if num is None:
                continue
            result[str(key)] = num
        return result

    def _resolve_local_source(self, source: str) -> str:
        if os.path.isabs(source) or not self.root:
            return source
        return os.path.join(self.root, source)

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
        norm = self._normalize_item_path(path)
        source = self._source_paths.get(norm)
        if source is None:
            raise FileNotFoundError(path)

        if self._is_s3_uri(source):
            import urllib.request
            try:
                url = self._get_presigned_url(source)
                with urllib.request.urlopen(url) as response:
                    return response.read()
            except Exception as exc:
                raise RuntimeError(f"Failed to download from S3: {exc}")
        if self._is_http_url(source):
            import urllib.request
            try:
                with urllib.request.urlopen(source) as response:
                    return response.read()
            except Exception as exc:
                raise RuntimeError(f"Failed to download from URL: {exc}")

        with open(self._resolve_local_source(source), "rb") as handle:
            return handle.read()

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
        norm = self._normalize_item_path(path)
        if norm in self._thumbnails:
            return self._thumbnails[norm]

        try:
            raw = self.read_bytes(norm)
            thumb, dims = self._make_thumbnail(raw)
            self._thumbnails[norm] = thumb
            if dims:
                self._dimensions[norm] = dims
                item = self._items.get(norm)
                if item:
                    item.width, item.height = dims
            return thumb
        except Exception:
            return None

    def _make_thumbnail(self, img_bytes: bytes) -> tuple[bytes, tuple[int, int] | None]:
        with Image.open(BytesIO(img_bytes)) as im:
            w, h = im.size
            short = min(w, h)
            if short > self.thumb_size:
                scale = self.thumb_size / short
                new_w = max(1, int(w * scale))
                new_h = max(1, int(h * scale))
                im = im.convert("RGB").resize((new_w, new_h), Image.LANCZOS)
            else:
                im = im.convert("RGB")
            out = BytesIO()
            im.save(out, format="WEBP", quality=self.thumb_quality, method=6)
            return out.getvalue(), (w, h)

    def get_dimensions(self, path: str) -> tuple[int, int]:
        norm = self._normalize_item_path(path)
        if norm in self._dimensions:
            return self._dimensions[norm]
        item = self._items.get(norm)
        if not item:
            return 0, 0

        source = self._source_paths.get(norm)
        if source and (self._is_s3_uri(source) or self._is_http_url(source)):
            url = source
            if self._is_s3_uri(source):
                try:
                    url = self._get_presigned_url(source)
                except Exception:
                    url = None
            if url:
                dims, total = self._get_remote_header_info(url, item.name)
                if total:
                    item.size = total
                if dims:
                    self._dimensions[norm] = dims
                    item.width, item.height = dims
                    return dims

        try:
            raw = self.read_bytes(norm)
            with Image.open(BytesIO(raw)) as im:
                w, h = im.size
                self._dimensions[norm] = (w, h)
                item.width = w
                item.height = h
                return w, h
        except Exception:
            return 0, 0

    def get_metadata(self, path: str) -> dict:
        norm = self._normalize_item_path(path)
        key = self._canonical_meta_key(norm)
        if key in self._metadata:
            return self._metadata[key]

        w, h = self._dimensions.get(norm, (0, 0))
        item = self._items.get(norm)
        if item and (w == 0 or h == 0):
            w, h = item.width, item.height

        meta = {
            "width": w,
            "height": h,
            "tags": [],
            "notes": "",
            "star": None,
            "version": 1,
            "updated_at": "",
            "updated_by": "server",
        }
        self._metadata[key] = meta
        return meta

    def set_metadata(self, path: str, meta: dict) -> None:
        norm = self._normalize_item_path(path)
        key = self._canonical_meta_key(norm)
        self._metadata[key] = meta

    def search(self, query: str = "", path: str = "/", limit: int = 100) -> list[CachedItem]:
        q = (query or "").lower()
        norm = self._normalize_path(path)
        scope_prefix = f"{norm}/" if norm else ""

        results: list[CachedItem] = []
        for item in self._items.values():
            logical_path = item.path.lstrip("/")
            if norm and not (logical_path == norm or logical_path.startswith(scope_prefix)):
                continue
            meta = self.get_metadata(item.path)
            parts = [
                item.name,
                " ".join(meta.get("tags", [])),
                meta.get("notes", ""),
            ]
            if self._include_source_in_search:
                source = self._source_paths.get(item.path, "")
                if source:
                    parts.append(source)
                if item.url:
                    parts.append(item.url)
            haystack = " ".join(parts).lower()
            if q in haystack:
                results.append(item)
                if len(results) >= limit:
                    break
        return results

    def _probe_remote_dimensions(self, tasks: list[tuple[str, CachedItem, str, str]]) -> None:
        total = len(tasks)
        if total == 0:
            return
        workers = self._effective_remote_workers(total)
        if workers <= 0:
            return

        def _work(task: tuple[str, CachedItem, str, str]):
            logical_path, item, source_path, name = task
            url = source_path
            if self._is_s3_uri(source_path):
                try:
                    url = self._get_presigned_url(source_path)
                except Exception:
                    url = None
            if not url:
                return logical_path, item, None, None
            dims, total_size = self._get_remote_header_info(url, name)
            return logical_path, item, dims, total_size

        from concurrent.futures import ThreadPoolExecutor, as_completed
        done = 0
        last_print = 0.0
        progress_label = "remote headers"
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_work, task) for task in tasks]
            for future in as_completed(futures):
                logical_path, item, dims, total_size = future.result()
                if dims:
                    self._dimensions[logical_path] = dims
                    item.width, item.height = dims
                if total_size:
                    item.size = total_size
                row_idx = self._path_to_row.get(logical_path)
                if row_idx is not None:
                    self._row_dimensions[row_idx] = (item.width, item.height)
                done += 1
                now = time.monotonic()
                if now - last_print > 0.1 or done == total:
                    self._progress(done, total, progress_label)
                    last_print = now

    def _progress(self, done: int, total: int, label: str) -> None:
        self._progress_bar.update(done, total, label)

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
        if total <= 0:
            return 0
        cpu = os.cpu_count() or 1
        # Scale with CPU availability but keep the historical 16-thread baseline.
        cap = max(self.REMOTE_DIM_WORKERS, cpu)
        cap = min(cap, self.REMOTE_DIM_WORKERS_MAX)
        return max(1, min(cap, total))

    def _get_presigned_url(self, s3_uri: str, expires_in: int = 3600) -> str:
        try:
            import boto3
            from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError(
                "boto3 package required for S3 support. Install with: pip install lenslet[s3]"
            ) from exc

        parsed = urlparse(s3_uri)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        if not bucket or not key:
            raise ValueError(f"Invalid S3 URI: {s3_uri}")

        try:
            s3_client = boto3.client("s3")
            return s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        except (BotoCoreError, ClientError, NoCredentialsError) as exc:
            raise RuntimeError(f"Failed to presign S3 URI: {exc}") from exc

    def _parse_content_range(self, header: str) -> int | None:
        try:
            if "/" not in header:
                return None
            total = header.split("/")[-1].strip()
            if total == "*":
                return None
            return int(total)
        except Exception:
            return None

    def _get_remote_header_bytes(self, url: str, max_bytes: int | None = None) -> tuple[bytes | None, int | None]:
        max_bytes = max_bytes or self.REMOTE_HEADER_BYTES
        try:
            import urllib.request
            req = urllib.request.Request(
                url,
                headers={"Range": f"bytes=0-{max_bytes - 1}"},
            )
            with urllib.request.urlopen(req) as response:
                data = response.read(max_bytes)
                total = None
                content_range = response.headers.get("Content-Range")
                if content_range:
                    total = self._parse_content_range(content_range)
                if total is None:
                    content_length = response.headers.get("Content-Length")
                    if content_length:
                        try:
                            total = int(content_length)
                        except Exception:
                            total = None
                return data, total
        except Exception:
            return None, None

    def _get_remote_header_info(self, url: str, name: str) -> tuple[tuple[int, int] | None, int | None]:
        header, total = self._get_remote_header_bytes(url)
        if not header:
            return None, total
        ext = os.path.splitext(name)[1].lower().lstrip(".") or None
        return self._read_dimensions_from_bytes(header, ext), total

    def _read_dimensions_from_bytes(self, data: bytes, ext: str | None) -> tuple[int, int] | None:
        if not data:
            return None

        kind = None
        if ext in ("jpg", "jpeg"):
            kind = "jpeg"
        elif ext == "png":
            kind = "png"
        elif ext == "webp":
            kind = "webp"
        else:
            if data.startswith(b"\xff\xd8"):
                kind = "jpeg"
            elif data.startswith(b"\x89PNG\r\n\x1a\n"):
                kind = "png"
            elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
                kind = "webp"

        try:
            buf = BytesIO(data)
            if kind == "jpeg":
                return self._jpeg_dimensions(buf)
            if kind == "png":
                return self._png_dimensions(buf)
            if kind == "webp":
                return self._webp_dimensions(buf)
        except Exception:
            return None
        return None

    def _read_dimensions_fast(self, filepath: str) -> tuple[int, int] | None:
        ext = filepath.lower().split(".")[-1]
        try:
            with open(filepath, "rb") as handle:
                if ext in ("jpg", "jpeg"):
                    return self._jpeg_dimensions(handle)
                if ext == "png":
                    return self._png_dimensions(handle)
                if ext == "webp":
                    return self._webp_dimensions(handle)
        except Exception:
            pass
        return None

    def _jpeg_dimensions(self, f) -> tuple[int, int] | None:
        f.seek(0)
        if f.read(2) != b"\xff\xd8":
            return None
        while True:
            marker = f.read(2)
            if len(marker) < 2 or marker[0] != 0xFF:
                return None
            if marker[1] == 0xD9:
                return None
            if 0xC0 <= marker[1] <= 0xCF and marker[1] not in (0xC4, 0xC8, 0xCC):
                f.read(2)
                f.read(1)
                h, w = struct.unpack(">HH", f.read(4))
                return w, h
            length = struct.unpack(">H", f.read(2))[0]
            f.seek(length - 2, 1)

    def _png_dimensions(self, f) -> tuple[int, int] | None:
        f.seek(0)
        if f.read(8) != b"\x89PNG\r\n\x1a\n":
            return None
        f.read(4)
        if f.read(4) != b"IHDR":
            return None
        w, h = struct.unpack(">II", f.read(8))
        return w, h

    def _webp_dimensions(self, f) -> tuple[int, int] | None:
        f.seek(0)
        if f.read(4) != b"RIFF":
            return None
        f.read(4)
        if f.read(4) != b"WEBP":
            return None
        chunk = f.read(4)
        if chunk == b"VP8 ":
            f.read(4)
            f.read(3)
            if f.read(3) != b"\x9d\x01\x2a":
                return None
            data = f.read(4)
            w = (data[0] | (data[1] << 8)) & 0x3FFF
            h = (data[2] | (data[3] << 8)) & 0x3FFF
            return w, h
        if chunk == b"VP8L":
            f.read(4)
            if f.read(1) != b"\x2f":
                return None
            data = struct.unpack("<I", f.read(4))[0]
            w = (data & 0x3FFF) + 1
            h = ((data >> 14) & 0x3FFF) + 1
            return w, h
        if chunk == b"VP8X":
            f.read(4)
            f.read(4)
            data = f.read(6)
            w = (data[0] | (data[1] << 8) | (data[2] << 16)) + 1
            h = (data[3] | (data[4] << 8) | (data[5] << 16)) + 1
            return w, h
        return None

    def _guess_mime(self, name: str) -> str:
        n = name.lower()
        if n.endswith(".webp"):
            return "image/webp"
        if n.endswith(".png"):
            return "image/png"
        return "image/jpeg"


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
