from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

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
        with pytest.raises(WorkspaceLockedError, match="another Lenslet process"):
            create_app(str(root))
    finally:
        holder.communicate(input="")
    # The lock dies with its process, so the dataset is writable again.
    create_app(str(root)).state  # noqa: B018 - construction is the assertion


def test_one_process_shares_the_lock_until_every_holder_releases(tmp_path: Path) -> None:
    lock_path = Workspace.for_dataset(str(_dataset(tmp_path)), True).labels_lock_path()
    assert lock_path is not None
    first = acquire_workspace_lock(lock_path)
    second = acquire_workspace_lock(lock_path)
    first.release()
    first.release()  # idempotent: must not drop the second holder's claim
    probe = subprocess.run(
        [sys.executable, "-c", (
            "import fcntl,os,sys; fd=os.open(sys.argv[1], os.O_RDWR);"
            "fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)"
        ), str(lock_path)],
        capture_output=True,
    )
    assert probe.returncode != 0, "lock was released while a holder remained"
    second.release()
    probe = subprocess.run(
        [sys.executable, "-c", (
            "import fcntl,os,sys; fd=os.open(sys.argv[1], os.O_RDWR);"
            "fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)"
        ), str(lock_path)],
        capture_output=True,
    )
    assert probe.returncode == 0


def test_read_only_workspace_takes_no_lock(tmp_path: Path) -> None:
    assert Workspace.for_dataset(str(tmp_path), False).labels_lock_path() is None
