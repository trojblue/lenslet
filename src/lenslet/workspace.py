from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Workspace:
    root: Path | None
    can_write: bool

    @classmethod
    def for_dataset(cls, dataset_root: str | None, can_write: bool) -> "Workspace":
        if not dataset_root:
            return cls(root=None, can_write=False)
        return cls(root=Path(dataset_root) / ".lenslet", can_write=can_write)

    def ensure(self) -> None:
        if not self.can_write or self.root is None:
            return
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def views_path(self) -> Path | None:
        return self.root / "views.json" if self.root else None

    def load_views(self) -> dict[str, Any]:
        default = {"version": 1, "views": []}
        path = self.views_path
        if path is None or not path.exists():
            return default
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception as exc:
            print(f"[lenslet] Warning: failed to read views.json: {exc}")
            return default
        if not isinstance(data, dict):
            return default
        views = data.get("views")
        if not isinstance(views, list):
            views = []
        version = data.get("version", 1)
        if not isinstance(version, int):
            version = 1
        return {"version": version, "views": views}

    def write_views(self, payload: dict[str, Any]) -> None:
        if not self.can_write or self.root is None:
            raise PermissionError("workspace is read-only")
        self.ensure()
        path = self.views_path
        if path is None:
            raise PermissionError("workspace is unavailable")
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(path)
