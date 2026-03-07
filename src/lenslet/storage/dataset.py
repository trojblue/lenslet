"""In-memory dataset storage for programmatic API."""
from __future__ import annotations

import hashlib
import os
import posixpath
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from urllib.parse import urlparse

from .progress import ProgressBar
from .table_facade import (
    get_dimensions as storage_get_dimensions,
    get_metadata as storage_get_metadata,
    get_metadata_readonly as storage_get_metadata_readonly,
    get_presigned_url as storage_get_presigned_url,
    get_s3_client as storage_get_s3_client,
    get_thumbnail as storage_get_thumbnail,
    guess_mime as storage_guess_mime,
    make_thumbnail as storage_make_thumbnail,
    read_bytes as storage_read_bytes,
    search_items as storage_search_items,
    set_metadata as storage_set_metadata,
)
from .table_index import ScannedRow, assemble_indexes
from .table_media import (
    read_dimensions_from_bytes,
    read_jpeg_dimensions,
    read_png_dimensions,
    read_webp_dimensions,
)
from .table_paths import (
    canonical_meta_key,
    dedupe_path,
    extract_name,
    is_http_url,
    is_s3_uri,
    is_supported_image,
    normalize_item_path,
    normalize_path,
)
from .table_probe import (
    effective_remote_workers,
    get_remote_header_bytes,
    get_remote_header_info,
    parse_content_range,
    probe_remote_dimensions,
)


@dataclass
class CachedItem:
    """In-memory cached metadata for an image."""

    path: str
    name: str
    mime: str
    width: int
    height: int
    size: int
    mtime: float
    url: str | None = None


@dataclass
class CachedIndex:
    """In-memory cached folder index."""

    path: str
    generated_at: str
    items: list[CachedItem] = field(default_factory=list)
    dirs: list[str] = field(default_factory=list)


def _common_parts(groups: list[list[str]]) -> list[str]:
    if not groups:
        return []
    common = list(groups[0])
    for parts in groups[1:]:
        limit = min(len(common), len(parts))
        idx = 0
        while idx < limit and common[idx] == parts[idx]:
            idx += 1
        common = common[:idx]
        if not common:
            break
    return common


def _compute_dataset_local_prefix(paths: list[str]) -> str | None:
    local_dirs: list[str] = []
    for source in paths:
        if is_s3_uri(source) or is_http_url(source):
            continue
        local_dirs.append(os.path.dirname(os.path.abspath(source)))
    if not local_dirs:
        return None
    try:
        return os.path.commonpath(local_dirs)
    except ValueError:
        return None


def _compute_dataset_s3_prefixes(paths: list[str]) -> tuple[dict[str, str], bool]:
    buckets: dict[str, list[list[str]]] = {}
    for source in paths:
        if not is_s3_uri(source):
            continue
        parsed = urlparse(source)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        if not bucket or not key:
            continue
        directory = posixpath.dirname(key)
        parts = [part for part in directory.split("/") if part and part != "."]
        buckets.setdefault(bucket, []).append(parts)

    prefixes: dict[str, str] = {}
    for bucket, groups in buckets.items():
        prefix_parts = _common_parts(groups)
        prefix = "/".join(prefix_parts)
        prefixes[bucket] = f"{prefix}/" if prefix else ""
    return prefixes, len(prefixes) > 1


def _compute_dataset_http_prefixes(paths: list[str]) -> tuple[dict[str, str], bool]:
    hosts: dict[str, list[list[str]]] = {}
    for source in paths:
        if not is_http_url(source):
            continue
        parsed = urlparse(source)
        host = parsed.netloc
        path = parsed.path.lstrip("/")
        if not host or not path:
            continue
        directory = posixpath.dirname(path)
        parts = [part for part in directory.split("/") if part and part != "."]
        hosts.setdefault(host, []).append(parts)

    prefixes: dict[str, str] = {}
    for host, groups in hosts.items():
        prefix_parts = _common_parts(groups)
        prefix = "/".join(prefix_parts)
        prefixes[host] = f"{prefix}/" if prefix else ""
    return prefixes, len(prefixes) > 1


def _trim_prefix(path: str, prefix: str) -> str:
    if prefix and path.startswith(prefix):
        return path[len(prefix):].lstrip("/")
    return path.lstrip("/")


