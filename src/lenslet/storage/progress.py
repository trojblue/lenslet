from __future__ import annotations

from dataclasses import dataclass, field
import threading
from typing import Callable

from tqdm import tqdm


class ProgressBar:
    """Thread-safe wrapper for a single tqdm progress bar."""

    def __init__(self) -> None:
        self._bar: tqdm | None = None
        self._last_done = 0
        self._last_label: str | None = None
        self._last_total: int | None = None
        self._lock = threading.Lock()

    def update(self, done: int, total: int, label: str) -> None:
        if total <= 0:
            return
        with self._lock:
            if (
                self._bar is None
                or self._last_label != label
                or self._last_total != total
            ):
                if self._bar is not None:
                    self._bar.close()
                desc = "[lenslet] Indexing"
                if label:
                    desc = f"[lenslet] Indexing ({label})"
                self._bar = tqdm(total=total, desc=desc, unit="img", leave=True)
                self._last_done = 0
                self._last_label = label
                self._last_total = total

            delta = done - self._last_done
            if delta > 0 and self._bar is not None:
                self._bar.update(delta)
                self._last_done = done

            if done >= total and self._bar is not None:
                self._bar.close()
                self._bar = None


@dataclass
class LeafBatch:
    """Track aggregate progress for many leaf folders."""

    parent: str
    total: int
    leaf_paths: set[str]
    done: int = 0
    seen: set[str] = field(default_factory=set)
    bar: tqdm | None = None


class LeafBatchTracker:
    """Aggregate tqdm progress across many leaf folder indexes."""

    def __init__(
        self,
        threshold: int,
        list_dir: Callable[[str], tuple[list[str], list[str]]],
        join: Callable[..., str],
        normalize_path: Callable[[str], str],
        display_path: Callable[[str], str],
        index_exists: Callable[[str], bool],
    ) -> None:
        self._threshold = threshold
        self._list_dir = list_dir
        self._join = join
        self._normalize_path = normalize_path
        self._display_path = display_path
        self._index_exists = index_exists
        self._batches: dict[str, LeafBatch] = {}
        self._checked: set[str] = set()
        self._lock = threading.Lock()

    def maybe_prepare(self, path: str, dirs: list[str]) -> None:
        if len(dirs) <= self._threshold:
            return
        parent = self._normalize_path(path)
        with self._lock:
            if parent in self._batches or parent in self._checked:
                return

        leaf_paths: list[str] = []
        for name in dirs:
            child = self._join(path, name) if path else name
            try:
                _, child_dirs = self._list_dir(child)
            except Exception:
                continue
            if not child_dirs:
                leaf_paths.append(self._normalize_path(child))

        if len(leaf_paths) <= self._threshold:
            with self._lock:
                self._checked.add(parent)
            return

        with self._lock:
            if parent in self._batches or parent in self._checked:
                return
            seen = {p for p in leaf_paths if self._index_exists(p)}
            total = len(leaf_paths)
            if len(seen) >= total:
                self._checked.add(parent)
                return
            self._batches[parent] = LeafBatch(
                parent=parent,
                total=total,
                leaf_paths=set(leaf_paths),
                done=len(seen),
                seen=seen,
            )
            self._checked.add(parent)

    def use_batch(self, norm: str, dirs: list[str]) -> bool:
        if dirs:
            return False
        parent = self._parent_norm(norm)
        with self._lock:
            batch = self._batches.get(parent)
            return bool(batch and norm in batch.leaf_paths)

    def update(self, norm: str) -> None:
        parent = self._parent_norm(norm)
        display = self._display_path(norm)
        with self._lock:
            batch = self._batches.get(parent)
            if not batch or norm not in batch.leaf_paths or norm in batch.seen:
                return
            batch.seen.add(norm)
            batch.done += 1
            curr = batch.done
            desc = f"updating folder: {display} ({curr}/{batch.total})"
            if batch.bar is None:
                batch.bar = tqdm(
                    total=batch.total,
                    desc=desc,
                    unit="folder",
                    leave=True,
                    initial=curr - 1,
                )
            else:
                batch.bar.set_description(desc)
            batch.bar.update(1)
            if batch.done >= batch.total:
                batch.bar.close()
                batch.bar = None
                self._batches.pop(parent, None)

    def clear(self) -> None:
        with self._lock:
            for batch in self._batches.values():
                if batch.bar is not None:
                    batch.bar.close()
            self._batches.clear()
            self._checked.clear()

    @staticmethod
    def _parent_norm(norm: str) -> str:
        if not norm or "/" not in norm:
            return ""
        return norm.rsplit("/", 1)[0]
