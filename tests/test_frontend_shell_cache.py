from __future__ import annotations

import time
from pathlib import Path

from lenslet.web.frontend import load_frontend_shell


def test_load_frontend_shell_reloads_when_mtime_changes(tmp_path: Path) -> None:
    index_path = tmp_path / "index.html"
    index_path.write_text("<html>first</html>", encoding="utf-8")
    first_mtime = index_path.stat().st_mtime_ns

    first = load_frontend_shell(str(index_path), first_mtime)

    time.sleep(0.01)
    index_path.write_text("<html>second</html>", encoding="utf-8")
    second_mtime = index_path.stat().st_mtime_ns

    second = load_frontend_shell(str(index_path), second_mtime)

    assert first == "<html>first</html>"
    assert second == "<html>second</html>"
