from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, TextIO

try:
    import fcntl
except ImportError:  # pragma: no cover - windows fallback
    fcntl = None  # type: ignore[assignment]


class RankingPersistenceError(ValueError):
    """Raised when ranking persistence operations fail validation."""


def resolve_results_path(
    dataset_path: Path,
    image_paths: Iterable[Path],
    override_path: str | Path | None = None,
) -> Path:
    dataset_path = dataset_path.resolve()
    if override_path is None:
        candidate = dataset_path.parent / ".lenslet" / "ranking" / f"{dataset_path.stem}.results.jsonl"
    else:
        raw = Path(override_path).expanduser()
        if not raw.is_absolute():
            raw = dataset_path.parent / raw
        candidate = raw
    resolved = candidate.resolve()
    _validate_results_path(resolved, image_paths)
    return resolved


class RankingResultsStore:
    def __init__(self, results_path: Path) -> None:
        self.results_path = results_path

    def append(self, entry: dict[str, Any]) -> None:
        serialized = json.dumps(entry, separators=(",", ":"), ensure_ascii=True)
        self.results_path.parent.mkdir(parents=True, exist_ok=True)
        with self.results_path.open("a+", encoding="utf-8") as handle:
            with _exclusive_lock(handle):
                _ensure_line_boundary(handle)
                handle.write(serialized + "\n")
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
        _fsync_dir(self.results_path.parent)

    def read_entries(self) -> list[dict[str, Any]]:
        if not self.results_path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with self.results_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    entries.append(payload)
        return entries

    def latest_entries_by_instance(self) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for entry in self.read_entries():
            instance_id = _instance_id_key(entry)
            if instance_id is None:
                continue
            current = latest.get(instance_id)
            if current is None or _is_newer_entry(entry, current):
                latest[instance_id] = entry
        return latest

    def collapsed_entries(self, ordered_instance_ids: Iterable[str]) -> list[dict[str, Any]]:
        latest = self.latest_entries_by_instance()
        ordered_entries: list[dict[str, Any]] = []
        for instance_id in ordered_instance_ids:
            entry = latest.get(instance_id)
            if entry is not None:
                ordered_entries.append(entry)
        return ordered_entries


def _validate_results_path(results_path: Path, image_paths: Iterable[Path]) -> None:
    parent = results_path.parent
    if results_path.is_dir():
        raise RankingPersistenceError(f"results path must be a file path, got directory: {results_path}")
    for image_path in image_paths:
        resolved_image = image_path.resolve()
        if resolved_image == results_path:
            raise RankingPersistenceError("results path cannot point to a served image file")
        if _is_relative_to(resolved_image, parent):
            raise RankingPersistenceError(
                f"results directory must not contain served image files: {parent}",
            )


@contextmanager
def _exclusive_lock(handle: TextIO) -> Iterator[None]:
    if fcntl is None:
        yield
        return
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    try:
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _instance_id_key(entry: dict[str, Any]) -> str | None:
    value = entry.get("instance_id")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _entry_save_seq(entry: dict[str, Any]) -> int | None:
    value = entry.get("save_seq")
    return value if isinstance(value, int) and value >= 0 else None


def _is_newer_entry(candidate: dict[str, Any], current: dict[str, Any]) -> bool:
    candidate_seq = _entry_save_seq(candidate)
    current_seq = _entry_save_seq(current)
    if candidate_seq is None and current_seq is None:
        return True
    if candidate_seq is None:
        return False
    if current_seq is None:
        return True
    return candidate_seq >= current_seq


def _is_relative_to(path: Path, other: Path) -> bool:
    try:
        path.relative_to(other)
        return True
    except ValueError:
        return False


def _ensure_line_boundary(handle: TextIO) -> None:
    handle.seek(0, os.SEEK_END)
    size = handle.tell()
    if size <= 0:
        return
    handle.seek(size - 1, os.SEEK_SET)
    tail = handle.read(1)
    if tail != "\n":
        handle.seek(0, os.SEEK_END)
        handle.write("\n")


def _fsync_dir(path: Path) -> None:
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
