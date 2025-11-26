from __future__ import annotations
import os
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from PIL import Image
from .local import LocalStorage


@dataclass
class CachedItem:
    """In-memory cached metadata for an image."""
    path: str
    name: str
    mime: str
    width: int
    height: int
    size: int
    mtime: float
    thumbnail: bytes | None = None


@dataclass
class CachedIndex:
    """In-memory cached folder index."""
    path: str
    generated_at: str
    items: list[CachedItem] = field(default_factory=list)
    dirs: list[str] = field(default_factory=list)


class MemoryStorage:
    """
    In-memory storage that wraps LocalStorage for reading,
    but keeps all indexes, thumbnails, and metadata in RAM.
    Does NOT write anything to the source directory.
    """

    IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")

    def __init__(self, root: str, thumb_size: int = 256, thumb_quality: int = 70):
        self.local = LocalStorage(root)
        self.root = root
        self.thumb_size = thumb_size
        self.thumb_quality = thumb_quality

        # In-memory caches
        self._indexes: dict[str, CachedIndex] = {}
        self._thumbnails: dict[str, bytes] = {}  # path -> thumbnail bytes
        self._metadata: dict[str, dict] = {}  # path -> sidecar-like metadata

    def _normalize_path(self, path: str) -> str:
        """Normalize path for consistent cache keys."""
        return path.strip("/") if path else ""

    def list_dir(self, path: str) -> tuple[list[str], list[str]]:
        """List directory, filtering out metadata files."""
        files, dirs = self.local.list_dir(path)
        # Filter out any existing metadata files from the listing
        files = [
            f for f in files
            if not f.endswith(".json")
            and not f.endswith(".thumbnail")
            and not f.startswith("_")
        ]
        dirs = [d for d in dirs if not d.startswith("_")]
        return files, dirs

    def read_bytes(self, path: str) -> bytes:
        """Read file from disk (images only)."""
        return self.local.read_bytes(path)

    def write_bytes(self, path: str, data: bytes) -> None:
        """No-op - we don't write to source directory."""
        pass

    def exists(self, path: str) -> bool:
        """Check if file exists on disk."""
        return self.local.exists(path)

    def size(self, path: str) -> int:
        """Get file size."""
        return self.local.size(path)

    def join(self, *parts: str) -> str:
        return self.local.join(*parts)

    def etag(self, path: str) -> str | None:
        return self.local.etag(path)

    # --- In-memory index/thumbnail operations ---

    def get_index(self, path: str) -> CachedIndex | None:
        """Get cached index for a folder, building if needed."""
        norm = self._normalize_path(path)
        if norm in self._indexes:
            return self._indexes[norm]
        return self._build_index(path)

    def _build_index(self, path: str) -> CachedIndex:
        """Build and cache folder index."""
        norm = self._normalize_path(path)
        files, dirs = self.list_dir(path)

        items: list[CachedItem] = []
        for name in files:
            if not name.lower().endswith(self.IMAGE_EXTS):
                continue
            full = self.join(path, name)
            try:
                size = self.size(full)
                w, h = self._get_dimensions(full)
                mime = self._guess_mime(name)
                mtime = os.path.getmtime(
                    os.path.join(self.local._root_real, full.lstrip("/"))
                )
                items.append(CachedItem(
                    path=full, name=name, mime=mime,
                    width=w, height=h, size=size, mtime=mtime
                ))
            except Exception:
                continue

        index = CachedIndex(
            path=path,
            generated_at=datetime.now(timezone.utc).isoformat(),
            items=items,
            dirs=dirs,
        )
        self._indexes[norm] = index
        return index

    def _get_dimensions(self, path: str) -> tuple[int, int]:
        """Get image dimensions, using cache if available."""
        if path in self._metadata:
            meta = self._metadata[path]
            return meta.get("width", 0), meta.get("height", 0)

        try:
            raw = self.read_bytes(path)
            with Image.open(BytesIO(raw)) as im:
                w, h = im.size
                self._metadata[path] = {"width": w, "height": h}
                return w, h
        except Exception:
            return 0, 0

    def get_thumbnail(self, path: str) -> bytes | None:
        """Get thumbnail, generating if needed."""
        if path in self._thumbnails:
            return self._thumbnails[path]

        try:
            raw = self.read_bytes(path)
            thumb = self._make_thumbnail(raw)
            self._thumbnails[path] = thumb
            return thumb
        except Exception:
            return None

    def _make_thumbnail(self, img_bytes: bytes) -> bytes:
        """Generate a WebP thumbnail."""
        with Image.open(BytesIO(img_bytes)) as im:
            w, h = im.size
            short = min(w, h)
            if short > self.thumb_size:
                scale = self.thumb_size / short
                new_w = max(1, int(w * scale))
                new_h = max(1, int(h * scale))
                im = im.convert("RGB").resize((new_w, new_h), Image.LANCZOS)
            else:
                im = im.convert("RGB")
            out = BytesIO()
            im.save(out, format="WEBP", quality=self.thumb_quality, method=6)
            return out.getvalue()

    def get_metadata(self, path: str) -> dict:
        """Get metadata for an image (in-memory only)."""
        if path in self._metadata:
            return self._metadata[path]
        # Build minimal metadata
        w, h = self._get_dimensions(path)
        meta = {
            "width": w,
            "height": h,
            "tags": [],
            "notes": "",
            "star": None,
        }
        self._metadata[path] = meta
        return meta

    def set_metadata(self, path: str, meta: dict) -> None:
        """Update in-memory metadata (session-only, lost on restart)."""
        self._metadata[path] = meta

    def invalidate_cache(self, path: str | None = None) -> None:
        """Clear cached data. If path is None, clear everything."""
        if path is None:
            self._indexes.clear()
            self._thumbnails.clear()
            self._metadata.clear()
        else:
            norm = self._normalize_path(path)
            self._indexes.pop(norm, None)
            self._thumbnails.pop(path, None)
            self._metadata.pop(path, None)

    @staticmethod
    def _guess_mime(name: str) -> str:
        n = name.lower()
        if n.endswith(".webp"):
            return "image/webp"
        if n.endswith(".png"):
            return "image/png"
        return "image/jpeg"

