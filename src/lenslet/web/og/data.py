from __future__ import annotations

import errno
from collections import deque

from ...storage.base import BrowseStorage


def _reason_text(exc: BaseException) -> str:
    text = str(exc).strip()
    return text or type(exc).__name__


class OgDataUnavailableError(RuntimeError):
    """Raised when OG generation cannot read browse data honestly."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"failed to load OG browse data for {path}: {reason}")

    @classmethod
    def from_exception(cls, path: str, exc: BaseException) -> "OgDataUnavailableError":
        return cls(path, _reason_text(exc))


def normalize_path(path: str | None) -> str:
    if not path:
        return "/"
    cleaned = path.strip()
    if not cleaned:
        return "/"
    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned}"
    if len(cleaned) > 1:
        cleaned = cleaned.rstrip("/")
    return cleaned


def sample_paths(storage: BrowseStorage, path: str | None, count: int) -> list[str]:
    target = normalize_path(path)
    index = load_index_or_none(storage, target)
    if index is None and target != "/":
        target = "/"
        index = load_index_or_none(storage, target)
    if index is None:
        return []

    records = _index_records(index)
    if records:
        return [p for _, p in records[:count]]

    records = _subfolder_records(storage, index, target, count)
    if not records:
        return []
    records.sort(key=lambda rec: (-rec[0], rec[1]))
    return [p for _, p in records[:count]]


def subtree_image_count(storage: BrowseStorage, path: str | None) -> int | None:
    target = normalize_path(path)
    index = load_index_or_none(storage, target)
    if index is None:
        return None

    total = len(getattr(index, "items", []) or [])
    dirs = getattr(index, "dirs", []) or []
    if not dirs:
        return total

    queue = deque(storage.join(target, name) for name in dirs)
    seen: set[str] = {target}
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        sub_index = load_index_or_none(storage, current)
        if sub_index is None:
            continue
        total += len(getattr(sub_index, "items", []) or [])
        sub_dirs = getattr(sub_index, "dirs", []) or []
        for name in sub_dirs:
            queue.append(storage.join(current, name))
    return total


def load_index_or_none(storage: BrowseStorage, path: str):
    try:
        return storage.load_index(path)
    except (FileNotFoundError, ValueError):
        return None
    except OSError as exc:
        if exc.errno in {errno.ENOENT, errno.ENOTDIR}:
            return None
        raise OgDataUnavailableError.from_exception(path, exc) from exc
    except Exception as exc:
        raise OgDataUnavailableError.from_exception(path, exc) from exc


def _index_records(index) -> list[tuple[float, str]]:
    items = getattr(index, "items", [])
    if not items:
        return []
    records: list[tuple[float, str]] = []
    for item in items:
        path = getattr(item, "path", None)
        if not path:
            continue
        mtime = getattr(item, "mtime", 0.0) or 0.0
        records.append((mtime, path))
    records.sort(key=lambda rec: (-rec[0], rec[1]))
    return records


def _subfolder_records(storage, index, base_path: str, count: int) -> list[tuple[float, str]]:
    dirs = getattr(index, "dirs", []) or []
    if not dirs:
        return []

    queue = deque()
    for name in dirs:
        queue.append(storage.join(base_path, name))

    records: list[tuple[float, str]] = []
    seen: set[str] = set()
    while queue and len(records) < count:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        sub_index = load_index_or_none(storage, current)
        if sub_index is None:
            continue
        sub_records = _index_records(sub_index)
        if sub_records:
            records.extend(sub_records)
            if len(records) >= count:
                break
        sub_dirs = getattr(sub_index, "dirs", []) or []
        for name in sub_dirs:
            queue.append(storage.join(current, name))
    return records
