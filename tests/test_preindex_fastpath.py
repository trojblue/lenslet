from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from PIL import Image

from lenslet.preindex import ensure_local_preindex
from lenslet import server_factory
from lenslet.workspace import Workspace


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (12, 9), color=(24, 64, 96)).save(path, format="JPEG")


def test_preindex_storage_uses_fast_local_validation(tmp_path: Path, monkeypatch) -> None:
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

    monkeypatch.setattr(server_factory, "TableStorage", SpyTableStorage)

    storage = server_factory._load_preindex_storage(
        str(root),
        preindex.workspace,
        thumb_size=256,
        thumb_quality=70,
        skip_indexing=False,
        preindex_signature=preindex.signature,
    )

    assert storage is not None
    assert captured.get("skip_local_realpath_validation") is True


def test_create_app_folder_items_parquet_uses_fast_local_validation(
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

        def get_index(self, path: str):
            _ = path
            return None

    monkeypatch.setattr(server_factory, "TableStorage", SpyTableStorage)
    app = server_factory.create_app(str(root))
    assert app is not None
    assert captured.get("skip_local_realpath_validation") is True
