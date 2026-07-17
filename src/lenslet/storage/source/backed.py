from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
import os
from typing import Any, Generic

from ...media_errors import MediaDecodeError, MediaReadError
from ..sidecar_state import SidecarStateMixin, copy_sidecar_state, default_sidecar_state
from ..progress_state import StorageProgressMixin
from ..search_text import build_search_haystack
from .catalog import SourceCatalog
from .media import MediaReadService
from .state import ItemT, SourceBackedIndexState, SourceRowIndexState
from .probe import (
    RemoteDimensionProbeContext,
    effective_remote_workers,
    probe_remote_dimensions,
)
from ..base import BrowseIndex, SidecarState
from ..image_media import ImageMime, guess_image_mime, make_webp_thumbnail


def guess_mime(name: str) -> ImageMime:
    return guess_image_mime(name)


@dataclass(frozen=True, slots=True)
class SourceBackedConfig:
    thumb_size: int
    thumb_quality: int
    include_source_in_search: bool
    remote_header_bytes: int
    remote_dim_workers: int
    remote_dim_workers_max: int


@dataclass(frozen=True, slots=True)
class SourceBackedServices:
    normalize_item_path: Callable[[str], str]
    canonical_sidecar_key: Callable[[str], str]
    is_s3_uri: Callable[[str], bool]
    is_http_url: Callable[[str], bool]
    resolve_local_source: Callable[[str], str]
    read_dimensions_from_bytes: Callable[[bytes, str | None], tuple[int, int] | None]
    progress: Callable[[int, int, str], None]


