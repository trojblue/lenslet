from __future__ import annotations
import os
from .base import Storage

class LocalStorage(Storage):
    def __init__(self, root: str):
        self.root = os.path.abspath(root)

    def _abs(self, path: str) -> str:
        return os.path.abspath(os.path.join(self.root, path.lstrip("/")))

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
