from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_sync_module() -> ModuleType:
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "check_frontend_packaging_sync.py"
    spec = importlib.util.spec_from_file_location("check_frontend_packaging_sync", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load check_frontend_packaging_sync module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_check_sync_passes_for_identical_trees(tmp_path: Path) -> None:
    sync = _load_sync_module()
    dist = tmp_path / "dist"
    packaged = tmp_path / "packaged"

    _write(dist / "index.html", "<html>ok</html>")
    _write(dist / "assets" / "app.js", "console.log('ok')")
    _write(packaged / "index.html", "<html>ok</html>")
    _write(packaged / "assets" / "app.js", "console.log('ok')")

    clean, diff = sync.check_sync(dist, packaged)
    assert clean is True
    assert diff == {"missing": [], "extra": [], "changed": []}


def test_check_sync_reports_missing_extra_and_changed_files(tmp_path: Path) -> None:
    sync = _load_sync_module()
    dist = tmp_path / "dist"
    packaged = tmp_path / "packaged"

    _write(dist / "index.html", "<html>dist</html>")
    _write(dist / "assets" / "app.js", "console.log('dist')")
    _write(packaged / "index.html", "<html>packaged</html>")
    _write(packaged / "assets" / "legacy.js", "console.log('legacy')")

    clean, diff = sync.check_sync(dist, packaged)

    assert clean is False
    assert diff["missing"] == ["assets/app.js"]
    assert diff["extra"] == ["assets/legacy.js"]
    assert diff["changed"] == ["index.html"]
