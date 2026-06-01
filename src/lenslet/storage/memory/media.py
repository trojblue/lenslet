from __future__ import annotations

from collections.abc import Callable
from io import BytesIO

from PIL import Image

from ...media_errors import MediaDecodeError, MediaReadError
from ..image_media import ImageMime, guess_image_mime, make_webp_thumbnail, read_dimensions_fast


class MemoryMediaMixin:
    _abs_path: Callable[[str], str]
    _cache_item_key: Callable[[str], str]
    thumb_quality: int
    thumb_size: int
    _dimensions: dict[str, tuple[int, int]]
    _load_dimensions_fast: Callable[[str], tuple[int, int] | None]
    _read_dimensions_fast: Callable[[str], tuple[int, int] | None]
    _thumbnails: dict[str, bytes]
    etag: Callable[[str], str | None]
    get_cached_thumbnail: Callable[[str], bytes | None]
    get_source_path: Callable[[str], str]
    read_bytes: Callable[[str], bytes]
    resolve_local_file_path: Callable[[str], str | None]

    def _abs_path(self, path: str) -> str:
        raise NotImplementedError

    def _cache_item_key(self, path: str) -> str:
        raise NotImplementedError

    def etag(self, path: str) -> str | None:
        raise NotImplementedError

    def get_source_path(self, logical_path: str) -> str:
        raise NotImplementedError

    def read_bytes(self, path: str) -> bytes:
        raise NotImplementedError

    def get_dimensions(self, path: str) -> tuple[int, int]:
        key = self._cache_item_key(path)
        return self._dimensions.get(key, (0, 0))

    def load_dimensions(self, path: str) -> tuple[int, int]:
        """Load image dimensions and update dimension cache state."""
        key = self._cache_item_key(path)
        if key in self._dimensions:
            return self._dimensions[key]

        dims = self._load_dimensions_fast(path)
        if dims:
            self._dimensions[key] = dims
            return dims

        try:
            raw = self.read_bytes(path)
        except FileNotFoundError:
            raise
        except (OSError, ValueError) as exc:
            raise MediaReadError.from_exception(path, exc) from exc

        try:
            with Image.open(BytesIO(raw)) as im:
                width, height = im.size
        except (OSError, ValueError) as exc:
            raise MediaDecodeError.from_exception(path, exc) from exc
        self._dimensions[key] = (width, height)
        return width, height

    def _load_dimensions_fast(self, path: str) -> tuple[int, int] | None:
        try:
            abs_path = self._abs_path(path)
            return self._read_dimensions_fast(abs_path)
        except (OSError, ValueError):
            return None

    def _read_dimensions_fast(self, filepath: str) -> tuple[int, int] | None:
        return read_dimensions_fast(filepath)

    def get_or_build_thumbnail(self, path: str) -> bytes:
        """Return thumbnail bytes, reading source data and updating caches when needed."""
        cached = self.get_cached_thumbnail(path)
        if cached is not None:
            return cached

        try:
            raw = self.read_bytes(path)
        except FileNotFoundError:
            raise
        except (OSError, ValueError) as exc:
            raise MediaReadError.from_exception(path, exc) from exc

        try:
            thumb, dims = make_webp_thumbnail(
                raw,
                thumb_size=self.thumb_size,
                thumb_quality=self.thumb_quality,
            )
        except (OSError, ValueError) as exc:
            raise MediaDecodeError.from_exception(path, exc) from exc

        key = self._cache_item_key(path)
        self._thumbnails[key] = thumb
        if dims:
            self._dimensions[key] = dims
        return thumb

    def get_cached_thumbnail(self, path: str) -> bytes | None:
        key = self._cache_item_key(path)
        return self._thumbnails.get(key)

    def thumbnail_cache_key(self, path: str) -> str | None:
        source = self.resolve_local_file_path(path)
        if not source:
            return None
        parts = [source, str(self.thumb_size), str(self.thumb_quality)]
        try:
            etag = self.etag(path)
        except (OSError, ValueError):
            etag = None
        if etag:
            parts.append(str(etag))
        return "|".join(parts)

    def resolve_local_file_path(self, path: str) -> str | None:
        try:
            return self._abs_path(self.get_source_path(path))
        except (FileNotFoundError, ValueError):
            return None

    @staticmethod
    def guess_mime(name: str) -> ImageMime:
        return guess_image_mime(name)
