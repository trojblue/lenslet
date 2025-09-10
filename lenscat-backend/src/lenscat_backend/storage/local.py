from __future__ import annotations
import os
from .base import Storage

class LocalStorage(Storage):
    def __init__(self, root: str):
        # Resolve the configured root to an absolute, symlink-resolved path
        self.root = os.path.abspath(root)
        self._root_real = os.path.realpath(self.root)

    def _abs(self, path: str) -> str:
        # Join requested path under root and normalize
        candidate = os.path.abspath(os.path.join(self._root_real, path.lstrip("/")))
        # Resolve symlinks and ensure the final path is within the storage root
        real = os.path.realpath(candidate)
        try:
            common = os.path.commonpath([self._root_real, real])
        except Exception:
            # Fallback for edge cases; deny on error
            raise ValueError("invalid path")
        if common != self._root_real:
            raise ValueError("invalid path")
        return real

    def list_dir(self, path: str):
        p = self._abs(path)
        files, dirs = [], []
        for name in os.listdir(p):
            full = os.path.join(p, name)
            if os.path.isdir(full):
                dirs.append(name)
            else:
                files.append(name)
        return files, dirs

    def read_bytes(self, path: str) -> bytes:
        with open(self._abs(path), 'rb') as f:
            return f.read()

    def write_bytes(self, path: str, data: bytes) -> None:
        full = self._abs(path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, 'wb') as f:
            f.write(data)

    def exists(self, path: str) -> bool:
        return os.path.exists(self._abs(path))

    def size(self, path: str) -> int:
        return os.path.getsize(self._abs(path))

    def join(self, *parts: str) -> str:
        return "/".join([p.strip("/") for p in parts if p])

    def etag(self, path: str) -> str | None:
        try:
            st = os.stat(self._abs(path))
            return f"{st.st_mtime_ns}-{st.st_size}"
        except FileNotFoundError:
            return None
