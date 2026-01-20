from __future__ import annotations

import hashlib
from pathlib import Path


class OgImageCache:
    """Simple on-disk cache for generated OG preview images."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

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
        except Exception:
            pass
