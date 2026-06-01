from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from lenslet import preindex
from lenslet.preindex import PreindexResult
from lenslet.server import create_app, create_app_from_datasets
import lenslet.web.factory as server_factory
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
    workspace = Workspace.for_dataset(str(tmp_path), can_write=True)

    def _raise(self) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(
        server_factory,
        "_ensure_preindex_storage",
        lambda *_args, **_kwargs: (None, workspace, None),
    )
    monkeypatch.setattr(Workspace, "ensure", _raise)

    with pytest.raises(RuntimeError, match="failed to initialize workspace: disk full"):
        create_app(str(tmp_path))


def test_preindex_does_not_downgrade_writable_workspace_failures(monkeypatch, tmp_path: Path) -> None:
    _make_image(tmp_path / "sample.jpg")
    workspace = Workspace.for_dataset(str(tmp_path), can_write=True)

    def _raise(self) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Workspace, "ensure", _raise)

    with pytest.raises(OSError, match="disk full"):
        preindex.ensure_local_preindex(tmp_path, workspace)


def test_create_app_raises_when_preindex_build_fails(monkeypatch, tmp_path: Path) -> None:
    _make_image(tmp_path / "sample.jpg")

    def _raise(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(server_factory, "ensure_local_preindex", _raise)

    with pytest.raises(RuntimeError, match="preindex build failed: disk full"):
        create_app(str(tmp_path))


def test_create_app_empty_dataset_falls_back_to_memory_mode(tmp_path: Path) -> None:
    with TestClient(create_app(str(tmp_path))) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["mode"] == "memory"


def test_create_app_raises_when_preindex_reload_returns_no_storage(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _make_image(tmp_path / "sample.jpg")
    workspace = Workspace.for_dataset(str(tmp_path), can_write=True)

    def _result(*_args, **_kwargs) -> PreindexResult:
        return PreindexResult(
            workspace=workspace,
            paths=server_factory.preindex_paths(workspace),
            signature="sig-1",
            image_count=1,
            format="json",
            reused=False,
        )

    monkeypatch.setattr(server_factory, "ensure_local_preindex", _result)
    monkeypatch.setattr(server_factory, "_load_preindex_storage", lambda *_args, **_kwargs: None)

    with pytest.raises(RuntimeError, match="preindex build completed but produced no readable storage"):
        create_app(str(tmp_path))


def test_dataset_factory_rejects_embedding_parquet_path(tmp_path: Path) -> None:
    image_path = tmp_path / "gallery" / "sample.jpg"
    _make_image(image_path)

    with pytest.raises(ValueError, match="embedding search is unavailable in dataset mode"):
        create_app_from_datasets(
            {"demo": [str(image_path)]},
            embedding_parquet_path=str(tmp_path / "items.parquet"),
        )
