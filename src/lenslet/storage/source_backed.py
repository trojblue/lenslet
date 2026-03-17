from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from io import BytesIO
import os
from threading import Lock
from typing import Any, Generic, Protocol, TypeVar
from urllib.parse import urlparse

from PIL import Image

from ..media_errors import MediaDecodeError, MediaReadError
from .s3 import S3_DEPENDENCY_ERROR, create_s3_client
from .search_text import build_search_haystack, normalize_search_path, path_in_scope
from .table_probe import effective_remote_workers, get_remote_header_bytes, get_remote_header_info, parse_content_range


class SourceBackedItem(Protocol):
    path: str
    name: str
    mime: str
    width: int
    height: int
    size: int
    mtime: float
    url: str | None
    source: str | None
    metrics: dict[str, float]


ItemT = TypeVar("ItemT", bound=SourceBackedItem)


def guess_mime(name: str) -> str:
    normalized = name.lower()
    if normalized.endswith(".webp"):
        return "image/webp"
    if normalized.endswith(".png"):
        return "image/png"
    return "image/jpeg"


class SourceBackedStorageMixin(Generic[ItemT], ABC):
    thumb_size: int
    thumb_quality: int
    REMOTE_HEADER_BYTES: int
    REMOTE_DIM_WORKERS: int
    REMOTE_DIM_WORKERS_MAX: int

    _include_source_in_search: bool
    _thumbnails: dict[str, bytes]
    _dimensions: dict[str, tuple[int, int]]
    _metadata: dict[str, dict[str, Any]]
    _items: dict[str, ItemT]
    _source_paths: dict[str, str]
    _s3_client_lock: Any
    _s3_session: Any | None
    _s3_client: Any | None
    _s3_client_creations: int

    def _initialize_source_backed_state(
        self,
        *,
        thumb_size: int,
        thumb_quality: int,
        include_source_in_search: bool,
    ) -> None:
        self.thumb_size = thumb_size
        self.thumb_quality = thumb_quality
        self._include_source_in_search = include_source_in_search
        self._items = {}
        self._thumbnails = {}
        self._metadata = {}
        self._dimensions = {}
        self._source_paths = {}
        self._row_dimensions = []
        self._path_to_row = {}
        self._row_to_path = {}
        self._s3_client_lock = Lock()
        self._s3_session = None
        self._s3_client = None
        self._s3_client_creations = 0

    @abstractmethod
    def _normalize_item_path(self, path: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def _canonical_meta_key(self, path: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def _resolve_local_source(self, source: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def _is_s3_uri(self, path: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def _is_http_url(self, path: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def _read_dimensions_from_bytes(
        self,
        data: bytes,
        ext: str | None,
    ) -> tuple[int, int] | None:
        raise NotImplementedError

    def _lookup_item(self, norm: str) -> ItemT | None:
        return self._items.get(norm)

    def _path_candidates(self, path: str) -> tuple[str, ...]:
        normalized = self._normalize_item_path(path)
        rooted = f"/{normalized.lstrip('/')}" if normalized else "/"
        candidates: list[str] = []
        for candidate in (path, normalized, path.lstrip("/"), rooted):
            if candidate and candidate not in candidates:
                candidates.append(candidate)
        return tuple(candidates)

    def _lookup_source_path(self, path: str) -> str | None:
        for candidate in self._path_candidates(path):
            source = self._source_paths.get(candidate)
            if source is not None:
                return source
        return None

    def guess_mime(self, name: str) -> str:
        return guess_mime(name)

    def _guess_mime(self, name: str) -> str:
        return self.guess_mime(name)

    def _make_thumbnail(self, img_bytes: bytes) -> tuple[bytes, tuple[int, int] | None]:
        with Image.open(BytesIO(img_bytes)) as image:
            width, height = image.size
            short_side = min(width, height)
            if short_side > self.thumb_size:
                scale = self.thumb_size / short_side
                resized_width = max(1, int(width * scale))
                resized_height = max(1, int(height * scale))
                image = image.convert("RGB").resize((resized_width, resized_height), Image.LANCZOS)
            else:
                image = image.convert("RGB")
            output = BytesIO()
            image.save(output, format="WEBP", quality=self.thumb_quality, method=6)
            return output.getvalue(), (width, height)

    def _effective_remote_workers(self, total: int) -> int:
        return effective_remote_workers(
            total,
            baseline_workers=self.REMOTE_DIM_WORKERS,
            max_workers=self.REMOTE_DIM_WORKERS_MAX,
            cpu_count=os.cpu_count,
        )

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

    def _get_s3_client(self):
        with self._s3_client_lock:
            if self._s3_client is not None:
                return self._s3_client
            self._s3_session, self._s3_client = create_s3_client()
            self._s3_client_creations += 1
            return self._s3_client

    def _get_presigned_url(self, s3_uri: str, expires_in: int = 3600) -> str:
        try:
            from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError(S3_DEPENDENCY_ERROR) from exc

        parsed = urlparse(s3_uri)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        if not bucket or not key:
            raise ValueError(f"Invalid S3 URI: {s3_uri}")

        try:
            s3_client = self._get_s3_client()
            return s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        except (BotoCoreError, ClientError, NoCredentialsError) as exc:
            raise RuntimeError(f"Failed to presign S3 URI: {exc}") from exc

    def read_bytes(self, path: str) -> bytes:
        norm = self._normalize_item_path(path)
        source = self._lookup_source_path(path)
        if source is None:
            raise FileNotFoundError(path)

        if self._is_s3_uri(source):
            import urllib.request

            try:
                url = self._get_presigned_url(source)
                with urllib.request.urlopen(url) as response:
                    return response.read()
            except Exception as exc:
                raise RuntimeError(f"Failed to download from S3: {exc}") from exc

        if self._is_http_url(source):
            import urllib.request

            try:
                with urllib.request.urlopen(source) as response:
                    return response.read()
            except Exception as exc:
                raise RuntimeError(f"Failed to download from URL: {exc}") from exc

        try:
            resolved = self._resolve_local_source(source)
        except ValueError as exc:
            raise FileNotFoundError(path) from exc
        with open(resolved, "rb") as handle:
            return handle.read()

    def get_thumbnail(self, path: str) -> bytes:
        norm = self._normalize_item_path(path)
        if norm in self._thumbnails:
            return self._thumbnails[norm]

        try:
            raw = self.read_bytes(norm)
        except FileNotFoundError:
            raise
        except Exception as exc:
            raise MediaReadError.from_exception(path, exc) from exc
        try:
            thumb, dims = self._make_thumbnail(raw)
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
        norm = self._normalize_item_path(path)
        if norm in self._dimensions:
            return self._dimensions[norm]

        item = self._lookup_item(norm)
        if item is None:
            raise FileNotFoundError(path)

        source = self._lookup_source_path(path)
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
            with Image.open(BytesIO(raw)) as image:
                width, height = image.size
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise MediaDecodeError.from_exception(path, exc) from exc
        except Exception as exc:
            raise MediaReadError.from_exception(path, exc) from exc

        dims = (width, height)
        self._dimensions[norm] = dims
        item.width = width
        item.height = height
        return dims

    def _default_metadata(self, norm: str) -> dict[str, Any]:
        width, height = self._dimensions.get(norm, (0, 0))
        item = self._lookup_item(norm)
        if item is not None and (width == 0 or height == 0):
            width, height = item.width, item.height
        return {
            "width": width,
            "height": height,
            "tags": [],
            "notes": "",
            "star": None,
            "version": 1,
            "updated_at": "",
            "updated_by": "server",
        }

    def get_source_path(self, logical_path: str) -> str:
        source = self._lookup_source_path(logical_path)
        if source is None:
            raise FileNotFoundError(logical_path)
        return source

    def get_cached_thumbnail(self, path: str) -> bytes | None:
        for candidate in self._path_candidates(path):
            thumb = self._thumbnails.get(candidate)
            if thumb is not None:
                return thumb
        return None

    def get_recursive_index(self, path: str):
        return self.get_index(path)

    def thumbnail_cache_key(self, path: str) -> str | None:
        try:
            source = self.get_source_path(path)
        except FileNotFoundError:
            return None
        parts = [source, str(self.thumb_size), str(self.thumb_quality)]
        if not (self._is_s3_uri(source) or self._is_http_url(source)):
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
        if self._is_s3_uri(source) or self._is_http_url(source):
            return None
        try:
            return self._resolve_local_source(source)
        except ValueError:
            return None

    def metadata_items(self) -> list[tuple[str, dict[str, Any]]]:
        return list(self._metadata.items())

    def metadata_snapshot_for_paths(
        self,
        paths: Iterable[str],
    ) -> dict[str, dict[str, Any]]:
        snapshot: dict[str, dict[str, Any]] = {}
        for path in paths:
            norm = self._normalize_item_path(path)
            key = self._canonical_meta_key(norm)
            meta = self._metadata.get(key)
            if meta is not None:
                snapshot[key] = dict(meta)
        return snapshot

    def replace_metadata(self, metadata: dict[str, dict[str, Any]]) -> None:
        self._metadata = {
            self._canonical_meta_key(path): dict(meta)
            for path, meta in metadata.items()
        }

    def total_items(self) -> int:
        return len(self._items)

    def items_in_scope(self, path: str) -> list[ItemT]:
        scope_norm = normalize_search_path(path)
        return [
            item
            for item in self._items.values()
            if path_in_scope(logical_path=item.path, scope_norm=scope_norm)
        ]

    def count_in_scope(self, path: str) -> int:
        scope_norm = normalize_search_path(path)
        return sum(
            1
            for item in self._items.values()
            if path_in_scope(logical_path=item.path, scope_norm=scope_norm)
        )

    def row_index_for_path(self, path: str) -> int | None:
        _ = path
        return None

    def sidecar_enrichment_for_path(self, path: str) -> dict[str, Any]:
        _ = path
        return {}

    def recursive_items_hard_limit(self) -> int | None:
        return None

    def get_metadata_readonly(self, path: str) -> dict[str, Any]:
        norm = self._normalize_item_path(path)
        key = self._canonical_meta_key(norm)
        meta = self._metadata.get(key)
        if meta is not None:
            return dict(meta)
        return self._default_metadata(norm)

    def ensure_metadata(self, path: str) -> dict[str, Any]:
        norm = self._normalize_item_path(path)
        key = self._canonical_meta_key(norm)
        meta = self._metadata.get(key)
        if meta is None:
            meta = self.get_metadata_readonly(path)
            self._metadata[key] = meta
        return meta

    def set_metadata(self, path: str, meta: dict[str, Any]) -> None:
        norm = self._normalize_item_path(path)
        key = self._canonical_meta_key(norm)
        self._metadata[key] = dict(meta)

    def search(self, query: str = "", path: str = "/", limit: int = 100) -> list[ItemT]:
        needle = (query or "").lower()
        scope_norm = normalize_search_path(path)
        results: list[ItemT] = []

        for item in self._items.values():
            if not path_in_scope(logical_path=item.path, scope_norm=scope_norm):
                continue
            meta = self.get_metadata_readonly(item.path)
            source = None
            if self._include_source_in_search:
                source = getattr(item, "source", None) or self._source_paths.get(item.path)
            haystack = build_search_haystack(
                logical_path=item.path,
                name=item.name,
                tags=meta.get("tags", []),
                notes=meta.get("notes", ""),
                source=source,
                url=item.url,
                include_source_fields=self._include_source_in_search,
            )
            if needle in haystack:
                results.append(item)
                if len(results) >= limit:
                    break
        return results
