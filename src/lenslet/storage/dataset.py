"""In-memory dataset storage for programmatic API."""
from __future__ import annotations

import hashlib
import os
import posixpath
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from .base import join_storage_path
from .progress import ProgressBar
from .source_backed import SourceBackedStorageMixin
from .table_index import ScannedRow, assemble_indexes
from .table_media import read_dimensions_from_bytes
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
    probe_remote_dimensions,
)


@dataclass
class DatasetBrowseItem:
    """In-memory cached metadata for an image."""

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
class DatasetBrowseIndex:
    """In-memory cached folder index."""

    path: str
    generated_at: str
    items: list[DatasetBrowseItem] = field(default_factory=list)
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


class DatasetStorage(SourceBackedStorageMixin[DatasetBrowseItem]):
    """
    In-memory storage for programmatic datasets.
    Supports local file paths, S3 URIs, and HTTP/HTTPS URLs.
    """

    IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
    REMOTE_HEADER_BYTES = 65536
    REMOTE_DIM_WORKERS = 16
    REMOTE_DIM_WORKERS_MAX = 16
    _is_s3_uri = staticmethod(is_s3_uri)
    _is_http_url = staticmethod(is_http_url)
    _extract_name = staticmethod(extract_name)
    _normalize_path = staticmethod(normalize_path)
    _canonical_meta_key = staticmethod(canonical_meta_key)
    _read_dimensions_from_bytes = staticmethod(read_dimensions_from_bytes)

    def __init__(
        self,
        datasets: dict[str, list[str]],
        thumb_size: int = 256,
        thumb_quality: int = 70,
        include_source_in_search: bool = True,
    ):
        self.datasets = datasets
        self._initialize_source_backed_state(
            thumb_size=thumb_size,
            thumb_quality=thumb_quality,
            include_source_in_search=include_source_in_search,
        )
        self._progress_bar = ProgressBar()

        self._indexes: dict[str, DatasetBrowseIndex] = {}
        self._row_dimensions: list[tuple[int, int] | None] = []

        self._build_all_indexes()
        self._browse_signature = self._compute_browse_signature()

    def _compute_browse_signature(self) -> str:
        digest = hashlib.sha256()
        for dataset in sorted(self.datasets.keys()):
            digest.update(dataset.encode("utf-8"))
            for source in sorted(self.datasets[dataset]):
                digest.update(source.encode("utf-8"))
        return digest.hexdigest()

    def _is_supported_image(self, name: str) -> bool:
        return is_supported_image(name, self.IMAGE_EXTS)

    def _normalize_item_path(self, path: str) -> str:
        normalized = normalize_item_path(path)
        return f"/{normalized}" if normalized else "/"

    def _resolve_local_source(self, source: str) -> str:
        if not source:
            raise ValueError("empty path")
        return os.path.abspath(source)

    def s3_client_creations(self) -> int:
        return self._s3_client_creations

    def _probe_remote_dimensions(
        self,
        tasks: list[tuple[str, DatasetBrowseItem, str, str]],
        label: str | None = None,
    ) -> None:
        _ = label
        probe_remote_dimensions(self, tasks)

    def _build_all_indexes(self) -> None:
        generated_at = datetime.now(timezone.utc).isoformat()
        total_sources = sum(len(paths) for paths in self.datasets.values())
        self._row_dimensions = [None] * total_sources

        rows: list[ScannedRow] = []
        remote_tasks: list[tuple[str, DatasetBrowseItem, str, str]] = []
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

                item = DatasetBrowseItem(
                    path=logical_path,
                    name=name,
                    mime=self._guess_mime(name),
                    width=0,
                    height=0,
                    size=size,
                    mtime=mtime,
                    url=url,
                    source=source,
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
            index_factory=DatasetBrowseIndex,
        )

        root_index = self._indexes.setdefault(
            "",
            DatasetBrowseIndex(path="/", generated_at=generated_at, items=[], dirs=[]),
        )
        root_dirs = set(root_index.dirs)
        for dataset_name in self.datasets:
            dataset_norm = normalize_path(dataset_name)
            self._indexes.setdefault(
                dataset_norm,
                DatasetBrowseIndex(
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

    def get_index(self, path: str) -> DatasetBrowseIndex | None:
        norm = self._normalize_path(path)
        if norm in self._indexes:
            return self._indexes[norm]
        return None

    def row_index_for_path(self, path: str) -> int | None:
        norm = self._normalize_item_path(path)
        return self._path_to_row.get(norm)

    def validate_image_path(self, path: str) -> None:
        norm = self._normalize_item_path(path)
        if not path or norm not in self._items:
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
