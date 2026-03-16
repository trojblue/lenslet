from __future__ import annotations

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
    """Browse-oriented storage contract used by the server/runtime layer."""

    def get_index(self, path: str) -> BrowseIndex | None:
        """Return a folder index, or None when the path is outside the browse tree."""
        ...

    def get_metadata_readonly(self, path: str) -> dict[str, Any]:
        """Return a detached metadata snapshot for the requested item."""
        ...

    def get_metadata(self, path: str) -> dict[str, Any]:
        """Return mutable metadata for the requested item."""
        ...

    def set_metadata(self, path: str, meta: dict[str, Any]) -> None:
        """Replace metadata for the requested item."""
        ...

    def get_source_path(self, logical_path: str) -> str:
        """Return the backing source path/URL for a logical browse path."""
        ...

    def get_cached_thumbnail(self, path: str) -> bytes | None:
        """Return an in-memory thumbnail if present, without generating one."""
        ...

    def resolve_local_file_path(self, path: str) -> str | None:
        """Return a local file path when the item is backed by a local file."""
        ...

    def metadata_items(self) -> list[tuple[str, dict[str, Any]]]:
        """Return storage metadata entries for persistence/export helpers."""
        ...

    def replace_metadata(self, metadata: dict[str, dict[str, Any]]) -> None:
        """Replace storage metadata entries from a caller-owned snapshot."""
        ...

    def total_items(self) -> int:
        """Return the number of indexed browse items."""
        ...


def join_storage_path(*parts: str) -> str:
    """Join logical browse paths into one rooted POSIX-style path."""

    joined = "/".join(part.strip("/") for part in parts if part and part.strip("/"))
    return f"/{joined}" if joined else "/"
