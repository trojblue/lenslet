from __future__ import annotations

import hashlib
from pathlib import Path


class OgImageCache:
    """Simple on-disk cache for generated OG preview images."""

    def __init__(self, root: Path, *, max_entries: int = 128) -> None:
        self.root = Path(root)
        self.max_entries = max(1, int(max_entries))

    def _path_for(self, key: str) -> Path:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
        subdir = digest[:2]
        return self.root / subdir / f"{digest}.png"

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
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
            self._prune_if_needed()
        except Exception:
            pass

    def _prune_if_needed(self) -> None:
        try:
            files = [entry for entry in self.root.rglob("*.png") if entry.is_file()]
        except Exception:
            return
        over_limit = len(files) - self.max_entries
        if over_limit <= 0:
            return
        files.sort(key=lambda entry: entry.stat().st_mtime)
        for stale in files[:over_limit]:
            try:
                stale.unlink()
            except Exception:
                continue
