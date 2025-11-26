from __future__ import annotations
import os
import struct
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
    width: int  # 0 = not yet loaded
    height: int  # 0 = not yet loaded
    size: int
    mtime: float


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
        self._dimensions: dict[str, tuple[int, int]] = {}  # path -> (w, h)

    def _normalize_path(self, path: str) -> str:
        """Normalize path for consistent cache keys."""
        return path.strip("/") if path else ""

    def _abs_path(self, path: str) -> str:
        """Fast, safe absolute path resolution via LocalStorage."""
        return self.local.resolve_path(path)

    def _is_supported_image(self, name: str) -> bool:
        return name.lower().endswith(self.IMAGE_EXTS)

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

    def validate_image_path(self, path: str) -> None:
        """Ensure path is a supported image and exists on disk."""
        if not path:
            raise ValueError("empty path")
        if not self._is_supported_image(path):
            raise ValueError("unsupported file type")
        # Resolve to catch traversal attempts even if file is missing
        self._abs_path(path)
        if not self.exists(path):
            raise FileNotFoundError(path)

    def _build_index(self, path: str) -> CachedIndex:
        """Build and cache folder index. Fast - no image reading."""
        norm = self._normalize_path(path)
        files, dirs = self.list_dir(path)

        items: list[CachedItem] = []
        image_files = [f for f in files if self._is_supported_image(f)]
        
        # Log progress for large directories
        total = len(image_files)
        if total > 1000:
            print(f"[lenslet] Indexing {total} images in {path or '/'} ...")

        for i, name in enumerate(image_files):
            full = self.join(path, name)
            try:
                abs_path = self._abs_path(full)
                stat = os.stat(abs_path)
                size = stat.st_size
                mtime = stat.st_mtime
                mime = self._guess_mime(name)

                # Dimensions are loaded lazily (0 = not loaded yet)
                # Try to get from cache first, but if 0/0, try fast read if small enough or requested?
                # For now, we keep it 0/0 to be lazy as requested.
                # The frontend handles 0/0 gracefully or triggers a fetch if needed.
                w, h = self._dimensions.get(full, (0, 0))
                
                # If missing dimensions, try fast header read immediately
                # This makes "lazy" loading actually eager but lightweight (header only)
                # which is critical for adaptive layout to work on first load.
                if w == 0 or h == 0:
                    try:
                        dims = self._read_dimensions_fast(abs_path)
                        if dims:
                            w, h = dims
                            self._dimensions[full] = (w, h)
                    except Exception:
                        pass  # Keep as 0,0 if failed

                items.append(CachedItem(
                    path=full, name=name, mime=mime,
                    width=w, height=h, size=size, mtime=mtime
                ))
            except Exception:
                continue
            
            # Progress for large dirs
            if total > 1000 and (i + 1) % 10000 == 0:
                print(f"[lenslet] ... {i + 1}/{total}")

        if total > 1000:
            print(f"[lenslet] Indexed {len(items)} images in {path or '/'}")

        index = CachedIndex(
            path=path,
            generated_at=datetime.now(timezone.utc).isoformat(),
            items=items,
            dirs=dirs,
        )
        self._indexes[norm] = index
        return index

    def get_dimensions(self, path: str) -> tuple[int, int]:
        """Get image dimensions, loading lazily if needed."""
        if path in self._dimensions:
            return self._dimensions[path]

        # Try fast header-only read first
        try:
            abs_path = self._abs_path(path)
            dims = self._read_dimensions_fast(abs_path)
            if dims:
                self._dimensions[path] = dims
                return dims
        except Exception:
            pass

        # Fallback to PIL (loads more data but works for all formats)
        try:
            raw = self.read_bytes(path)
            with Image.open(BytesIO(raw)) as im:
                w, h = im.size
                self._dimensions[path] = (w, h)
                return w, h
        except Exception:
            return 0, 0

    def _read_dimensions_fast(self, filepath: str) -> tuple[int, int] | None:
        """Read image dimensions from header only (fast)."""
        ext = filepath.lower().split(".")[-1]
        
        try:
            with open(filepath, "rb") as f:
                if ext in ("jpg", "jpeg"):
                    return self._jpeg_dimensions(f)
                elif ext == "png":
                    return self._png_dimensions(f)
                elif ext == "webp":
                    return self._webp_dimensions(f)
        except Exception:
            pass
        return None

    def _jpeg_dimensions(self, f) -> tuple[int, int] | None:
        """Read JPEG dimensions from SOF marker."""
        f.seek(0)
        if f.read(2) != b'\xff\xd8':
            return None
        while True:
            marker = f.read(2)
            if len(marker) < 2:
                return None
            if marker[0] != 0xff:
                return None
            if marker[1] == 0xd9:  # EOI
                return None
            if 0xc0 <= marker[1] <= 0xcf and marker[1] not in (0xc4, 0xc8, 0xcc):
                # SOF marker
                length = struct.unpack(">H", f.read(2))[0]
                f.read(1)  # precision
                h, w = struct.unpack(">HH", f.read(4))
                return w, h
            else:
                length = struct.unpack(">H", f.read(2))[0]
                f.seek(length - 2, 1)

    def _png_dimensions(self, f) -> tuple[int, int] | None:
        """Read PNG dimensions from IHDR chunk."""
        f.seek(0)
        sig = f.read(8)
        if sig != b'\x89PNG\r\n\x1a\n':
            return None
        f.read(4)  # chunk length
        chunk_type = f.read(4)
        if chunk_type != b'IHDR':
            return None
        w, h = struct.unpack(">II", f.read(8))
        return w, h

    def _webp_dimensions(self, f) -> tuple[int, int] | None:
        """Read WebP dimensions from header."""
        f.seek(0)
        riff = f.read(4)
        if riff != b'RIFF':
            return None
        f.read(4)  # file size
        webp = f.read(4)
        if webp != b'WEBP':
            return None
        chunk = f.read(4)
        if chunk == b'VP8 ':
            f.read(4)  # chunk size
            f.read(3)  # frame tag
            if f.read(3) != b'\x9d\x01\x2a':
                return None
            data = f.read(4)
            w = (data[0] | (data[1] << 8)) & 0x3fff
            h = (data[2] | (data[3] << 8)) & 0x3fff
            return w, h
        elif chunk == b'VP8L':
            f.read(4)  # chunk size
            sig = f.read(1)
            if sig != b'\x2f':
                return None
            data = struct.unpack("<I", f.read(4))[0]
            w = (data & 0x3fff) + 1
            h = ((data >> 14) & 0x3fff) + 1
            return w, h
        elif chunk == b'VP8X':
            f.read(4)  # chunk size
            f.read(4)  # flags
            data = f.read(6)
            w = (data[0] | (data[1] << 8) | (data[2] << 16)) + 1
            h = (data[3] | (data[4] << 8) | (data[5] << 16)) + 1
            return w, h
        return None

    def _all_items(self) -> list[CachedItem]:
        """Return cached items; build root index if nothing is cached yet."""
        if self._indexes:
            return [it for idx in self._indexes.values() for it in idx.items]
        try:
            return list(self.get_index("/").items)
        except Exception:
            return []

    def search(self, query: str = "", path: str = "/", limit: int = 100) -> list[CachedItem]:
        """Simple in-memory search over cached indexes."""
        q = (query or "").lower()
        norm = self._normalize_path(path)
        scope_prefix = f"{norm}/" if norm else ""

        results: list[CachedItem] = []
        for item in self._all_items():
            logical_path = item.path.lstrip("/")
            if norm and not (logical_path == norm or logical_path.startswith(scope_prefix)):
                continue
            meta = self.get_metadata(item.path)
            haystack = " ".join([
                item.name,
                " ".join(meta.get("tags", [])),
                meta.get("notes", ""),
            ]).lower()
            if q in haystack:
                results.append(item)
                if len(results) >= limit:
                    break
        return results

    def get_thumbnail(self, path: str) -> bytes | None:
        """Get thumbnail, generating if needed."""
        if path in self._thumbnails:
            return self._thumbnails[path]

        try:
            raw = self.read_bytes(path)
            thumb, dims = self._make_thumbnail(raw)
            self._thumbnails[path] = thumb
            # Cache dimensions from thumbnail generation
            if dims:
                self._dimensions[path] = dims
            return thumb
        except Exception:
            return None

    def _make_thumbnail(self, img_bytes: bytes) -> tuple[bytes, tuple[int, int] | None]:
        """Generate a WebP thumbnail. Returns (thumb_bytes, (w, h))."""
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
            return out.getvalue(), (w, h)

    def get_metadata(self, path: str) -> dict:
        """Get metadata for an image (in-memory only)."""
        if path in self._metadata:
            return self._metadata[path]
        # Build minimal metadata - dimensions loaded lazily
        w, h = self._dimensions.get(path, (0, 0))
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
            self._dimensions.clear()
        else:
            norm = self._normalize_path(path)
            self._indexes.pop(norm, None)
            self._thumbnails.pop(path, None)
            self._metadata.pop(path, None)
            self._dimensions.pop(path, None)

    @staticmethod
    def _guess_mime(name: str) -> str:
        n = name.lower()
        if n.endswith(".webp"):
            return "image/webp"
        if n.endswith(".png"):
            return "image/png"
        return "image/jpeg"
