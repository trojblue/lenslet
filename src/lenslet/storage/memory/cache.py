from __future__ import annotations

from collections.abc import Callable
from typing import Any


class MemoryCacheInvalidationMixin:
    _bump_browse_generation: Callable[[], None]
    _cache_item_key: Callable[[str], str]
    _canonical_sidecar_key: Callable[[str], str]
    _dimensions: dict[str, tuple[int, int]]
    _drop_folder_indexes_for_subtree: Callable[[str], None]
    _drop_item_caches_for_subtree: Callable[..., None]
    _indexes: dict[str, Any]
    _item_key_in_subtree: Callable[[str, str], bool]
    _leaf_batch: Any
    _sidecars: dict[str, dict[str, Any]]
    _normalize_path: Callable[[str], str]
    _recursive_indexes: dict[str, Any]
    _thumbnails: dict[str, bytes]

    def _bump_browse_generation(self) -> None:
        raise NotImplementedError

    def _cache_item_key(self, path: str) -> str:
        raise NotImplementedError

    def _canonical_sidecar_key(self, path: str) -> str:
        raise NotImplementedError

    def _normalize_path(self, path: str) -> str:
        raise NotImplementedError

    def invalidate_cache(self, path: str | None = None) -> None:
        """Clear cached data. If path is None, clear everything."""
        self._bump_browse_generation()
        if path is None:
            self._leaf_batch.clear()
            self._indexes.clear()
            self._recursive_indexes.clear()
            self._thumbnails.clear()
            self._sidecars.clear()
            self._dimensions.clear()
            return

        norm = self._normalize_path(path)
        self._indexes.pop(norm, None)
        self._recursive_indexes.pop(norm, None)
        cache_key = self._cache_item_key(path)
        self._thumbnails.pop(cache_key, None)
        self._sidecars.pop(self._canonical_sidecar_key(path), None)
        self._dimensions.pop(cache_key, None)

    def _drop_folder_indexes_for_subtree(self, norm: str) -> None:
        if not norm:
            self._indexes.clear()
            self._recursive_indexes.clear()
            return

        prefix = f"{norm}/"
        for cache in (self._indexes, self._recursive_indexes):
            for key in list(cache.keys()):
                if key == norm or key.startswith(prefix):
                    cache.pop(key, None)

    def _item_key_in_subtree(self, item_path: str, canonical: str) -> bool:
        candidate = self._canonical_sidecar_key(item_path)
        if canonical == "/":
            return True
        return candidate == canonical or candidate.startswith(canonical + "/")

    def _drop_item_caches_for_subtree(self, canonical: str, *, clear_sidecars: bool) -> None:
        for cache in (self._thumbnails, self._dimensions):
            for key in list(cache.keys()):
                if self._item_key_in_subtree(key, canonical):
                    cache.pop(key, None)
        if clear_sidecars:
            for key in list(self._sidecars.keys()):
                if self._item_key_in_subtree(key, canonical):
                    self._sidecars.pop(key, None)

    def invalidate_subtree(self, path: str, clear_sidecars: bool = True) -> None:
        """Drop cached entries for a folder subtree.

        By default, sidecars are cleared too. For refresh flows, callers can pass
        clear_sidecars=False to preserve in-memory annotations while rebuilding
        folder indexes and thumbnails.
        """
        self._bump_browse_generation()
        norm = self._normalize_path(path)
        self._leaf_batch.clear()
        self._drop_folder_indexes_for_subtree(norm)
        self._drop_item_caches_for_subtree(self._canonical_sidecar_key(path), clear_sidecars=clear_sidecars)
