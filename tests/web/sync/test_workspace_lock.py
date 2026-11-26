from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from fastapi.testclient import TestClient

from lenslet.server import create_app
from lenslet.workspace import Workspace
from lenslet.workspace_lock import WorkspaceLockedError, acquire_workspace_lock

_HOLD_LOCK = """
import sys
from lenslet.workspace import Workspace
from lenslet.workspace_lock import acquire_workspace_lock
acquire_workspace_lock(Workspace.for_dataset(sys.argv[1], True).labels_lock_path())
print("held", flush=True)
sys.stdin.read()
"""


def _dataset(tmp_path: Path) -> Path:
    Image.new("RGB", (8, 6)).save(tmp_path / "a.jpg", "JPEG")
    return tmp_path


def test_second_process_cannot_write_labels_for_the_same_dataset(tmp_path: Path) -> None:
    root = _dataset(tmp_path)
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    holder = subprocess.Popen(
        [sys.executable, "-c", _HOLD_LOCK, str(root)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env,
    )
    try:
        assert holder.stdout is not None and holder.stdout.readline().strip() == "held"
        with pytest.raises(WorkspaceLockedError, match="another Lenslet server"):
            create_app(str(root))
    finally:
        holder.communicate(input="")
    # The lock dies with its process, so the dataset is writable again.
    create_app(str(root)).state  # noqa: B018 - construction is the assertion


def test_second_app_in_the_same_process_cannot_write_labels(tmp_path: Path) -> None:
    root = _dataset(tmp_path)
    with TestClient(create_app(str(root))) as first:
        assert first.get("/health").status_code == 200
        with pytest.raises(WorkspaceLockedError, match="another Lenslet server"):
            create_app(str(root))
    # Shutting the first app down releases its claim.
    with TestClient(create_app(str(root))) as second:
        assert second.get("/health").status_code == 200


def test_lease_release_is_idempotent(tmp_path: Path) -> None:
    lock_path = Workspace.for_dataset(str(_dataset(tmp_path)), True).labels_lock_path()
    assert lock_path is not None
    lease = acquire_workspace_lock(lock_path)
    with pytest.raises(WorkspaceLockedError):
        acquire_workspace_lock(lock_path)
    lease.release()
    lease.release()
    acquire_workspace_lock(lock_path).release()


def test_read_only_workspace_takes_no_lock(tmp_path: Path) -> None:
    assert Workspace.for_dataset(str(tmp_path), False).labels_lock_path() is None
