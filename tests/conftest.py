from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_user_state(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Detached workspaces live in the user's state directory; keep tests out of the real one."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path_factory.mktemp("xdg-state")))
