from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol


class StorageWriteUnsupportedError(PermissionError):
    """Raised when a storage backend does not support raw writes."""


class Storage(Protocol):
    """Abstract read-oriented storage protocol for file operations."""

    def list_dir(self, path: str) -> tuple[list[str], list[str]]:
        """Return (files, dirs) names in path (no recursion)."""
        ...

    def read_bytes(self, path: str) -> bytes:
        """Read file contents."""
        ...

    def exists(self, path: str) -> bool:
        """Check if path exists."""
        ...

    def size(self, path: str) -> int:
        """Get file size in bytes."""
        ...

    def join(self, *parts: str) -> str:
        """Join path parts."""
        ...

    def etag(self, path: str) -> str | None:
        """Get ETag for caching."""
        ...


class WritableStorage(Storage, Protocol):
    """Optional raw-write extension for storage backends."""

    def write_bytes(self, path: str, data: bytes) -> None:
        """Write file contents or raise StorageWriteUnsupportedError."""
        ...


class BrowseItem(Protocol):
    """Shared cached-item shape exposed by browse-capable backends."""

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


class BrowseIndex(Protocol):
    """Minimal folder-index contract shared by browse storage backends."""

    items: list[BrowseItem]
    dirs: list[str]


class BrowseStorage(Storage, Protocol):
    """Server-facing browse storage contract used by the runtime and routes."""

    def get_index(self, path: str) -> BrowseIndex | None:
        """Return a folder index, or None when the path is outside the browse tree."""
        ...

    def get_recursive_index(self, path: str) -> BrowseIndex | None:
        """Return the recursive-traversal index for a folder."""
        ...

    def items_in_scope(self, path: str) -> list[BrowseItem]:
        """Return all items beneath a logical scope."""
        ...

    def count_in_scope(self, path: str) -> int:
        """Return the total number of items beneath a logical scope."""
        ...

    def validate_image_path(self, path: str) -> None:
        """Raise when the path does not resolve to a valid image item."""
        ...

    def guess_mime(self, path: str) -> str:
        """Return the MIME type for the requested logical path."""
        ...

    def get_metadata_readonly(self, path: str) -> dict[str, Any]:
        """Return a detached metadata snapshot for the requested item."""
        ...

    def ensure_metadata(self, path: str) -> dict[str, Any]:
        """Return mutable metadata for the requested item, creating cache state when needed."""
        ...

    def set_metadata(self, path: str, meta: dict[str, Any]) -> None:
        """Replace metadata for the requested item."""
        ...

    def get_source_path(self, logical_path: str) -> str:
        """Return the backing source path/URL for a logical browse path."""
        ...

    def get_thumbnail(self, path: str) -> bytes | None:
        """Return or build the thumbnail bytes for the requested item."""
        ...

    def get_cached_thumbnail(self, path: str) -> bytes | None:
        """Return an in-memory thumbnail if present, without generating one."""
        ...

    def thumbnail_cache_key(self, path: str) -> str | None:
        """Return the shared thumbnail cache key for the requested item."""
        ...

    def resolve_local_file_path(self, path: str) -> str | None:
        """Return a local file path when the item is backed by a local file."""
        ...

    def metadata_items(self) -> list[tuple[str, dict[str, Any]]]:
        """Return storage metadata entries for persistence/export helpers."""
        ...

    def metadata_snapshot_for_paths(
        self,
        paths: Iterable[str],
    ) -> dict[str, dict[str, Any]]:
        """Return a canonicalized metadata snapshot limited to the supplied logical paths."""
        ...

    def replace_metadata(self, metadata: dict[str, dict[str, Any]]) -> None:
        """Replace storage metadata entries from a caller-owned snapshot."""
        ...

    def total_items(self) -> int:
        """Return the number of indexed browse items."""
        ...

    def row_index_for_path(self, path: str) -> int | None:
        """Return the row index backing a logical path, or None when unavailable."""
        ...

    def table_fields_for_path(self, path: str) -> dict[str, Any]:
        """Return displayable table fields for a logical path."""
        ...

    def indexing_progress(self) -> dict[str, int | str | bool | None]:
        """Return the current indexing progress snapshot."""
        ...

    def browse_generation(self) -> int:
        """Return the current browse generation token."""
        ...

    def browse_cache_signature(self) -> str:
        """Return the stable browse cache signature."""
        ...

    def recursive_items_hard_limit(self) -> int | None:
        """Return the hard limit for recursive browse expansion."""
        ...


class RefreshableBrowseStorage(BrowseStorage, Protocol):
    """Browse storage that can refresh a subtree in place."""

    def refresh_subtree(self, path: str, *, preserve_metadata: bool = True) -> None:
        """Refresh a folder subtree, optionally retaining mutable metadata."""
        ...


def join_storage_path(*parts: str) -> str:
    """Join logical browse paths into one rooted POSIX-style path."""

    joined = "/".join(part.strip("/") for part in parts if part and part.strip("/"))
    return f"/{joined}" if joined else "/"
