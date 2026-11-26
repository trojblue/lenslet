"""Single-writer guard for a workspace's label files.

Label event ids, snapshots and log compaction assume one writing process per
workspace. A second Lenslet process on the same files would reuse event ids and
overwrite the other's snapshot, silently losing labels on reload. Holders in one
process share the OS lock so runtime swaps (refresh, workspace rebinding) can
open the next writer before closing the previous one.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

fcntl: Any | None
try:  # pragma: no cover - platform sentinel
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None


class WorkspaceLockedError(RuntimeError):
    """Another process is already writing labels for this workspace."""


@dataclass(slots=True)
class _HeldLock:
    fd: int
    holders: int


_held: dict[Path, _HeldLock] = {}
_held_guard = threading.Lock()


class WorkspaceLease:
    """One holder's claim on a workspace label lock; release is idempotent."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._released = False

    def release(self) -> None:
        with _held_guard:
            if self._released:
                return
            self._released = True
            held = _held.get(self.path)
            if held is None:
                return
            held.holders -= 1
            if held.holders > 0:
                return
            del _held[self.path]
            os.close(held.fd)  # closing the descriptor drops the flock


def acquire_workspace_lock(path: Path) -> WorkspaceLease:
    key = path.resolve()
    with _held_guard:
        held = _held.get(key)
        if held is None:
            _held[key] = _HeldLock(fd=_lock_file(key), holders=1)
        else:
            held.holders += 1
    return WorkspaceLease(key)


def _lock_file(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    if fcntl is None:
        return fd
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(fd)
        raise WorkspaceLockedError(
            f"another Lenslet process is already writing labels at {path.parent}; "
            "stop it before starting a second server on the same dataset",
        ) from exc
    except BaseException:
        os.close(fd)
        raise
    return fd