class SourceBackedStorageBase(SidecarStateMixin, StorageProgressMixin, Generic[ItemT]):
    thumb_size: int
    thumb_quality: int

    _source_config: SourceBackedConfig
    _source_services: SourceBackedServices
    _include_source_in_search: bool
    _thumbnails: dict[str, bytes]
    _source_catalog: SourceCatalog[ItemT]
    _media_reads: MediaReadService
    _index_state: SourceBackedIndexState[ItemT]
    _row_index_state: SourceRowIndexState | None
    _items: dict[str, ItemT]
    _source_paths: dict[str, str]
    _row_dimensions: list[tuple[int, int] | None]
    _path_to_row: dict[str, int]
    _row_to_path: dict[int, str] | list[str | None]
    _dimensions: dict[str, tuple[int, int]]
    _sidecars: dict[str, SidecarState]
    _normalize_source_item_path: Callable[[str], str]
    _canonical_source_sidecar_key: Callable[[str], str]
    _source_is_s3_uri: Callable[[str], bool]
    _source_is_http_url: Callable[[str], bool]
    _progress_bar: Any
    _browse_signature: str

    def _initialize_source_backed_state(
        self,
        *,
        config: SourceBackedConfig,
        services: SourceBackedServices,
    ) -> None:
        self._source_config = config
        self._source_services = services
        self.thumb_size = config.thumb_size
        self.thumb_quality = config.thumb_quality
        self._include_source_in_search = config.include_source_in_search
        self._normalize_source_item_path = services.normalize_item_path
        self._canonical_source_sidecar_key = services.canonical_sidecar_key
        self._source_is_s3_uri = services.is_s3_uri
        self._source_is_http_url = services.is_http_url
        self._source_catalog = SourceCatalog(
            SourceBackedIndexState(),
            normalize_item_path=self._normalize_source_item_path,
        )
        self._bind_source_state(self._source_catalog.state)
        self._row_index_state = None
        self._thumbnails = {}
        self._sidecars = {}
        self._media_reads = MediaReadService(
            remote_header_bytes=config.remote_header_bytes,
            resolve_local_source=services.resolve_local_source,
            is_s3_uri=self._source_is_s3_uri,
            is_http_url=self._source_is_http_url,
            read_dimensions_from_bytes=services.read_dimensions_from_bytes,
        )

    def _bind_source_state(self, state: SourceBackedIndexState[ItemT]) -> None:
        self._source_catalog.bind(state)
        self._index_state = state
        self._items = state.items
        self._source_paths = state.source_paths
        self._dimensions = state.dimensions

    def _bind_row_index_state(self, state: SourceRowIndexState) -> None:
        self._row_index_state = state
        self._row_dimensions = state.row_dimensions
        self._path_to_row = state.path_to_row
        self._row_to_path = state.row_to_path

    def _lookup_item(self, norm: str) -> ItemT | None:
        return self._source_catalog.lookup_item(norm)

    def get_browse_item(self, path: str) -> ItemT:
        item = self._lookup_item(path)
        if item is None:
            raise FileNotFoundError(path)
        return item

    def _path_candidates(self, path: str) -> tuple[str, ...]:
        return self._source_catalog.path_candidates(path)

    def _lookup_source_path(self, path: str) -> str | None:
        return self._source_catalog.lookup_source_path(path)

    def guess_mime(self, name: str) -> ImageMime:
        return guess_mime(name)

    def _guess_mime(self, name: str) -> ImageMime:
        return self.guess_mime(name)

    def _effective_remote_workers(self, total: int) -> int:
        return effective_remote_workers(
            total,
            baseline_workers=self._source_config.remote_dim_workers,
            max_workers=self._source_config.remote_dim_workers_max,
            cpu_count=os.cpu_count,
        )

    def _remote_dimension_probe_context(self) -> RemoteDimensionProbeContext:
        return RemoteDimensionProbeContext(
            effective_remote_workers=self._effective_remote_workers,
            is_s3_uri=self._source_is_s3_uri,
            get_presigned_url=self._get_presigned_url,
            get_remote_header_info=self._get_remote_header_info,
            progress=self._source_services.progress,
        )

    def _probe_remote_dimensions(
        self,
        tasks: list[tuple[str, ItemT, str, str]],
    ) -> None:
        probe_remote_dimensions(
            self._remote_dimension_probe_context(),
            self._index_state,
            self._row_index_state,
            tasks,
        )

    def _get_remote_header_info(
        self,
        url: str,
        name: str,
    ) -> tuple[tuple[int, int] | None, int | None]:
        return self._media_reads.get_remote_header_info(url, name)

    def _get_safe_remote_header_info(
        self,
        url: str,
        name: str,
    ) -> tuple[tuple[int, int] | None, int | None]:
        return self._media_reads.get_safe_remote_header_info(url, name)

    def _get_presigned_url(self, s3_uri: str, expires_in: int = 3600) -> str:
        return self._media_reads.get_presigned_url(s3_uri, expires_in=expires_in)

    def remote_access_url(self, source: str) -> str | None:
        return self._media_reads.remote_access_url(source)

    def browse_generation(self) -> int:
        return 0

    def read_bytes(self, path: str) -> bytes:
        source = self._lookup_source_path(path)
        if source is None:
            raise FileNotFoundError(path)
        return self._media_reads.read_bytes(path, source)

    def open_remote_media_stream(self, path: str, *, range_header: str | None = None):
        source = self._lookup_source_path(path)
        if source is None:
            raise FileNotFoundError(path)
        return self._media_reads.open_remote_stream(path, source, range_header=range_header)

    def exists(self, path: str) -> bool:
        norm = self._normalize_source_item_path(path)
        return norm in self._items

    def size(self, path: str) -> int:
        norm = self._normalize_source_item_path(path)
        item = self._items.get(norm)
        if item is None:
            raise FileNotFoundError(path)
        return item.size

    def etag(self, path: str) -> str | None:
        norm = self._normalize_source_item_path(path)
        item = self._items.get(norm)
        if not item:
            return None
        return f"{int(item.mtime)}-{item.size}"

    def get_or_build_thumbnail(self, path: str) -> bytes:
        norm = self._normalize_source_item_path(path)
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
            self._dimensions[norm] = dims
            item = self._lookup_item(norm)
            if item is not None:
                item.width, item.height = dims
        return thumb

    def get_dimensions(self, path: str) -> tuple[int, int]:
        norm = self._normalize_source_item_path(path)
        if norm in self._dimensions:
            return self._dimensions[norm]

        item = self._lookup_item(norm)
        if item is None:
            raise FileNotFoundError(path)
        return item.width, item.height

    def load_dimensions(self, path: str) -> tuple[int, int]:
        norm = self._normalize_source_item_path(path)
        if norm in self._dimensions:
            return self._dimensions[norm]

        item = self._lookup_item(norm)
        if item is None:
            raise FileNotFoundError(path)
        if item.width > 0 and item.height > 0:
            dims = (item.width, item.height)
            self._dimensions[norm] = dims
            return dims

        source = self._lookup_source_path(path)
        if source and (self._source_is_s3_uri(source) or self._source_is_http_url(source)):
            dims, total = self._media_reads.remote_header_info(source, item.name)
            if total:
                item.size = total
            if dims:
                self._dimensions[norm] = dims
                item.width, item.height = dims
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
                width, height = image.size
        except (OSError, ValueError) as exc:
            raise MediaDecodeError.from_exception(path, exc) from exc

        dims = (width, height)
        self._dimensions[norm] = dims
        item.width = width
        item.height = height
        return dims

    def _default_sidecar(self, norm: str) -> SidecarState:
        width, height = self._dimensions.get(norm, (0, 0))
        item = self._lookup_item(norm)
        if item is not None and (width == 0 or height == 0):
            width, height = item.width, item.height
        return default_sidecar_state(width=width, height=height)

    def get_source_path(self, logical_path: str) -> str:
        return self._source_catalog.source_for_path(logical_path)

    def get_cached_thumbnail(self, path: str) -> bytes | None:
        for candidate in self._path_candidates(path):
            thumb = self._thumbnails.get(candidate)
            if thumb is not None:
                return thumb
        return None

    def load_recursive_index(self, path: str) -> BrowseIndex | None:
        return self.load_index(path)

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

    def _sidecar_snapshot_key(self, path: str) -> str:
        norm = self._normalize_source_item_path(path)
        return self._canonical_source_sidecar_key(norm)

    def _sidecar_replace_key(self, path: str) -> str:
        return self._canonical_source_sidecar_key(path)

    def total_items(self) -> int:
        return self._source_catalog.total_items()

    def items_in_scope(self, path: str) -> list[ItemT]:
        return self._source_catalog.items_in_scope(path)

    def count_in_scope(self, path: str) -> int:
        return self._source_catalog.count_in_scope(path)

    def row_index_for_path(self, path: str) -> int | None:
        if self._row_index_state is None:
            return None
        norm = self._normalize_source_item_path(path)
        row_idx = self._path_to_row.get(norm)
        if row_idx is not None:
            return row_idx
        item = self._items.get(norm)
        item_row_idx = getattr(item, "row_idx", None)
        if isinstance(item_row_idx, int) and item_row_idx >= 0:
            return item_row_idx
        return None

    def sidecar_enrichment_for_path(self, path: str) -> dict[str, Any]:
        _ = path
        return {}

    def recursive_items_hard_limit(self) -> int | None:
        return None

    def get_sidecar_readonly(self, path: str) -> SidecarState:
        norm = self._normalize_source_item_path(path)
        key = self._canonical_source_sidecar_key(norm)
        sidecar = self._sidecars.get(key)
        if sidecar is not None:
            return copy_sidecar_state(sidecar)
        return self._default_sidecar(norm)

    def ensure_sidecar(self, path: str) -> SidecarState:
        norm = self._normalize_source_item_path(path)
        key = self._canonical_source_sidecar_key(norm)
        sidecar = self._sidecars.get(key)
        if sidecar is None:
            sidecar = self.get_sidecar_readonly(path)
            self._sidecars[key] = sidecar
        return sidecar

    def set_sidecar(self, path: str, sidecar: SidecarState) -> None:
        norm = self._normalize_source_item_path(path)
        key = self._canonical_source_sidecar_key(norm)
        self._sidecars[key] = copy_sidecar_state(sidecar)

    def search(self, query: str = "", path: str = "/", limit: int = 100) -> list[ItemT]:
        needle = (query or "").lower()
        results: list[ItemT] = []

        for item in self._source_catalog.items_in_scope(path):
            sidecar_state = self.get_sidecar_readonly(item.path)
            source = None
            if self._include_source_in_search:
                source = getattr(item, "source", None) or self._source_paths.get(item.path)
            haystack = build_search_haystack(
                logical_path=item.path,
                name=item.name,
                tags=sidecar_state.get("tags", []),
                notes=sidecar_state.get("notes", ""),
                source=source,
                url=item.url,
                include_source_fields=self._include_source_in_search,
            )
            if needle in haystack:
                results.append(item)
                if len(results) >= limit:
                    break
        return results
