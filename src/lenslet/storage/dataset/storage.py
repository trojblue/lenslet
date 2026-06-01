"""In-memory dataset storage for programmatic API."""
from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..base import join_storage_path
from .paths import (
    DatasetSourcePrefixes,
    clean_dataset_sources,
    dataset_folder_norm,
    dataset_logical_relative_path,
    dataset_relative_path,
    dataset_source_prefixes,
)
from ..index_assembly import ScannedRow, assemble_indexes
from ..progress import ProgressBar
from ..source.backed import SourceBackedConfig, SourceBackedServices, SourceBackedStorageBase
from ..source.state import SourceBackedIndexState, SourceRowIndexState
from ..image_media import ImageMime, read_dimensions_from_bytes
from ..source.paths import (
    canonical_sidecar_key,
    dedupe_path,
    extract_name,
    is_http_url,
    is_s3_uri,
    is_supported_image,
    normalize_item_path,
    normalize_path,
)


@dataclass
class DatasetBrowseItem:
    """In-memory cached browse facts for an image."""

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


@dataclass
class DatasetBrowseIndex:
    """In-memory cached folder index."""

    path: str
    generated_at: str
    items: list[DatasetBrowseItem] = field(default_factory=list)
    dirs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _LocalSourceInfo:
    size: int
    mtime: float


@dataclass(frozen=True)
class _DatasetSourceRow:
    row: ScannedRow
    remote_task: tuple[str, DatasetBrowseItem, str, str] | None = None


def _local_source_info(storage: "DatasetStorage", source: str) -> _LocalSourceInfo | None:
    resolved = storage._resolve_local_source(source)
    if not os.path.exists(resolved):
        print(f"[lenslet] Warning: File not found: {resolved}")
        return None
    size = 0
    mtime = time.time()
    try:
        size = os.path.getsize(resolved)
    except OSError:
        size = 0
    try:
        mtime = os.path.getmtime(resolved)
    except OSError:
        mtime = time.time()
    return _LocalSourceInfo(size=size, mtime=mtime)


def _source_row(
    storage: "DatasetStorage",
    dataset_name: str,
    source: str,
    prefixes: DatasetSourcePrefixes,
    seen_paths: set[str],
    row_idx: int,
) -> _DatasetSourceRow | None:
    name = storage._extract_name(source)
    if not storage._is_supported_image(name):
        return None

    relative_path = dataset_relative_path(source, prefixes)
    logical_relative = dataset_logical_relative_path(dataset_name, relative_path)
    if not logical_relative:
        return None

    logical_relative = dedupe_path(logical_relative, seen_paths)
    seen_paths.add(logical_relative)
    logical_path = storage._normalize_item_path(logical_relative)

    is_s3 = storage._is_s3_uri(source)
    is_http = storage._is_http_url(source)
    url = source if is_http else None
    source_info = _LocalSourceInfo(size=0, mtime=time.time())
    if not is_s3 and not is_http:
        local_info = _local_source_info(storage, source)
        if local_info is None:
            return None
        source_info = local_info

    item = DatasetBrowseItem(
        path=logical_path,
        name=name,
        mime=storage._guess_mime(name),
        width=0,
        height=0,
        size=source_info.size,
        mtime=source_info.mtime,
        url=url,
        source=source,
    )
    row = ScannedRow(
        row_idx=row_idx,
        logical_path=logical_path,
        source=source,
        folder_norm=dataset_folder_norm(logical_path),
        item=item,
        discovered_dims=None,
    )
    remote_task = (logical_path, item, source, name) if is_s3 or is_http else None
    return _DatasetSourceRow(row=row, remote_task=remote_task)


def _scan_dataset_sources(
    storage: "DatasetStorage",
    dataset_name: str,
    raw_paths: list[str],
    row_idx: int,
) -> tuple[list[ScannedRow], list[tuple[str, DatasetBrowseItem, str, str]], int]:
    sources = clean_dataset_sources(raw_paths)
    prefixes = dataset_source_prefixes(sources)
    seen_paths: set[str] = set()
    rows: list[ScannedRow] = []
    remote_tasks: list[tuple[str, DatasetBrowseItem, str, str]] = []

    for source in sources:
        scanned = _source_row(storage, dataset_name, source, prefixes, seen_paths, row_idx)
        if scanned is None:
            continue
        rows.append(scanned.row)
        if scanned.remote_task is not None:
            remote_tasks.append(scanned.remote_task)
        row_idx += 1

    return rows, remote_tasks, row_idx


class DatasetStorage(SourceBackedStorageBase[DatasetBrowseItem]):
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
    _canonical_sidecar_key = staticmethod(canonical_sidecar_key)
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
            config=SourceBackedConfig(
                thumb_size=thumb_size,
                thumb_quality=thumb_quality,
                include_source_in_search=include_source_in_search,
                remote_header_bytes=self.REMOTE_HEADER_BYTES,
                remote_dim_workers=self.REMOTE_DIM_WORKERS,
                remote_dim_workers_max=self.REMOTE_DIM_WORKERS_MAX,
            ),
            services=SourceBackedServices(
                normalize_item_path=self._normalize_item_path,
                canonical_sidecar_key=canonical_sidecar_key,
                is_s3_uri=is_s3_uri,
                is_http_url=is_http_url,
                resolve_local_source=self._resolve_local_source,
                read_dimensions_from_bytes=read_dimensions_from_bytes,
                progress=self._progress,
            ),
        )
        self._progress_bar = ProgressBar()

        self._indexes: dict[str, DatasetBrowseIndex] = {}

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
        return self._media_reads.s3_client_creations

    def _build_all_indexes(self) -> None:
        generated_at = datetime.now(timezone.utc).isoformat()

        rows: list[ScannedRow] = []
        remote_tasks: list[tuple[str, DatasetBrowseItem, str, str]] = []
        row_idx = 0

        for dataset_name, raw_paths in self.datasets.items():
            dataset_rows, dataset_remote_tasks, row_idx = _scan_dataset_sources(
                self,
                dataset_name,
                raw_paths,
                row_idx,
            )
            rows.extend(dataset_rows)
            remote_tasks.extend(dataset_remote_tasks)

        index_result = assemble_indexes(
            rows,
            generated_at=generated_at,
            row_count=row_idx,
            index_factory=DatasetBrowseIndex,
        )
        self._indexes = index_result.indexes
        self._bind_source_state(
            SourceBackedIndexState(
                items=index_result.items,
                source_paths=index_result.source_paths,
                dimensions=index_result.dimensions,
            )
        )
        self._bind_row_index_state(
            SourceRowIndexState(
                row_dimensions=index_result.row_dimensions,
                path_to_row=index_result.path_to_row,
                row_to_path=index_result.row_to_path,
            )
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
                    path=self._normalize_item_path(dataset_norm),
                    generated_at=generated_at,
                    items=[],
                    dirs=[],
                ),
            )
            if dataset_norm:
                root_dirs.add(dataset_norm)
        root_index.dirs = sorted(root_dirs)

        if remote_tasks:
            self._probe_remote_dimensions(remote_tasks)

    def load_index(self, path: str) -> DatasetBrowseIndex | None:
        norm = self._normalize_path(path)
        if norm in self._indexes:
            return self._indexes[norm]
        return None

    def validate_image_path(self, path: str) -> None:
        norm = self._normalize_item_path(path)
        if not path or norm not in self._items:
            raise FileNotFoundError(path)

    def join(self, *parts: str) -> str:
        return join_storage_path(*parts)
