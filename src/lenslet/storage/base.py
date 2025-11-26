from __future__ import annotations
from typing import Protocol


class Storage(Protocol):
    """Abstract storage protocol for file operations."""

    def list_dir(self, path: str) -> tuple[list[str], list[str]]:
        """Return (files, dirs) names in path (no recursion)."""
        ...

    def read_bytes(self, path: str) -> bytes:
        """Read file contents."""
        ...

    def write_bytes(self, path: str, data: bytes) -> None:
        """Write file contents."""
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

