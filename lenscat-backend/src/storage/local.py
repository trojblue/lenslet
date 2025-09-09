"""Local filesystem storage backend."""
import os
from pathlib import Path
from typing import List, Optional, Tuple

import aiofiles
from PIL import Image

from ..models.types import DirEntry, DirKind, Item, MimeType
from .base import StorageBackend


class LocalStorage(StorageBackend):
    """Local filesystem storage implementation."""

    def __init__(self, root_path: str):
        """Initialize with root directory path."""
        self.root = Path(root_path).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, path: str) -> Path:
        """Resolve relative path to absolute path within root."""
        # Remove leading slash and resolve
        clean_path = path.lstrip("/")
        resolved = (self.root / clean_path).resolve()
        
        # Security check: ensure path is within root
        if not str(resolved).startswith(str(self.root)):
            raise ValueError(f"Path {path} is outside root directory")
        
        return resolved

    async def exists(self, path: str) -> bool:
        """Check if path exists."""
        try:
            return self._resolve_path(path).exists()
        except ValueError:
            return False

    async def read_bytes(self, path: str) -> bytes:
        """Read file as bytes."""
        file_path = self._resolve_path(path)
        async with aiofiles.open(file_path, "rb") as f:
            return await f.read()

    async def read_text(self, path: str) -> str:
        """Read file as text."""
        file_path = self._resolve_path(path)
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            return await f.read()

    async def write_bytes(self, path: str, data: bytes) -> None:
        """Write bytes to file."""
        file_path = self._resolve_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(data)

    async def write_text(self, path: str, content: str) -> None:
        """Write text to file."""
        file_path = self._resolve_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(content)

    async def list_directory(self, path: str) -> Tuple[List[DirEntry], List[Item]]:
        """List directory contents."""
        dir_path = self._resolve_path(path)
        if not dir_path.is_dir():
            return [], []

        dirs = []
        items = []
        
        for entry in dir_path.iterdir():
            if entry.is_dir():
                # Determine directory kind
                kind = DirKind.BRANCH
                if any(self._is_image_file(f) for f in entry.iterdir() if f.is_file()):
                    kind = DirKind.LEAF_REAL
                elif (entry / ".lenscat.folder.json").exists():
                    kind = DirKind.LEAF_POINTER
                
                dirs.append(DirEntry(name=entry.name, kind=kind))
            
            elif entry.is_file() and self._is_image_file(entry):
                # Get image info
                try:
                    info = await self.get_file_info(str(entry.relative_to(self.root)))
                    if info:
                        w, h, size = info
                        rel_path = str(entry.relative_to(self.root))
                        
                        # Check for sidecar and thumbnail
                        has_meta = (entry.parent / f"{entry.name}.json").exists()
                        has_thumb = (entry.parent / f"{entry.name}.thumbnail").exists()
                        
                        items.append(Item(
                            path=rel_path,
                            name=entry.name,
                            type=self._get_mime_type(entry),
                            w=w,
                            h=h,
                            size=size,
                            hasThumb=has_thumb,
                            hasMeta=has_meta
                        ))
                except Exception:
                    # Skip files we can't process
                    continue

        return dirs, items

    async def get_file_info(self, path: str) -> Optional[Tuple[int, int, int]]:
        """Get image file info: (width, height, size)."""
        try:
            file_path = self._resolve_path(path)
            if not file_path.exists() or not self._is_image_file(file_path):
                return None
            
            # Get file size
            size = file_path.stat().st_size
            
            # Get image dimensions
            with Image.open(file_path) as img:
                w, h = img.size
            
            return w, h, size
        except Exception:
            return None

    async def delete(self, path: str) -> None:
        """Delete file."""
        file_path = self._resolve_path(path)
        if file_path.exists():
            file_path.unlink()

    def get_public_url(self, path: str) -> str:
        """Get public URL for file access."""
        # For local storage, return a file:// URL or relative path
        return f"/api/files/{path.lstrip('/')}"

    async def health_check(self) -> dict:
        """Return storage health status."""
        return {
            "type": "local",
            "root_path": str(self.root),
            "writable": os.access(self.root, os.W_OK),
            "exists": self.root.exists(),
        }

    def _is_image_file(self, path: Path) -> bool:
        """Check if file is a supported image."""
        return path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}

    def _get_mime_type(self, path: Path) -> MimeType:
        """Get MIME type from file extension."""
        ext = path.suffix.lower()
        if ext in {".jpg", ".jpeg"}:
            return MimeType.JPEG
        elif ext == ".png":
            return MimeType.PNG
        elif ext == ".webp":
            return MimeType.WEBP
        else:
            return MimeType.JPEG  # fallback
