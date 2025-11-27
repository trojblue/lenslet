"""In-memory dataset storage for programmatic API."""
from __future__ import annotations
import os
import struct
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import urlparse
from PIL import Image


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
    url: str | None = None  # For S3 images, this is the presigned URL


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

    def __init__(
        self,
        datasets: dict[str, list[str]],
        thumb_size: int = 256,
        thumb_quality: int = 70,
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
        
        # Build flat path structure: /dataset_name/image_name
        self._items: dict[str, CachedItem] = {}  # path -> item
        self._indexes: dict[str, CachedIndex] = {}
        self._thumbnails: dict[str, bytes] = {}
        self._metadata: dict[str, dict] = {}
        self._dimensions: dict[str, tuple[int, int]] = {}
        
        # Build initial index
        self._build_all_indexes()

    def _is_s3_uri(self, path: str) -> bool:
        """Check if path is an S3 URI."""
        return path.startswith("s3://")

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
        if self._is_s3_uri(path):
            parsed = urlparse(path)
            return os.path.basename(parsed.path)
        return os.path.basename(path)

    def _guess_mime(self, name: str) -> str:
        """Guess MIME type from filename."""
        n = name.lower()
        if n.endswith(".webp"):
            return "image/webp"
        if n.endswith(".png"):
            return "image/png"
        return "image/jpeg"

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
            for source_path in paths:
                name = self._extract_name(source_path)
                if not self._is_supported_image(name):
                    continue
                
                # Create logical path: /dataset_name/filename
                logical_path = f"/{dataset_name}/{name}"
                
                # Determine if S3 or local
                is_s3 = self._is_s3_uri(source_path)
                url = None
                size = 0
                
                if is_s3:
                    # For S3, get presigned URL
                    try:
                        url = self._get_presigned_url(source_path)
                        # We can't easily get size without fetching, use 0 for now
                        size = 0
                    except Exception as e:
                        print(f"[lenslet] Warning: Failed to presign {source_path}: {e}")
                        continue
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
                
                # Create cached item
                item = CachedItem(
                    path=logical_path,
                    name=name,
                    mime=mime,
                    width=0,  # Lazy load
                    height=0,  # Lazy load
                    size=size,
                    mtime=mtime,
                    url=url,  # For S3 images
                )
                
                items.append(item)
                self._items[logical_path] = item
                
                # Store source path mapping
                if not hasattr(self, '_source_paths'):
                    self._source_paths = {}
                self._source_paths[logical_path] = source_path
            
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
        if not hasattr(self, '_source_paths'):
            raise FileNotFoundError(logical_path)
        if logical_path not in self._source_paths:
            raise FileNotFoundError(logical_path)
        return self._source_paths[logical_path]

    def read_bytes(self, path: str) -> bytes:
        """Read file contents. For S3, downloads from presigned URL. For local, reads file."""
        source_path = self.get_source_path(path)
        item = self._items[path]
        
        if item.url:  # S3 image
            import urllib.request
            try:
                with urllib.request.urlopen(item.url) as response:
                    return response.read()
            except Exception as e:
                raise RuntimeError(f"Failed to download from S3: {e}")
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
        if path in self._metadata:
            return self._metadata[path]
        
        # Get dimensions if available
        w, h = self._dimensions.get(path, (0, 0))
        if (w == 0 or h == 0) and path in self._items:
            w = self._items[path].width
            h = self._items[path].height
        
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
        """Update in-memory metadata (session-only)."""
        self._metadata[path] = meta

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

    def _guess_mime(self, name: str) -> str:
        """Guess MIME type from filename."""
        n = name.lower()
        if n.endswith(".webp"):
            return "image/webp"
        if n.endswith(".png"):
            return "image/png"
        return "image/jpeg"


