from __future__ import annotations
import os
import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from PIL import Image

from .local import LocalStorage


@dataclass
class CachedItem:
    """In-memory cached metadata for an image loaded from Parquet."""
    path: str
    name: str
    mime: str
    width: int
    height: int
    size: int
    mtime: float
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class CachedIndex:
    """In-memory cached folder index."""
    path: str
    generated_at: str
    items: list[CachedItem] = field(default_factory=list)
    dirs: list[str] = field(default_factory=list)


def _load_parquet(path: str) -> dict[str, list[Any]]:
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - dependency is optional until parquet is used
        raise ImportError(
            "pyarrow is required for Parquet datasets. Install with: pip install pyarrow"
        ) from exc

    table = pq.read_table(path)
    return table.to_pydict()


def _normalize_id(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_timestamp(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if hasattr(value, "timestamp"):
        try:
            return float(value.timestamp())
        except Exception:
            return None
    return _coerce_float(value)


class ParquetStorage:
    """
    In-memory storage backed by Parquet files for item metadata/metrics.
    Reads image bytes from a local dataset root.
    """

    IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")

    def __init__(self, root: str, thumb_size: int = 256, thumb_quality: int = 70):
        self.local = LocalStorage(root)
        self.root = root
        self.thumb_size = thumb_size
        self.thumb_quality = thumb_quality

        self._indexes: dict[str, CachedIndex] = {}
        self._items: dict[str, CachedItem] = {}
        self._thumbnails: dict[str, bytes] = {}
        self._metadata: dict[str, dict] = {}
        self._dimensions: dict[str, tuple[int, int]] = {}

        self._build_indexes()

    def _normalize_path(self, path: str) -> str:
        return path.strip("/") if path else ""

    def _normalize_item_path(self, path: str) -> str:
        p = (path or "").replace("\\", "/").lstrip("/")
        if p.startswith("./"):
            p = p[2:]
        return p.strip("/")

    def _canonical_meta_key(self, path: str) -> str:
        """Canonical key for metadata maps (leading slash, no trailing)."""
        p = (path or "").replace("\\", "/").strip()
        if not p:
            return "/"
        p = "/" + p.lstrip("/")
        if p != "/":
            p = p.rstrip("/")
        return p

    def _is_supported_image(self, name: str) -> bool:
        return name.lower().endswith(self.IMAGE_EXTS)

    def _guess_mime(self, name: str) -> str:
        n = name.lower()
        if n.endswith(".webp"):
            return "image/webp"
        if n.endswith(".png"):
            return "image/png"
        return "image/jpeg"

    def _build_metrics_map(self, data: dict[str, list[Any]] | None) -> dict[str, dict[str, float]]:
        if not data:
            return {}
        if "image_id" not in data:
            return {}

        ids = data.get("image_id") or []
        metric_keys = [k for k in data.keys() if k != "image_id"]
        metrics: dict[str, dict[str, float]] = {}

        for idx, raw_id in enumerate(ids):
            norm_id = _normalize_id(raw_id)
            if norm_id is None:
                continue
            row: dict[str, float] = {}
            for key in metric_keys:
                col = data.get(key) or []
                if idx >= len(col):
                    continue
                val = _coerce_float(col[idx])
                if val is None:
                    continue
                row[key] = val
            if row:
                metrics[norm_id] = row
        return metrics

    def _build_indexes(self) -> None:
        items_path = os.path.join(self.root, "items.parquet")
        data = _load_parquet(items_path)

        if "path" not in data:
            raise ValueError("items.parquet must include a 'path' column")
        if "image_id" not in data:
            print("[lenslet] Warning: items.parquet missing 'image_id'; metrics join may be incomplete")

        ids = data.get("image_id") or [None] * len(data["path"])
        paths = data.get("path") or []
        sizes = data.get("size")
        mtimes = data.get("mtime")
        widths = data.get("width")
        heights = data.get("height")

        metrics_path = os.path.join(self.root, "metrics.parquet")
        metrics_data = None
        if os.path.exists(metrics_path):
            try:
                metrics_data = _load_parquet(metrics_path)
            except Exception as exc:
                print(f"[lenslet] Warning: Failed to read metrics.parquet: {exc}")
                metrics_data = None

        metrics_map = self._build_metrics_map(metrics_data)

        generated_at = datetime.now(timezone.utc).isoformat()
        dir_children: dict[str, set[str]] = {}

        for i, raw_path in enumerate(paths):
            if raw_path is None:
                continue
            norm_path = self._normalize_item_path(str(raw_path))
            if not norm_path:
                continue
            name = os.path.basename(norm_path)
            if not self._is_supported_image(name):
                continue

            item_id = _normalize_id(ids[i]) if i < len(ids) else None
            metrics = metrics_map.get(item_id, {})

            size = _coerce_int(sizes[i]) if sizes and i < len(sizes) else None
            mtime = _coerce_timestamp(mtimes[i]) if mtimes and i < len(mtimes) else None
            width = _coerce_int(widths[i]) if widths and i < len(widths) else None
            height = _coerce_int(heights[i]) if heights and i < len(heights) else None

            if size is None or mtime is None:
                try:
                    abs_path = self.local.resolve_path(norm_path)
                    stat = os.stat(abs_path)
                    if size is None:
                        size = stat.st_size
                    if mtime is None:
                        mtime = stat.st_mtime
                except Exception:
                    size = size or 0
                    mtime = mtime or 0.0

            w = width or 0
            h = height or 0
            if w == 0 or h == 0:
                try:
                    abs_path = self.local.resolve_path(norm_path)
                    dims = self._read_dimensions_fast(abs_path)
                    if dims:
                        w, h = dims
                        self._dimensions[norm_path] = dims
                except Exception:
                    pass

            item = CachedItem(
                path=norm_path,
                name=name,
                mime=self._guess_mime(name),
                width=w,
                height=h,
                size=size or 0,
                mtime=mtime or 0.0,
                metrics=metrics,
            )

            self._items[norm_path] = item

            folder = os.path.dirname(norm_path).replace("\\", "/")
            folder_norm = self._normalize_path(folder)
            self._indexes.setdefault(folder_norm, CachedIndex(
                path="/" + folder_norm if folder_norm else "/",
                generated_at=generated_at,
                items=[],
                dirs=[],
            )).items.append(item)

            parts = folder_norm.split("/") if folder_norm else []
            for depth in range(len(parts)):
                parent = "/".join(parts[:depth])
                child = parts[depth]
                dir_children.setdefault(parent, set()).add(child)

        # Build index entries for directories
        self._indexes.setdefault("", CachedIndex(path="/", generated_at=generated_at, items=[], dirs=[]))
        for parent, children in dir_children.items():
            index = self._indexes.setdefault(parent, CachedIndex(
                path="/" + parent if parent else "/",
                generated_at=generated_at,
                items=[],
                dirs=[],
            ))
            index.dirs = sorted(children)

    def get_index(self, path: str) -> CachedIndex:
        norm = self._normalize_path(path)
        if norm in self._indexes:
            return self._indexes[norm]
        raise FileNotFoundError(path)

    def validate_image_path(self, path: str) -> None:
        if not path:
            raise ValueError("empty path")
        norm = self._normalize_item_path(path)
        if norm not in self._items:
            raise FileNotFoundError(path)

    def read_bytes(self, path: str) -> bytes:
        norm = self._normalize_item_path(path)
        return self.local.read_bytes(norm)

    def exists(self, path: str) -> bool:
        norm = self._normalize_item_path(path)
        return norm in self._items

    def size(self, path: str) -> int:
        norm = self._normalize_item_path(path)
        item = self._items.get(norm)
        return item.size if item else 0

    def join(self, *parts: str) -> str:
        return self.local.join(*parts)

    def etag(self, path: str) -> str | None:
        norm = self._normalize_item_path(path)
        item = self._items.get(norm)
        if not item:
            return None
        return f"{int(item.mtime)}-{item.size}"

    def get_thumbnail(self, path: str) -> bytes | None:
        norm = self._normalize_item_path(path)
        if norm in self._thumbnails:
            return self._thumbnails[norm]

        try:
            raw = self.read_bytes(norm)
            thumb, dims = self._make_thumbnail(raw)
            self._thumbnails[norm] = thumb
            if dims:
                self._dimensions[norm] = dims
            return thumb
        except Exception:
            return None

    def get_dimensions(self, path: str) -> tuple[int, int]:
        norm = self._normalize_item_path(path)
        if norm in self._dimensions:
            return self._dimensions[norm]
        try:
            abs_path = self.local.resolve_path(norm)
            dims = self._read_dimensions_fast(abs_path)
            if dims:
                self._dimensions[norm] = dims
                if norm in self._items:
                    self._items[norm].width, self._items[norm].height = dims
                return dims
        except Exception:
            pass
        try:
            raw = self.read_bytes(norm)
            with Image.open(BytesIO(raw)) as im:
                w, h = im.size
                self._dimensions[norm] = (w, h)
                if norm in self._items:
                    self._items[norm].width = w
                    self._items[norm].height = h
                return w, h
        except Exception:
            return 0, 0

    def _make_thumbnail(self, img_bytes: bytes) -> tuple[bytes, tuple[int, int] | None]:
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

    def _read_dimensions_fast(self, filepath: str) -> tuple[int, int] | None:
        ext = filepath.lower().split(".")[-1]
        try:
            with open(filepath, "rb") as f:
                if ext in ("jpg", "jpeg"):
                    return self._jpeg_dimensions(f)
                if ext == "png":
                    return self._png_dimensions(f)
                if ext == "webp":
                    return self._webp_dimensions(f)
        except Exception:
            pass
        return None

    def _jpeg_dimensions(self, f) -> tuple[int, int] | None:
        f.seek(0)
        if f.read(2) != b"\xff\xd8":
            return None
        while True:
            marker = f.read(2)
            if len(marker) < 2 or marker[0] != 0xFF:
                return None
            if marker[1] == 0xD9:
                return None
            if 0xC0 <= marker[1] <= 0xCF and marker[1] not in (0xC4, 0xC8, 0xCC):
                f.read(2)
                f.read(1)
                h, w = struct.unpack(">HH", f.read(4))
                return w, h
            length = struct.unpack(">H", f.read(2))[0]
            f.seek(length - 2, 1)

    def _png_dimensions(self, f) -> tuple[int, int] | None:
        f.seek(0)
        if f.read(8) != b"\x89PNG\r\n\x1a\n":
            return None
        f.read(4)
        if f.read(4) != b"IHDR":
            return None
        w, h = struct.unpack(">II", f.read(8))
        return w, h

    def _webp_dimensions(self, f) -> tuple[int, int] | None:
        f.seek(0)
        if f.read(4) != b"RIFF":
            return None
        f.read(4)
        if f.read(4) != b"WEBP":
            return None
        chunk = f.read(4)
        if chunk == b"VP8 ":
            f.read(4)
            f.read(3)
            if f.read(3) != b"\x9d\x01\x2a":
                return None
            data = f.read(4)
            w = (data[0] | (data[1] << 8)) & 0x3FFF
            h = (data[2] | (data[3] << 8)) & 0x3FFF
            return w, h
        if chunk == b"VP8L":
            f.read(4)
            if f.read(1) != b"\x2f":
                return None
            data = struct.unpack("<I", f.read(4))[0]
            w = (data & 0x3FFF) + 1
            h = ((data >> 14) & 0x3FFF) + 1
            return w, h
        if chunk == b"VP8X":
            f.read(4)
            f.read(4)
            data = f.read(6)
            w = (data[0] | (data[1] << 8) | (data[2] << 16)) + 1
            h = (data[3] | (data[4] << 8) | (data[5] << 16)) + 1
            return w, h
        return None

    def get_metadata(self, path: str) -> dict:
        norm = self._normalize_item_path(path)
        key = self._canonical_meta_key(norm)
        if key in self._metadata:
            return self._metadata[key]
        w, h = self._dimensions.get(norm, (0, 0))
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
        norm = self._normalize_item_path(path)
        key = self._canonical_meta_key(norm)
        self._metadata[key] = meta

    def _all_items(self) -> list[CachedItem]:
        if self._indexes:
            return [it for idx in self._indexes.values() for it in idx.items]
        return list(self._items.values())

    def search(self, query: str = "", path: str = "/", limit: int = 100) -> list[CachedItem]:
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
