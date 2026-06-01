from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from PIL import Image

from lenslet.storage.local.preindex import ensure_local_preindex
import lenslet.storage.table.launch as table_launch_module
import lenslet.web.app.factory as server_factory
import lenslet.web.app.local as local_app
from lenslet.workspace import Workspace


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (12, 9), color=(24, 64, 96)).save(path, format="JPEG")


def test_preindex_storage_uses_strict_local_validation(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "gallery"
    _make_image(root / "a.jpg")

    workspace = Workspace.for_dataset(str(root), can_write=True)
    preindex = ensure_local_preindex(root, workspace)
    assert preindex is not None

    captured: dict = {}

    class SpyTableStorage:
        def __init__(self, *args, **kwargs):
            _ = args
            captured.update(kwargs)

    monkeypatch.setattr(local_app, "TableStorage", SpyTableStorage)

    storage = local_app.load_preindex_storage(
        str(root),
        preindex.workspace,
        thumb_size=256,
        thumb_quality=70,
        skip_dimension_probe=False,
        preindex_signature=preindex.signature,
    )

    assert storage is not None
    assert captured["options"].skip_local_realpath_validation is False


def test_create_app_folder_items_parquet_uses_strict_local_validation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "gallery"
    _make_image(root / "a.jpg")
    table = pa.table({"source": ["a.jpg"], "path": ["a.jpg"]})
    pq.write_table(table, root / "items.parquet")

    captured: dict = {}

    class SpyTableStorage:
        def __init__(self, *args, **kwargs):
            _ = args
            captured.update(kwargs)

        def row_dimensions(self):
            return {}

        def load_index(self, path: str):
            _ = path
            return None

    monkeypatch.setattr(table_launch_module, "TableStorage", SpyTableStorage)
    app = server_factory.create_app(str(root))
    assert app is not None
    assert captured["options"].skip_local_realpath_validation is False


def test_preindex_storage_reports_symlink_target_outside_root(
    tmp_path: Path,
    capsys,
) -> None:
    root = tmp_path / "gallery"
    outside = tmp_path / "source-images" / "a.jpg"
    symlink = root / "linked" / "a.jpg"
    _make_image(outside)
    symlink.parent.mkdir(parents=True, exist_ok=True)
    symlink.symlink_to(outside)

    workspace = Workspace.for_dataset(str(root), can_write=True)
    preindex = ensure_local_preindex(root, workspace)
    assert preindex is not None
    capsys.readouterr()

    storage = local_app.load_preindex_storage(
        str(root),
        preindex.workspace,
        thumb_size=256,
        thumb_quality=70,
        skip_dimension_probe=False,
        preindex_signature=preindex.signature,
    )

    captured = capsys.readouterr()
    assert storage is not None
    assert storage.total_items() == 0
    assert "inside base_dir but resolve outside it" in captured.out
    assert "symlinks point outside the launched directory" in captured.out


def test_preindex_reports_scan_phase(
    tmp_path: Path,
    capsys,
) -> None:
    root = tmp_path / "gallery"
    _make_image(root / "a.jpg")
    workspace = Workspace.for_dataset(str(root), can_write=True)

    class SilentProgress:
        def update(self, done: int, total: int, label: str) -> None:
            _ = (done, total, label)

    result = ensure_local_preindex(root, workspace, progress=SilentProgress())
    assert result is not None
    captured = capsys.readouterr()
    assert "[lenslet] Scanning files..." in captured.out
