from __future__ import annotations

import hashlib
import threading
from pathlib import Path


class ThumbCache:
    """Simple on-disk WebP thumbnail cache."""

    def __init__(self, root: Path, *, max_disk_bytes: int | None = None) -> None:
        self.root = Path(root)
        self.max_disk_bytes = max(0, int(max_disk_bytes or 0))
        self._lock = threading.Lock()
        self._current_size_bytes: int | None = None
        if self.max_disk_bytes > 0:
            self._current_size_bytes = self._evict_to_cap()

    def _scan_cache_entries(self) -> tuple[int, list[tuple[float, int, Path]]]:
        try:
            paths = list(self.root.rglob("*.webp"))
        except Exception:
            return 0, []
        total = 0
        entries: list[tuple[float, int, Path]] = []
        for path in paths:
            try:
                stat = path.stat()
            except Exception:
                continue
            total += stat.st_size
            entries.append((stat.st_mtime, stat.st_size, path))
        return total, entries

    def _evict_to_cap(self) -> int:
        if self.max_disk_bytes <= 0:
            return self._current_size_bytes or 0
        total, entries = self._scan_cache_entries()
        if total <= self.max_disk_bytes:
            self._current_size_bytes = total
            return total
        entries.sort(key=lambda entry: entry[0])
        for _mtime, size, path in entries:
            if total <= self.max_disk_bytes:
                break
            try:
                path.unlink()
            except Exception:
                continue
            total -= size
        self._current_size_bytes = total
        return total

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
                old_size = 0
                if self.max_disk_bytes > 0:
                    try:
                        old_size = path.stat().st_size if path.exists() else 0
                    except Exception:
                        old_size = 0
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".tmp")
                tmp.write_bytes(data)
                tmp.replace(path)
                if self.max_disk_bytes <= 0:
                    return
                if self._current_size_bytes is None:
                    self._current_size_bytes = self._evict_to_cap()
                    return
                self._current_size_bytes = max(
                    0,
                    self._current_size_bytes - old_size + len(data),
                )
                if self._current_size_bytes > self.max_disk_bytes:
                    self._current_size_bytes = self._evict_to_cap()
        except Exception:
            pass
