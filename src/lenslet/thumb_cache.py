from __future__ import annotations

import hashlib
from pathlib import Path
import threading


class ThumbCache:
    """Simple on-disk WebP thumbnail cache."""

    def __init__(self, root: Path, *, max_disk_bytes: int | None = None) -> None:
        self.root = Path(root)
        self.max_disk_bytes = max(0, int(max_disk_bytes or 0))
        self._lock = threading.Lock()
        if self.max_disk_bytes > 0:
            self._evict_to_cap()

    def _evict_to_cap(self) -> None:
        if self.max_disk_bytes <= 0:
            return
        try:
            paths = list(self.root.rglob("*.webp"))
        except Exception:
            return
        total = 0
        entries: list[tuple[float, int, Path]] = []
        for path in paths:
            try:
                stat = path.stat()
            except Exception:
                continue
            total += stat.st_size
            entries.append((stat.st_mtime, stat.st_size, path))
        if total <= self.max_disk_bytes:
            return
        entries.sort(key=lambda entry: entry[0])
        for _mtime, size, path in entries:
            if total <= self.max_disk_bytes:
                break
            try:
                path.unlink()
            except Exception:
                continue
            total -= size

    def _path_for(self, key: str) -> Path:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
        subdir = digest[:2]
        return self.root / subdir / f"{digest}.webp"

    def get(self, key: str) -> bytes | None:
        path = self._path_for(key)
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None
        except Exception:
            return None

    def set(self, key: str, data: bytes) -> None:
        path = self._path_for(key)
        try:
            with self._lock:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".tmp")
                tmp.write_bytes(data)
                tmp.replace(path)
                self._evict_to_cap()
        except Exception:
            pass
