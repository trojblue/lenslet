from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Workspace:
    root: Path | None
    can_write: bool
    memory_views: dict[str, Any] | None = None
    views_override: Path | None = None

    @classmethod
    def for_dataset(cls, dataset_root: str | None, can_write: bool) -> "Workspace":
        if not dataset_root:
            return cls(root=None, can_write=False)
        return cls(root=Path(dataset_root) / ".lenslet", can_write=can_write)

    @classmethod
    def for_parquet(cls, parquet_path: str | Path | None, can_write: bool) -> "Workspace":
        if not parquet_path:
            return cls(root=None, can_write=False)
        path = Path(parquet_path)
        sidecar = Path(f"{path}.lenslet.json")
        return cls(root=None, can_write=can_write, views_override=sidecar)

    def ensure(self) -> None:
        if not self.can_write or self.root is None:
            if self.can_write and self.views_override is not None:
                self.views_override.parent.mkdir(parents=True, exist_ok=True)
            return
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def views_path(self) -> Path | None:
        if self.views_override is not None:
            return self.views_override
        return self.root / "views.json" if self.root else None

    def load_views(self) -> dict[str, Any]:
        if not self.can_write and self.memory_views is not None:
            return self.memory_views
        default = {"version": 1, "views": []}
        path = self.views_path
        if path is None or not path.exists():
            if not self.can_write:
                self.memory_views = default
            return default
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception as exc:
            print(f"[lenslet] Warning: failed to read views.json: {exc}")
            if not self.can_write:
                self.memory_views = default
            return default
        if not isinstance(data, dict):
            if not self.can_write:
                self.memory_views = default
            return default
        views = data.get("views")
        if not isinstance(views, list):
            views = []
        version = data.get("version", 1)
        if not isinstance(version, int):
            version = 1
        payload = {"version": version, "views": views}
        if not self.can_write:
            self.memory_views = payload
        return payload

    def save_views(self, payload: dict[str, Any]) -> None:
        if not self.can_write:
            self.memory_views = payload
            return
        if self.views_path is None:
            self.memory_views = payload
            return
        self.write_views(payload)

    def write_views(self, payload: dict[str, Any]) -> None:
        path = self.views_path
        if not self.can_write or path is None:
            raise PermissionError("workspace is read-only")
        self.ensure()
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(path)

    def thumb_cache_dir(self) -> Path | None:
        if not self.can_write:
            return None
        if self.views_override is not None:
            name = self.views_override.name
            if name.endswith(".lenslet.json"):
                name = name[: -len(".lenslet.json")]
            base = self.views_override.with_name(name)
            return Path(f"{base}.cache") / "thumbs"
        if self.root is None:
            return None
        return self.root / "thumbs"
