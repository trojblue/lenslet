"""Abstract storage interface."""
from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Optional, Tuple

from ..models.types import DirEntry, Item


class StorageBackend(ABC):
    """Abstract storage backend interface."""

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check if path exists."""
        pass

    @abstractmethod
    async def read_bytes(self, path: str) -> bytes:
        """Read file as bytes."""
        pass

    @abstractmethod
    async def read_text(self, path: str) -> str:
        """Read file as text."""
        pass

    @abstractmethod
    async def write_bytes(self, path: str, data: bytes) -> None:
        """Write bytes to file."""
        pass

    @abstractmethod
    async def write_text(self, path: str, content: str) -> None:
        """Write text to file."""
        pass

    @abstractmethod
    async def list_directory(self, path: str) -> Tuple[List[DirEntry], List[Item]]:
        """List directory contents, returns (dirs, items)."""
        pass

    @abstractmethod
    async def get_file_info(self, path: str) -> Optional[Tuple[int, int, int]]:
        """Get file info: (width, height, size) or None if not found."""
        pass

    @abstractmethod
    async def delete(self, path: str) -> None:
        """Delete file."""
        pass

    @abstractmethod
    def get_public_url(self, path: str) -> str:
        """Get public URL for file access."""
        pass

    @abstractmethod
    async def health_check(self) -> dict:
        """Return storage backend health status."""
        pass
