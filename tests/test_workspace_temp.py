from __future__ import annotations

import stat
from pathlib import Path

from lenslet.workspace import Workspace


def test_temp_workspace_uses_private_random_directory(tmp_path: Path) -> None:
    workspace_one = Workspace.for_temp_dataset(tmp_path / "gallery-a")
    workspace_two = Workspace.for_temp_dataset(tmp_path / "gallery-a")

    assert workspace_one.root is not None
    assert workspace_one.root.exists()
    assert workspace_one.root != workspace_two.root
    assert workspace_one.is_temp_workspace() is True

    mode = stat.S_IMODE(workspace_one.root.stat().st_mode)
    assert mode & 0o077 == 0
