"""In-memory dataset storage for programmatic API."""
from __future__ import annotations
import os
import struct
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import urlparse
from PIL import Image
from .progress import ProgressBar


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
    url: str | None = None  # For HTTP/HTTPS sources


@dataclass
class CachedIndex:
    """In-memory cached folder index."""
    path: str
    generated_at: str
    items: list[CachedItem] = field(default_factory=list)
    dirs: list[str] = field(default_factory=list)


class DatasetStorage:
    """
    In-memory storage for programmatic datasets.
    Supports both local file paths and S3 URIs.
    """

    IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
    REMOTE_HEADER_BYTES = 65536
    REMOTE_DIM_WORKERS = 16

    def __init__(
        self,
        datasets: dict[str, list[str]],
        thumb_size: int = 256,
        thumb_quality: int = 70,
        include_source_in_search: bool = True,
    ):
        """
        Initialize with datasets.
        
        Args:
            datasets: Dict of {dataset_name: [list of paths/URIs]}
            thumb_size: Thumbnail short edge size
            thumb_quality: WebP quality for thumbnails
        """
        self.datasets = datasets
        self.thumb_size = thumb_size
        self.thumb_quality = thumb_quality
        self._include_source_in_search = include_source_in_search
        self._progress_bar = ProgressBar()
        
        # Build flat path structure: /dataset_name/image_name
        self._items: dict[str, CachedItem] = {}  # path -> item
        self._indexes: dict[str, CachedIndex] = {}
        self._thumbnails: dict[str, bytes] = {}
        self._metadata: dict[str, dict] = {}
        self._dimensions: dict[str, tuple[int, int]] = {}
        self._source_paths: dict[str, str] = {}
        
        # Build initial index
        self._build_all_indexes()

    def _is_s3_uri(self, path: str) -> bool:
        """Check if path is an S3 URI."""
        return path.startswith("s3://")

    def _is_http_url(self, path: str) -> bool:
        """Check if path is an HTTP/HTTPS URL."""
        return path.startswith("http://") or path.startswith("https://")

    def _get_presigned_url(self, s3_uri: str, expires_in: int = 3600) -> str:
        """Convert S3 URI to a presigned HTTPS URL using boto3."""
        try:
            import boto3
            from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ImportError(
                "boto3 package required for S3 support. Install with: pip install lenslet[s3]"
            ) from exc

        parsed = urlparse(s3_uri)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        if not bucket or not key:
            raise ValueError(f"Invalid S3 URI: {s3_uri}")

        try:
            s3_client = boto3.client("s3")
            return s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        except (BotoCoreError, ClientError, NoCredentialsError) as e:
            raise RuntimeError(f"Failed to presign S3 URI: {e}") from e

    def _is_supported_image(self, name: str) -> bool:
        """Check if file is a supported image."""
        return name.lower().endswith(self.IMAGE_EXTS)

    def _extract_name(self, path: str) -> str:
        """Extract filename from local path or S3 URI."""
        if self._is_s3_uri(path) or self._is_http_url(path):
            parsed = urlparse(path)
            return os.path.basename(parsed.path)
        return os.path.basename(path)

    def _read_dimensions_from_bytes(self, data: bytes, ext: str | None) -> tuple[int, int] | None:
        """Read image dimensions from in-memory bytes."""
        if not data:
            return None

        kind = None
        if ext in ("jpg", "jpeg"):
            kind = "jpeg"
        elif ext == "png":
            kind = "png"
        elif ext == "webp":
            kind = "webp"
        else:
            if data.startswith(b"\xff\xd8"):
                kind = "jpeg"
            elif data.startswith(b"\x89PNG\r\n\x1a\n"):
                kind = "png"
            elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
                kind = "webp"

        try:
            buf = BytesIO(data)
            if kind == "jpeg":
                return self._jpeg_dimensions(buf)
            if kind == "png":
                return self._png_dimensions(buf)
            if kind == "webp":
                return self._webp_dimensions(buf)
        except Exception:
            return None
        return None

    def _parse_content_range(self, header: str) -> int | None:
        """Parse Content-Range and return total size if present."""
        # Expected format: "bytes start-end/total" or "bytes */total"
        try:
            if "/" not in header:
                return None
            total = header.split("/")[-1].strip()
            if total == "*":
                return None
            return int(total)
        except Exception:
            return None

    def _get_remote_header_bytes(
        self,
        url: str,
        max_bytes: int | None = None,
    ) -> tuple[bytes | None, int | None]:
        """Fetch the first N bytes of a remote image via Range request."""
        max_bytes = max_bytes or self.REMOTE_HEADER_BYTES
        try:
            import urllib.request
            req = urllib.request.Request(
                url,
                headers={"Range": f"bytes=0-{max_bytes - 1}"},
            )
            with urllib.request.urlopen(req) as response:
                data = response.read(max_bytes)
                total = None
                content_range = response.headers.get("Content-Range")
                if content_range:
                    total = self._parse_content_range(content_range)
                if total is None:
                    content_length = response.headers.get("Content-Length")
                    if content_length:
                        try:
                            total = int(content_length)
                        except Exception:
                            total = None
                return data, total
        except Exception:
            return None, None

    def _get_remote_header_info(
        self,
        url: str,
        name: str,
    ) -> tuple[tuple[int, int] | None, int | None]:
        """Try to read dimensions and size from a ranged remote request."""
        header, total = self._get_remote_header_bytes(url)
        if not header:
            return None, total
        ext = os.path.splitext(name)[1].lower().lstrip(".") or None
        return self._read_dimensions_from_bytes(header, ext), total

    def _get_remote_dimensions(self, url: str, name: str) -> tuple[int, int] | None:
        """Try to read dimensions from a ranged remote request."""
        dims, _ = self._get_remote_header_info(url, name)
        return dims

    def _progress(self, done: int, total: int, label: str) -> None:
        self._progress_bar.update(done, total, label)

    def _effective_remote_workers(self, total: int) -> int:
        if total <= 0:
            return 0
        cpu = os.cpu_count() or 1
        return max(1, min(self.REMOTE_DIM_WORKERS, cpu, total))

    def _probe_remote_dimensions(self, tasks: list[tuple[str, CachedItem, str, str]], label: str) -> None:
        """Fetch remote dimensions in parallel and update cached items."""
        total = len(tasks)
        if total == 0:
            return
        workers = self._effective_remote_workers(total)
        done = 0
        last_print = 0.0
        progress_label = label

        def _work(task: tuple[str, CachedItem, str, str]):
            logical_path, item, source_path, name = task
            url = None
            if self._is_s3_uri(source_path):
                try:
                    url = self._get_presigned_url(source_path)
                except Exception:
                    url = None
            elif self._is_http_url(source_path):
                url = source_path
            if not url:
                return logical_path, item, None, None
            dims, total_size = self._get_remote_header_info(url, name)
            return logical_path, item, dims, total_size

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(_work, task) for task in tasks]
            for future in as_completed(futures):
                logical_path, item, dims, total_size = future.result()
                if dims:
                    self._dimensions[logical_path] = dims
                    item.width, item.height = dims
                if total_size:
                    item.size = total_size
                done += 1
                now = time.monotonic()
                if now - last_print > 0.1 or done == total:
                    self._progress(done, total, progress_label)
                    last_print = now

    def _build_all_indexes(self):
        """Build indexes for all datasets."""
        # Root index contains dataset folders
        root_dirs = list(self.datasets.keys())
        self._indexes["/"] = CachedIndex(
            path="/",
            generated_at=datetime.now(timezone.utc).isoformat(),
            items=[],
            dirs=root_dirs,
        )
        
        # Build index for each dataset
        for dataset_name, paths in self.datasets.items():
            items = []
            remote_tasks: list[tuple[str, CachedItem, str, str]] = []
            for source_path in paths:
                name = self._extract_name(source_path)
                if not self._is_supported_image(name):
                    continue
                
                # Create logical path: /dataset_name/filename
                logical_path = f"/{dataset_name}/{name}"
                
                # Determine source type
                is_s3 = self._is_s3_uri(source_path)
                is_http = self._is_http_url(source_path)
                url = None
                size = 0

                if is_s3:
                    # For S3, presign on-demand only
                    size = 0
                elif is_http:
                    # Plain HTTP/HTTPS URL — use as-is
                    url = source_path
                    size = 0
                else:
                    # For local, validate and get size
                    if not os.path.exists(source_path):
                        print(f"[lenslet] Warning: File not found: {source_path}")
                        continue
                    try:
                        size = os.path.getsize(source_path)
                    except Exception:
                        size = 0
                
                mime = self._guess_mime(name)
                mtime = time.time()
                width, height = 0, 0

                # Create cached item
                item = CachedItem(
                    path=logical_path,
                    name=name,
                    mime=mime,
                    width=width,
                    height=height,
                    size=size,
                    mtime=mtime,
                    url=url,  # For S3 images
                )

                items.append(item)
                self._items[logical_path] = item
                self._source_paths[logical_path] = source_path
                if url:
                    remote_tasks.append((logical_path, item, url, name))
                elif is_s3:
                    remote_tasks.append((logical_path, item, source_path, name))
            
            if remote_tasks:
                self._probe_remote_dimensions(remote_tasks, f"remote headers: {dataset_name}")

            # Create dataset index
            dataset_path = f"/{dataset_name}"
            self._indexes[dataset_path] = CachedIndex(
                path=dataset_path,
                generated_at=datetime.now(timezone.utc).isoformat(),
                items=items,
                dirs=[],
            )

    def _normalize_path(self, path: str) -> str:
        """Normalize path for consistent cache keys."""
        p = path.strip("/")
        return "/" + p if p else "/"

    def _canonical_meta_key(self, path: str) -> str:
        """Canonical key for metadata maps (leading slash, no trailing)."""
        p = (path or "").replace("\\", "/").strip()
        if not p:
            return "/"
        p = "/" + p.lstrip("/")
        if p != "/":
            p = p.rstrip("/")
        return p

    def get_index(self, path: str) -> CachedIndex:
        """Get cached index for a folder."""
        norm = self._normalize_path(path)
        if norm in self._indexes:
            return self._indexes[norm]
        raise FileNotFoundError(f"Dataset not found: {path}")

    def validate_image_path(self, path: str) -> None:
        """Ensure path is valid and exists in our dataset."""
        if not path or path not in self._items:
            raise FileNotFoundError(path)

    def get_source_path(self, logical_path: str) -> str:
        """Get original source path/URI for a logical path."""
        if logical_path not in self._source_paths:
            raise FileNotFoundError(logical_path)
        return self._source_paths[logical_path]

    def read_bytes(self, path: str) -> bytes:
        """Read file contents. For S3, downloads from presigned URL. For local, reads file."""
        source_path = self.get_source_path(path)
        item = self._items[path]
        
        if self._is_s3_uri(source_path):  # S3 image
            import urllib.request
            try:
                url = self._get_presigned_url(source_path)
                with urllib.request.urlopen(url) as response:
                    return response.read()
            except Exception as e:
                raise RuntimeError(f"Failed to download from S3: {e}")
        if item.url:  # HTTP/HTTPS image
            import urllib.request
            try:
                with urllib.request.urlopen(item.url) as response:
                    return response.read()
            except Exception as e:
                raise RuntimeError(f"Failed to download from URL: {e}")
        else:  # Local file
            with open(source_path, "rb") as f:
                return f.read()

    def exists(self, path: str) -> bool:
        """Check if path exists in dataset."""
        return path in self._items

    def size(self, path: str) -> int:
        """Get file size."""
        if path in self._items:
            return self._items[path].size
        return 0

    def join(self, *parts: str) -> str:
        """Join path parts."""
        return "/" + "/".join(p.strip("/") for p in parts if p.strip("/"))

    def etag(self, path: str) -> str | None:
        """Get ETag for caching."""
        if path in self._items:
            item = self._items[path]
            return f"{int(item.mtime)}-{item.size}"
        return None

    def get_thumbnail(self, path: str) -> bytes | None:
        """Get thumbnail, generating if needed."""
        if path in self._thumbnails:
            return self._thumbnails[path]

        try:
            raw = self.read_bytes(path)
            thumb, dims = self._make_thumbnail(raw)
            self._thumbnails[path] = thumb
            if dims:
                self._dimensions[path] = dims
            return thumb
        except Exception as e:
            print(f"[lenslet] Failed to generate thumbnail for {path}: {e}")
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

    def get_dimensions(self, path: str) -> tuple[int, int]:
        """Get image dimensions, loading lazily if needed."""
        if path in self._dimensions:
            return self._dimensions[path]

        item = self._items.get(path)
        if item:
            url = None
            source_path = self.get_source_path(path)
            if self._is_s3_uri(source_path):
                try:
                    url = self._get_presigned_url(source_path)
                except Exception:
                    url = None
            else:
                url = item.url
            if url:
                dims, total = self._get_remote_header_info(url, item.name)
                if total:
                    self._items[path].size = total
                if dims:
                    self._dimensions[path] = dims
                    self._items[path].width = dims[0]
                    self._items[path].height = dims[1]
                    return dims

        try:
            raw = self.read_bytes(path)
            with Image.open(BytesIO(raw)) as im:
                w, h = im.size
                self._dimensions[path] = (w, h)
                
                # Update item dimensions
                if path in self._items:
                    self._items[path].width = w
                    self._items[path].height = h
                
                return w, h
        except Exception:
            return 0, 0

    def get_metadata(self, path: str) -> dict:
        """Get metadata for an image."""
        key = self._canonical_meta_key(path)
        if key in self._metadata:
            return self._metadata[key]
        
        # Get dimensions if available
        w, h = self._dimensions.get(key, (0, 0))
        if (w == 0 or h == 0) and key in self._items:
            w = self._items[key].width
            h = self._items[key].height
        
        meta = {
            "width": w,
            "height": h,
            "tags": [],
            "notes": "",
            "star": None,
            "version": 1,
            "updated_at": "",
            "updated_by": "server",
        }
        self._metadata[key] = meta
        return meta

    def set_metadata(self, path: str, meta: dict) -> None:
        """Update in-memory metadata (session-only)."""
        key = self._canonical_meta_key(path)
        self._metadata[key] = meta

    def search(self, query: str = "", path: str = "/", limit: int = 100) -> list[CachedItem]:
        """Simple in-memory search."""
        q = (query or "").lower()
        norm = self._normalize_path(path)
        
        results = []
        for item in self._items.values():
            # Filter by path scope
            if norm != "/" and not item.path.startswith(norm + "/"):
                continue
            
            # Search in name and metadata
            meta = self.get_metadata(item.path)
            parts = [
                item.name,
                " ".join(meta.get("tags", [])),
                meta.get("notes", ""),
            ]
            if self._include_source_in_search:
                source = self._source_paths.get(item.path, "")
                if source:
                    parts.append(source)
                if item.url:
                    parts.append(item.url)
            haystack = " ".join(parts).lower()
            
            if q in haystack:
                results.append(item)
                if len(results) >= limit:
                    break
        
        return results

    def _jpeg_dimensions(self, f) -> tuple[int, int] | None:
        """Read JPEG dimensions from SOF marker."""
        f.seek(0)
        if f.read(2) != b"\xff\xd8":
            return None
        while True:
            marker = f.read(2)
            if len(marker) < 2 or marker[0] != 0xff:
                return None
            if marker[1] == 0xd9:  # EOI
                return None
            if 0xc0 <= marker[1] <= 0xcf and marker[1] not in (0xc4, 0xc8, 0xcc):
                length_bytes = f.read(2)
                if len(length_bytes) < 2:
                    return None
                _ = struct.unpack(">H", length_bytes)[0]
                f.read(1)  # precision
                size = f.read(4)
                if len(size) < 4:
                    return None
                h, w = struct.unpack(">HH", size)
                return w, h
            length_bytes = f.read(2)
            if len(length_bytes) < 2:
                return None
            length = struct.unpack(">H", length_bytes)[0]
            if length < 2:
                return None
            f.seek(length - 2, 1)

    def _png_dimensions(self, f) -> tuple[int, int] | None:
        """Read PNG dimensions from IHDR chunk."""
        f.seek(0)
        if f.read(8) != b"\x89PNG\r\n\x1a\n":
            return None
        if len(f.read(4)) < 4:
            return None
        if f.read(4) != b"IHDR":
            return None
        data = f.read(8)
        if len(data) < 8:
            return None
        w, h = struct.unpack(">II", data)
        return w, h

    def _webp_dimensions(self, f) -> tuple[int, int] | None:
        """Read WebP dimensions from header."""
        f.seek(0)
        if f.read(4) != b"RIFF":
            return None
        if len(f.read(4)) < 4:
            return None
        if f.read(4) != b"WEBP":
            return None
        chunk = f.read(4)
        if chunk == b"VP8 ":
            if len(f.read(4)) < 4:
                return None
            f.read(3)
            if f.read(3) != b"\x9d\x01\x2a":
                return None
            data = f.read(4)
            if len(data) < 4:
                return None
            w = (data[0] | (data[1] << 8)) & 0x3FFF
            h = (data[2] | (data[3] << 8)) & 0x3FFF
            return w, h
        if chunk == b"VP8L":
            if len(f.read(4)) < 4:
                return None
            if f.read(1) != b"\x2f":
                return None
            data = f.read(4)
            if len(data) < 4:
                return None
            val = struct.unpack("<I", data)[0]
            w = (val & 0x3FFF) + 1
            h = ((val >> 14) & 0x3FFF) + 1
            return w, h
        if chunk == b"VP8X":
            if len(f.read(4)) < 4:
                return None
            f.read(4)
            data = f.read(6)
            if len(data) < 6:
                return None
            w = (data[0] | (data[1] << 8) | (data[2] << 16)) + 1
            h = (data[3] | (data[4] << 8) | (data[5] << 16)) + 1
            return w, h
        return None

    def _guess_mime(self, name: str) -> str:
        """Guess MIME type from filename."""
        n = name.lower()
        if n.endswith(".webp"):
            return "image/webp"
        if n.endswith(".png"):
            return "image/png"
        return "image/jpeg"
