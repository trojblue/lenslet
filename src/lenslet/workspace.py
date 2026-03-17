from __future__ import annotations
import json
import os
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Generic, TypeVar


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class WorkspaceReadResult(Generic[T]):
    status: str
    value: T
    detail: str | None = None
    invalid_entries: int = 0

    @property
    def has_issue(self) -> bool:
        return self.status in {"invalid", "error", "partial"}


@dataclass
class Workspace:
    root: Path | None
    can_write: bool
    memory_views: dict[str, Any] | None = None
    views_override: Path | None = None
    is_temp: bool = False

    TEMP_ROOT = Path("/tmp/lenslet")

    @staticmethod
    def dataset_cache_key(dataset_root: str | Path) -> str:
        root = Path(dataset_root).resolve()
        digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()
        return digest

    @classmethod
    def for_temp_dataset(cls, dataset_root: str | Path) -> "Workspace":
        key = cls.dataset_cache_key(dataset_root)
        root = cls.TEMP_ROOT / key
        return cls(root=root, can_write=True, is_temp=True)

    def is_temp_workspace(self) -> bool:
        return self.is_temp

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

    def preindex_dir(self) -> Path | None:
        if self.root is None:
            return None
        return self.root / "preindex"

    def _views_override_cache_base(self) -> Path | None:
        if self.views_override is None:
            return None
        name = self.views_override.name
        if name.endswith(".lenslet.json"):
            name = name[: -len(".lenslet.json")]
        return self.views_override.with_name(name)

    def _views_override_cache_dir(self, suffix: str) -> Path | None:
        base = self._views_override_cache_base()
        if base is None:
            return None
        return Path(f"{base}.cache") / suffix

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

        result = self.load_views_result()
        if result.has_issue:
            self._warn_read_issue("views", self.views_path, result)
        return _remember(result.value)

    def load_views_result(self) -> WorkspaceReadResult[dict[str, Any]]:
        if not self.can_write and self.memory_views is not None:
            return WorkspaceReadResult(status="ok", value=self.memory_views)

        default = {"version": 1, "views": []}
        path = self.views_path
        if path is None or not path.exists():
            return WorkspaceReadResult(status="missing", value=default)
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            return WorkspaceReadResult(status="invalid", value=default, detail=str(exc))
        except OSError as exc:
            return WorkspaceReadResult(status="error", value=default, detail=str(exc))
        if not isinstance(data, dict):
            return WorkspaceReadResult(
                status="invalid",
                value=default,
                detail="views payload must be a JSON object",
            )
        views = data.get("views")
        if not isinstance(views, list):
            return WorkspaceReadResult(
                status="invalid",
                value=default,
                detail="views payload must contain a list under 'views'",
            )
        version = data.get("version", 1)
        if not isinstance(version, int):
            return WorkspaceReadResult(
                status="invalid",
                value=default,
                detail="views payload must contain an integer 'version'",
            )
        return WorkspaceReadResult(
            status="ok",
            value={"version": version, "views": views},
        )

    def ensure_writable(self) -> None:
        if not self.can_write:
            raise PermissionError("workspace is read-only")

    def save_views(self, payload: dict[str, Any]) -> None:
        self.write_views(payload)

    def write_views(self, payload: dict[str, Any]) -> None:
        path = self.views_path
        self.ensure_writable()
        if path is None:
            raise PermissionError("workspace is read-only")
        self.ensure()
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temp.replace(path)

    def thumb_cache_dir(self) -> Path | None:
        if not self.can_write:
            return None
        override_dir = self._views_override_cache_dir("thumbs")
        if override_dir is not None:
            return override_dir
        if self.root is None:
            return None
        return self.root / "thumbs"

    def browse_cache_dir(self) -> Path | None:
        if not self.can_write:
            return None
        override_dir = self._views_override_cache_dir("browse-cache")
        if override_dir is not None:
            return override_dir
        if self.root is None:
            return None
        return self.root / "browse-cache"

    def embedding_cache_dir(self) -> Path | None:
        if not self.can_write:
            return None
        override_dir = self._views_override_cache_dir("embeddings_cache")
        if override_dir is not None:
            return override_dir
        if self.root is None:
            return None
        return self.root / "embeddings_cache"

    def og_cache_dir(self) -> Path | None:
        if not self.can_write:
            return None
        override_dir = self._views_override_cache_dir("og-cache")
        if override_dir is not None:
            return override_dir
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
        result = self.read_labels_snapshot_result()
        if result.has_issue:
            self._warn_read_issue("labels snapshot", self.labels_snapshot_path(), result)
        return result.value

    def read_labels_snapshot_result(self) -> WorkspaceReadResult[dict[str, Any] | None]:
        path = self.labels_snapshot_path()
        if path is None or not path.exists():
            return WorkspaceReadResult(status="missing", value=None)
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            return WorkspaceReadResult(status="invalid", value=None, detail=str(exc))
        except OSError as exc:
            return WorkspaceReadResult(status="error", value=None, detail=str(exc))
        if not isinstance(data, dict):
            return WorkspaceReadResult(
                status="invalid",
                value=None,
                detail="labels snapshot must be a JSON object",
            )
        items = data.get("items", {})
        last_event_id = data.get("last_event_id", 0)
        version = data.get("version", 1)
        if not isinstance(items, dict):
            return WorkspaceReadResult(
                status="invalid",
                value=None,
                detail="labels snapshot 'items' must be a JSON object",
            )
        if not isinstance(last_event_id, int):
            return WorkspaceReadResult(
                status="invalid",
                value=None,
                detail="labels snapshot 'last_event_id' must be an integer",
            )
        if not isinstance(version, int):
            return WorkspaceReadResult(
                status="invalid",
                value=None,
                detail="labels snapshot 'version' must be an integer",
            )
        return WorkspaceReadResult(
            status="ok",
            value={
                "version": version,
                "last_event_id": last_event_id,
                "items": items,
            },
        )

    def write_labels_snapshot(self, payload: dict[str, Any]) -> None:
        path = self.labels_snapshot_path()
        self.ensure_writable()
        if path is None:
            raise PermissionError("workspace is read-only")
        self.ensure()
        serialized = json.dumps(payload, indent=2, sort_keys=True)
        self._atomic_write_text(path, serialized)

    def append_labels_log(self, payload: dict[str, Any]) -> None:
        path = self.labels_log_path()
        self.ensure_writable()
        if path is None:
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
        result = self.read_labels_log_result()
        if result.has_issue:
            self._warn_read_issue("labels log", self.labels_log_path(), result)
        return result.value

    def read_labels_log_result(self) -> WorkspaceReadResult[list[dict[str, Any]]]:
        path = self.labels_log_path()
        if path is None or not path.exists():
            return WorkspaceReadResult(status="missing", value=[])
        entries: list[dict[str, Any]] = []
        invalid_entries = 0
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        invalid_entries += 1
                        continue
                    if isinstance(data, dict):
                        entries.append(data)
                        continue
                    invalid_entries += 1
        except OSError as exc:
            return WorkspaceReadResult(status="error", value=[], detail=str(exc))
        if invalid_entries:
            return WorkspaceReadResult(
                status="partial",
                value=entries,
                detail=f"ignored {invalid_entries} malformed log entr{'y' if invalid_entries == 1 else 'ies'}",
                invalid_entries=invalid_entries,
            )
        return WorkspaceReadResult(status="ok", value=entries)

    def _warn_read_issue(
        self,
        label: str,
        path: Path | None,
        result: WorkspaceReadResult[Any],
    ) -> None:
        if not result.has_issue:
            return
        location = str(path) if path is not None else "<memory>"
        detail = result.detail or result.status
        print(f"[lenslet] Warning: failed to read {label} at {location}: {detail}")

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
