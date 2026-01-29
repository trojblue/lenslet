from __future__ import annotations
import json
import os
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

        def _remember(payload: dict[str, Any]) -> dict[str, Any]:
            if not self.can_write:
                self.memory_views = payload
            return payload

        default = {"version": 1, "views": []}
        path = self.views_path
        if path is None or not path.exists():
            return _remember(default)
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception as exc:
            print(f"[lenslet] Warning: failed to read views.json: {exc}")
            return _remember(default)
        if not isinstance(data, dict):
            return _remember(default)
        views = data.get("views")
        if not isinstance(views, list):
            views = []
        version = data.get("version", 1)
        if not isinstance(version, int):
            version = 1
        payload = {"version": version, "views": views}
        return _remember(payload)

    def save_views(self, payload: dict[str, Any]) -> None:
        if not self.can_write or self.views_path is None:
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

    def embedding_cache_dir(self) -> Path | None:
        if not self.can_write:
            return None
        if self.views_override is not None:
            name = self.views_override.name
            if name.endswith(".lenslet.json"):
                name = name[: -len(".lenslet.json")]
            base = self.views_override.with_name(name)
            return Path(f"{base}.cache") / "embeddings_cache"
        if self.root is None:
            return None
        return self.root / "embeddings_cache"

    def og_cache_dir(self) -> Path | None:
        if not self.can_write:
            return None
        if self.views_override is not None:
            name = self.views_override.name
            if name.endswith(".lenslet.json"):
                name = name[: -len(".lenslet.json")]
            base = self.views_override.with_name(name)
            return Path(f"{base}.cache") / "og-cache"
        if self.root is None:
            return None
        return self.root / "og-cache"

    def labels_log_path(self) -> Path | None:
        if not self.can_write:
            return None
        if self.views_override is not None:
            base = self.views_override.stem
            return self.views_override.with_name(f"{base}.labels.log.jsonl")
        if self.root is None:
            return None
        return self.root / "labels.log.jsonl"

    def labels_snapshot_path(self) -> Path | None:
        if not self.can_write:
            return None
        if self.views_override is not None:
            base = self.views_override.stem
            return self.views_override.with_name(f"{base}.labels.snapshot.json")
        if self.root is None:
            return None
        return self.root / "labels.snapshot.json"

    def read_labels_snapshot(self) -> dict[str, Any] | None:
        path = self.labels_snapshot_path()
        if path is None or not path.exists():
            return None
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception as exc:
            print(f"[lenslet] Warning: failed to read labels snapshot: {exc}")
            return None
        if not isinstance(data, dict):
            return None
        return data

    def write_labels_snapshot(self, payload: dict[str, Any]) -> None:
        path = self.labels_snapshot_path()
        if not self.can_write or path is None:
            raise PermissionError("workspace is read-only")
        self.ensure()
        serialized = json.dumps(payload, indent=2, sort_keys=True)
        self._atomic_write_text(path, serialized)

    def append_labels_log(self, payload: dict[str, Any]) -> None:
        path = self.labels_log_path()
        if not self.can_write or path is None:
            raise PermissionError("workspace is read-only")
        self.ensure()
        line = json.dumps(payload, separators=(",", ":"))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass

    def compact_labels_log(self, last_event_id: int, max_bytes: int = 5_000_000) -> bool:
        path = self.labels_log_path()
        if not self.can_write or path is None or not path.exists():
            return False
        try:
            if max_bytes > 0 and path.stat().st_size < max_bytes:
                return False
        except Exception:
            return False

        keep: list[str] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        data = json.loads(raw)
                    except Exception:
                        continue
                    if not isinstance(data, dict):
                        continue
                    event_id = data.get("id")
                    if isinstance(event_id, int) and event_id <= last_event_id:
                        continue
                    keep.append(json.dumps(data, separators=(",", ":")))
        except Exception as exc:
            print(f"[lenslet] Warning: failed to compact labels log: {exc}")
            return False

        payload = "\n".join(keep)
        if payload:
            payload += "\n"
        try:
            self._atomic_write_text(path, payload)
        except Exception as exc:
            print(f"[lenslet] Warning: failed to write compacted labels log: {exc}")
            return False
        return True

    def read_labels_log(self) -> list[dict[str, Any]]:
        path = self.labels_log_path()
        if path is None or not path.exists():
            return []
        entries: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        data = json.loads(raw)
                    except Exception:
                        continue
                    if isinstance(data, dict):
                        entries.append(data)
        except Exception as exc:
            print(f"[lenslet] Warning: failed to read labels log: {exc}")
        return entries

    def _atomic_write_text(self, path: Path, payload: str) -> None:
        temp = path.with_suffix(".tmp")
        with temp.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
        temp.replace(path)
        self._fsync_dir(path.parent)

    def _fsync_dir(self, path: Path) -> None:
        flags = getattr(os, "O_DIRECTORY", 0)
        try:
            fd = os.open(os.fspath(path), os.O_RDONLY | flags)
        except OSError:
            return
        try:
            os.fsync(fd)
        except OSError:
            pass
        finally:
            os.close(fd)
