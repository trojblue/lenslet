from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias


TableSourceRefreshState: TypeAlias = Literal[
    "current",
    "refreshing",
    "stale",
    "restart-required",
]

TABLE_SOURCE_CHANGED_MESSAGE = "The source table changed; restart Lenslet to load the new snapshot."


class TableSourceChangedError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TableSourceRefreshStatus:
    state: TableSourceRefreshState
    generation: str | None
    message: str | None = None

    def event_payload(self) -> dict[str, str | None]:
        return {
            "state": self.state,
            "generation": self.generation,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class _LocalSourceFingerprint:
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int
    sample_digest: str

    @property
    def generation(self) -> str:
        raw = ":".join(str(value) for value in (
            self.device,
            self.inode,
            self.size,
            self.modified_ns,
            self.changed_ns,
            self.sample_digest,
        ))
        return hashlib.sha256(raw.encode("ascii")).hexdigest()[:24]


class TableSourceRefreshTracker:
    def __init__(
        self,
        *,
        path: Path | None,
        fingerprint: _LocalSourceFingerprint | None,
        status: TableSourceRefreshStatus,
    ) -> None:
        self._path = path
        self._fingerprint = fingerprint
        self._status = status
        self._lock = threading.Lock()
        self._pending_transition = False

    @classmethod
    def for_local_file(cls, path: Path) -> TableSourceRefreshTracker:
        watched_path = path.absolute()
        fingerprint = _fingerprint(watched_path)
        return cls(
            path=watched_path,
            fingerprint=fingerprint,
            status=TableSourceRefreshStatus(
                state="current",
                generation=fingerprint.generation,
            ),
        )

    @classmethod
    def restart_required(cls, message: str) -> TableSourceRefreshTracker:
        return cls(
            path=None,
            fingerprint=None,
            status=TableSourceRefreshStatus(
                state="restart-required",
                generation=None,
                message=message,
            ),
        )

    def status(self) -> TableSourceRefreshStatus:
        with self._lock:
            return self._status

    def is_pollable(self) -> bool:
        with self._lock:
            return (
                self._path is not None
                and self._fingerprint is not None
                and (self._status.state == "current" or self._pending_transition)
            )

    def ensure_current(self) -> None:
        status = self._refresh_status()
        if status.state != "current":
            raise TableSourceChangedError(
                status.message or "The source table is not current; restart Lenslet to reload it."
            )

    def poll(self) -> tuple[TableSourceRefreshStatus, bool]:
        status = self._refresh_status()
        with self._lock:
            changed = self._pending_transition
            self._pending_transition = False
        return status, changed

    def _refresh_status(self) -> TableSourceRefreshStatus:
        with self._lock:
            if self._status.state == "restart-required":
                return self._status
            current_status = self._status
        path = self._path
        fingerprint = self._fingerprint
        if path is None or fingerprint is None:
            return current_status
        try:
            observed = _fingerprint(path)
        except OSError:
            next_status = TableSourceRefreshStatus(
                state="restart-required",
                generation=fingerprint.generation,
                message="The source table is unavailable; restart Lenslet after restoring it.",
            )
        else:
            if observed == fingerprint:
                next_status = TableSourceRefreshStatus(
                    state="current",
                    generation=fingerprint.generation,
                )
            else:
                next_status = TableSourceRefreshStatus(
                    state="restart-required",
                    generation=fingerprint.generation,
                    message=TABLE_SOURCE_CHANGED_MESSAGE,
                )
        with self._lock:
            if self._status.state == "restart-required":
                return self._status
            if next_status != self._status:
                self._status = next_status
                self._pending_transition = True
            return self._status


def _fingerprint(path: Path) -> _LocalSourceFingerprint:
    stat = path.stat()
    sample_digest = _sample_digest(path, stat.st_size)
    stat = path.stat()
    return _LocalSourceFingerprint(
        device=stat.st_dev,
        inode=stat.st_ino,
        size=stat.st_size,
        modified_ns=stat.st_mtime_ns,
        changed_ns=stat.st_ctime_ns,
        sample_digest=sample_digest,
    )


def _sample_digest(path: Path, size: int) -> str:
    digest = hashlib.sha256()
    sample_size = 4_096
    offsets = {
        min(max(0, size - sample_size), (size * index) // 7)
        for index in range(8)
    }
    with path.open("rb") as handle:
        for offset in sorted(offsets):
            handle.seek(offset)
            digest.update(offset.to_bytes(8, "little", signed=False))
            digest.update(handle.read(sample_size))
    return digest.hexdigest()[:24]