def _dataset_relative_path(
    source: str,
    *,
    local_prefix: str | None,
    s3_prefixes: dict[str, str],
    s3_use_bucket: bool,
    http_prefixes: dict[str, str],
    http_use_host: bool,
) -> str:
    if is_s3_uri(source):
        parsed = urlparse(source)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        trimmed = _trim_prefix(key, s3_prefixes.get(bucket, ""))
        if s3_use_bucket and bucket:
            return f"{bucket}/{trimmed}" if trimmed else bucket
        return trimmed or extract_name(source)

    if is_http_url(source):
        parsed = urlparse(source)
        host = parsed.netloc
        path = parsed.path.lstrip("/")
        trimmed = _trim_prefix(path, http_prefixes.get(host, ""))
        if http_use_host and host:
            return f"{host}/{trimmed}" if trimmed else host
        return trimmed or extract_name(source)

    resolved = os.path.abspath(source)
    if local_prefix:
        try:
            relative = os.path.relpath(resolved, local_prefix)
            if not relative.startswith(".."):
                return relative
        except ValueError:
            pass
    return os.path.basename(resolved)


class DatasetStorage:
    """
    In-memory storage for programmatic datasets.
    Supports local file paths, S3 URIs, and HTTP/HTTPS URLs.
    """

    IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
    REMOTE_HEADER_BYTES = 65536
    REMOTE_DIM_WORKERS = 16
    REMOTE_DIM_WORKERS_MAX = 16

    def __init__(
        self,
        datasets: dict[str, list[str]],
        thumb_size: int = 256,
        thumb_quality: int = 70,
        include_source_in_search: bool = True,
    ):
        self.datasets = datasets
        self.thumb_size = thumb_size
        self.thumb_quality = thumb_quality
        self._include_source_in_search = include_source_in_search
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

        self._build_all_indexes()
        self._browse_signature = self._compute_browse_signature()

    def _compute_browse_signature(self) -> str:
        digest = hashlib.sha256()
        for dataset in sorted(self.datasets.keys()):
            digest.update(dataset.encode("utf-8"))
            for source in sorted(self.datasets[dataset]):
                digest.update(source.encode("utf-8"))
        return digest.hexdigest()

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
        normalized = normalize_item_path(path)
        return f"/{normalized}" if normalized else "/"

    def _canonical_meta_key(self, path: str) -> str:
        return canonical_meta_key(path)

    def _resolve_local_source(self, source: str) -> str:
        if not source:
            raise ValueError("empty path")
        return os.path.abspath(source)

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

    def _get_remote_header_bytes(
        self,
        url: str,
        max_bytes: int | None = None,
    ) -> tuple[bytes | None, int | None]:
        return get_remote_header_bytes(
            url,
            max_bytes=max_bytes or self.REMOTE_HEADER_BYTES,
            parse_content_range_fn=self._parse_content_range,
        )

    def _get_remote_header_info(
        self,
        url: str,
        name: str,
    ) -> tuple[tuple[int, int] | None, int | None]:
        return get_remote_header_info(
            url,
            name,
            max_bytes=self.REMOTE_HEADER_BYTES,
            read_dimensions_from_bytes=self._read_dimensions_from_bytes,
            get_remote_header_bytes_fn=self._get_remote_header_bytes,
        )

    def _read_dimensions_from_bytes(self, data: bytes, ext: str | None) -> tuple[int, int] | None:
        return read_dimensions_from_bytes(data, ext)

    def _probe_remote_dimensions(
        self,
        tasks: list[tuple[str, CachedItem, str, str]],
        label: str | None = None,
    ) -> None:
        _ = label
        probe_remote_dimensions(self, tasks)

    def _build_all_indexes(self) -> None:
        generated_at = datetime.now(timezone.utc).isoformat()
        total_sources = sum(len(paths) for paths in self.datasets.values())
        self._row_dimensions = [None] * total_sources

        rows: list[ScannedRow] = []
        remote_tasks: list[tuple[str, CachedItem, str, str]] = []
        row_idx = 0

        for dataset_name, raw_paths in self.datasets.items():
            sources: list[str] = []
            for raw in raw_paths:
                if isinstance(raw, os.PathLike):
                    raw = os.fspath(raw)
                if not isinstance(raw, str):
                    continue
                source = raw.strip()
                if source:
                    sources.append(source)

            local_prefix = _compute_dataset_local_prefix(sources)
            s3_prefixes, s3_use_bucket = _compute_dataset_s3_prefixes(sources)
            http_prefixes, http_use_host = _compute_dataset_http_prefixes(sources)
            seen_paths: set[str] = set()

            for source in sources:
                name = self._extract_name(source)
                if not self._is_supported_image(name):
                    continue

                relative_path = _dataset_relative_path(
                    source,
                    local_prefix=local_prefix,
                    s3_prefixes=s3_prefixes,
                    s3_use_bucket=s3_use_bucket,
                    http_prefixes=http_prefixes,
                    http_use_host=http_use_host,
                )
                logical_relative = normalize_item_path(f"{dataset_name}/{relative_path}")
                if not logical_relative:
                    continue

                logical_relative = dedupe_path(logical_relative, seen_paths)
                seen_paths.add(logical_relative)
                logical_path = self._normalize_item_path(logical_relative)

                is_s3 = self._is_s3_uri(source)
                is_http = self._is_http_url(source)
                url = source if is_http else None
                size = 0
                mtime = time.time()

                if not is_s3 and not is_http:
                    resolved = self._resolve_local_source(source)
                    if not os.path.exists(resolved):
                        print(f"[lenslet] Warning: File not found: {resolved}")
                        continue
                    try:
                        size = os.path.getsize(resolved)
                    except Exception:
                        size = 0
                    try:
                        mtime = os.path.getmtime(resolved)
                    except Exception:
                        mtime = time.time()

                item = CachedItem(
                    path=logical_path,
                    name=name,
                    mime=self._guess_mime(name),
                    width=0,
                    height=0,
                    size=size,
                    mtime=mtime,
                    url=url,
                )
                folder_norm = normalize_path(os.path.dirname(logical_path))
                rows.append(
                    ScannedRow(
                        row_idx=row_idx,
                        logical_path=logical_path,
                        source=source,
                        folder_norm=folder_norm,
                        item=item,
                        discovered_dims=None,
                    )
                )
                row_idx += 1

                if is_s3 or is_http:
                    remote_tasks.append((logical_path, item, source, name))

        self._row_dimensions = self._row_dimensions[:row_idx]
        assemble_indexes(
            self,
            rows,
            generated_at=generated_at,
            index_factory=CachedIndex,
        )

        root_index = self._indexes.setdefault(
            "",
            CachedIndex(path="/", generated_at=generated_at, items=[], dirs=[]),
        )
        root_dirs = set(root_index.dirs)
        for dataset_name in self.datasets:
            dataset_norm = normalize_path(dataset_name)
            self._indexes.setdefault(
                dataset_norm,
                CachedIndex(
                    path=f"/{dataset_norm}" if dataset_norm else "/",
                    generated_at=generated_at,
                    items=[],
                    dirs=[],
                ),
            )
            if dataset_norm:
                root_dirs.add(dataset_norm)
        root_index.dirs = sorted(root_dirs)

        if remote_tasks:
            self._probe_remote_dimensions(remote_tasks, "remote headers")

    def _progress(self, done: int, total: int, label: str) -> None:
        self._progress_bar.update(done, total, label)

    def indexing_progress(self) -> dict[str, int | str | bool | None]:
        return self._progress_bar.snapshot()

    def browse_generation(self) -> int:
        return 0

    def browse_cache_signature(self) -> str:
        return self._browse_signature

    def get_index(self, path: str) -> CachedIndex:
        norm = self._normalize_path(path)
        if norm in self._indexes:
            return self._indexes[norm]
        raise FileNotFoundError(f"Dataset not found: {path}")

    def validate_image_path(self, path: str) -> None:
        norm = self._normalize_item_path(path)
        if not path or norm not in self._items:
            raise FileNotFoundError(path)

    def get_source_path(self, logical_path: str) -> str:
        norm = self._normalize_item_path(logical_path)
        if norm not in self._source_paths:
            raise FileNotFoundError(logical_path)
        return self._source_paths[norm]

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
        return "/" + "/".join(p.strip("/") for p in parts if p.strip("/"))

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

    def get_metadata_readonly(self, path: str) -> dict:
        return storage_get_metadata_readonly(self, path)

    def set_metadata(self, path: str, meta: dict) -> None:
        storage_set_metadata(self, path, meta)

    def search(self, query: str = "", path: str = "/", limit: int = 100) -> list[CachedItem]:
        return storage_search_items(self, query=query, path=path, limit=limit)

    def _jpeg_dimensions(self, handle) -> tuple[int, int] | None:
        return read_jpeg_dimensions(handle)

    def _png_dimensions(self, handle) -> tuple[int, int] | None:
        return read_png_dimensions(handle)

    def _webp_dimensions(self, handle) -> tuple[int, int] | None:
        return read_webp_dimensions(handle)

    def _guess_mime(self, name: str) -> str:
        return storage_guess_mime(name)
