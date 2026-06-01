from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import logging
import os
import time

from ..image_media import ImageMime


def indexing_reason(exc: BaseException) -> str:
    text = str(exc).strip()
    return text or type(exc).__name__


def local_index_worker_count(
    total: int,
    *,
    max_workers: int,
    cpu_count: Callable[[], int | None],
) -> int:
    if total <= 0:
        return 0
    cpu = cpu_count() or 1
    return max(1, min(max_workers, cpu, total))


class MemoryIndexBuildError(RuntimeError):
    """Raised when a folder index cannot represent its source files honestly."""

    def __init__(self, item_path: str, stage: str, reason: str) -> None:
        self.item_path = item_path
        self.stage = stage
        self.reason = reason
        super().__init__(f"failed to index {item_path} during {stage}: {reason}")

    @classmethod
    def from_exception(
        cls,
        item_path: str,
        stage: str,
        exc: BaseException,
    ) -> "MemoryIndexBuildError":
        return cls(item_path, stage, indexing_reason(exc))


@dataclass
class MemoryBrowseItem:
    """In-memory cached browse facts for an image."""

    path: str
    name: str
    mime: ImageMime
    width: int
    height: int
    size: int
    mtime: float
    url: str | None = None
    source: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class MemoryBrowseIndex:
    """In-memory cached folder index."""

    path: str
    generated_at: str
    items: list[MemoryBrowseItem] = field(default_factory=list)
    dirs: list[str] = field(default_factory=list)


BuiltMemoryItem = tuple[int, MemoryBrowseItem, tuple[int, int] | None]


@dataclass
class IndexBuildState:
    items: list[MemoryBrowseItem | None]
    show_progress: bool
    total: int
    done: int = 0
    last_print: float = 0.0

    @classmethod
    def create(cls, total: int, *, show_progress: bool) -> "IndexBuildState":
        return cls(
            items=[None] * total,
            show_progress=show_progress,
            total=total,
        )

    def consume(
        self,
        result: BuiltMemoryItem,
        *,
        dimensions: dict[str, tuple[int, int]],
        progress: Callable[[int, int, str], None],
    ) -> None:
        idx, item, dims = result
        self.items[idx] = item
        if dims:
            dimensions[item.path] = dims
        self.done += 1
        if not self.show_progress:
            return
        now = time.monotonic()
        if now - self.last_print <= 0.1 and self.done != self.total:
            return
        progress(self.done, self.total, "local")
        self.last_print = now

    def completed_items(self) -> list[MemoryBrowseItem]:
        return [item for item in self.items if item is not None]


def root_entry_signature(entry: os.DirEntry[str]) -> str | None:
    if entry.name.startswith("."):
        return None
    try:
        stat = entry.stat(follow_symlinks=False)
        is_dir = entry.is_dir(follow_symlinks=False)
    except OSError as exc:
        logging.getLogger(__name__).debug(
            "Skipping unreadable root entry %s while computing browse signature: %s",
            entry.name,
            exc,
        )
        return None
    kind = "d" if is_dir else "f"
    return f"{kind}:{entry.name}:{stat.st_mtime_ns}:{stat.st_size}"
