from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, TextIO

from .models import RankingResultEntry

_LOGGER = logging.getLogger(__name__)

# Platform sentinel: importing fcntl is cheap where available and absent on Windows.
fcntl: Any | None
try:
    import fcntl
except ImportError:  # pragma: no cover - windows fallback
    fcntl = None


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

    def append(self, entry: RankingResultEntry) -> None:
        serialized = json.dumps(entry, separators=(",", ":"), ensure_ascii=True)
        self.results_path.parent.mkdir(parents=True, exist_ok=True)
        with self.results_path.open("a+", encoding="utf-8") as handle:
            with _exclusive_lock(handle):
                _ensure_line_boundary(handle)
                handle.write(serialized + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        _fsync_dir(self.results_path.parent)

    def read_entries(self) -> list[RankingResultEntry]:
        if not self.results_path.exists():
            return []
        entries: list[RankingResultEntry] = []
        with self.results_path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    _LOGGER.warning(
                        "Ignoring malformed ranking results entry in %s at line %d: %s",
                        self.results_path,
                        line_number,
                        exc,
                    )
                    continue
                if isinstance(payload, dict):
                    entry = _coerce_result_entry(payload)
                    if entry is not None:
                        entries.append(entry)
        return entries

    def latest_entries_by_instance(self) -> dict[str, RankingResultEntry]:
        latest: dict[str, RankingResultEntry] = {}
        for entry in self.read_entries():
            instance_id = _instance_id_key(entry)
            if instance_id is None:
                continue
            current = latest.get(instance_id)
            if current is None or _is_newer_entry(entry, current):
                latest[instance_id] = entry
        return latest

    def collapsed_entries(self, ordered_instance_ids: Iterable[str]) -> list[RankingResultEntry]:
        latest = self.latest_entries_by_instance()
        ordered_entries: list[RankingResultEntry] = []
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


def _coerce_result_entry(payload: Mapping[str, object]) -> RankingResultEntry | None:
    instance_id = _coerce_nonempty_str(payload.get("instance_id"))
    instance_index = _coerce_required_int(payload.get("instance_index"))
    completed = payload.get("completed")
    if instance_id is None or instance_index is None or not isinstance(completed, bool):
        return None

    entry: RankingResultEntry = {
        "instance_id": instance_id,
        "instance_index": instance_index,
        "completed": completed,
    }
    final_ranks = _coerce_rank_groups(payload.get("final_ranks"))
    if final_ranks is not None:
        entry["final_ranks"] = final_ranks
    missing_image_ids = _coerce_str_list(payload.get("missing_image_ids"))
    if missing_image_ids is not None:
        entry["missing_image_ids"] = missing_image_ids
    started_at = _coerce_nonempty_str(payload.get("started_at"))
    if started_at is not None:
        entry["started_at"] = started_at
    submitted_at = _coerce_nonempty_str(payload.get("submitted_at"))
    if submitted_at is not None:
        entry["submitted_at"] = submitted_at
    duration_ms = _coerce_non_negative_int(payload.get("duration_ms"))
    if duration_ms is not None:
        entry["duration_ms"] = duration_ms
    save_seq = _coerce_non_negative_int(payload.get("save_seq"))
    if save_seq is not None:
        entry["save_seq"] = save_seq
    return entry


def _coerce_nonempty_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _coerce_required_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _coerce_non_negative_int(value: object) -> int | None:
    coerced = _coerce_required_int(value)
    if coerced is None or coerced < 0:
        return None
    return coerced


def _coerce_str_list(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    if not all(isinstance(item, str) for item in value):
        return None
    return list(value)


def _coerce_rank_groups(value: object) -> list[list[str]] | None:
    if not isinstance(value, list):
        return None
    groups: list[list[str]] = []
    for group in value:
        coerced_group = _coerce_str_list(group)
        if coerced_group is None:
            return None
        groups.append(coerced_group)
    return groups


def _instance_id_key(entry: RankingResultEntry) -> str | None:
    return entry["instance_id"] or None


def _entry_save_seq(entry: RankingResultEntry) -> int | None:
    value = entry.get("save_seq")
    return value if isinstance(value, int) and value >= 0 else None


def _is_newer_entry(candidate: RankingResultEntry, current: RankingResultEntry) -> bool:
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
    if not hasattr(os, "O_DIRECTORY"):
        return
    try:
        fd = os.open(os.fspath(path), os.O_RDONLY | os.O_DIRECTORY)
    except OSError as exc:
        _LOGGER.warning("Could not open ranking results directory %s for fsync: %s", path, exc)
        return
    try:
        os.fsync(fd)
    except OSError as exc:
        _LOGGER.warning("Could not fsync ranking results directory %s: %s", path, exc)
    finally:
        os.close(fd)
