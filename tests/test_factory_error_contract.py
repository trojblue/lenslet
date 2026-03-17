from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from lenslet.server import create_app, create_app_from_datasets
from lenslet.workspace import Workspace


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color=(50, 100, 150)).save(path, format="JPEG")


def test_create_app_raises_when_items_parquet_is_invalid(tmp_path: Path) -> None:
    _make_image(tmp_path / "gallery" / "sample.jpg")
    (tmp_path / "items.parquet").write_text("not a parquet file", encoding="utf-8")

    with pytest.raises(RuntimeError, match="failed to initialize table dataset"):
        create_app(str(tmp_path))


def test_create_app_raises_when_workspace_init_fails(monkeypatch, tmp_path: Path) -> None:
    _make_image(tmp_path / "sample.jpg")

    def _raise(self) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Workspace, "ensure", _raise)

    with pytest.raises(RuntimeError, match="failed to initialize workspace: disk full"):
        create_app(str(tmp_path))


def test_dataset_factory_rejects_embedding_parquet_path(tmp_path: Path) -> None:
    image_path = tmp_path / "gallery" / "sample.jpg"
    _make_image(image_path)

    with pytest.raises(ValueError, match="embedding search is unavailable in dataset mode"):
        create_app_from_datasets(
            {"demo": [str(image_path)]},
            embedding_parquet_path=str(tmp_path / "items.parquet"),
        )
