"""Single-writer guard for a workspace's label files.

Label event ids, snapshots and log compaction assume exactly one label writer
per workspace. A second writer, in another process or in the same one, would
reuse event ids and overwrite the other's snapshot, silently losing labels on
reload. Each writer therefore holds its own exclusive lock on its own open file
description, which conflicts with every other holder, including in-process ones.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

fcntl: Any | None
try:  # pragma: no cover - platform sentinel
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None


class WorkspaceLockedError(RuntimeError):
    """Another label writer already holds this workspace."""


class WorkspaceLease:
    """One writer's exclusive claim on a workspace label lock; release is idempotent."""

    def __init__(self, path: Path, fd: int) -> None:
        self.path = path
        self._fd: int | None = fd
        self._guard = threading.Lock()

    def release(self) -> None:
        with self._guard:
            fd, self._fd = self._fd, None
        if fd is not None:
            os.close(fd)  # closing the descriptor drops the flock


def acquire_workspace_lock(path: Path) -> WorkspaceLease:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    if fcntl is None:
        return WorkspaceLease(path, fd)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(fd)
        raise WorkspaceLockedError(
            f"another Lenslet server is already writing labels at {path.parent}; "
            "stop it before starting a second server on the same dataset",
        ) from exc
    except BaseException:
        os.close(fd)
        raise
    return WorkspaceLease(path, fd)
