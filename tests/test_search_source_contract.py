from __future__ import annotations

from pathlib import Path
from typing import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from lenslet.server import create_app_from_datasets, create_app_from_storage
from lenslet.storage.dataset import DatasetStorage
from lenslet.storage.table import TableStorage


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (10, 8), color=(40, 88, 132)).save(path, format="JPEG")


def _search_paths(client: TestClient, *, query: str, path: str = "/") -> set[str]:
    response = client.get("/search", params={"q": query, "path": path})
    assert response.status_code == 200
    return {item["path"] for item in response.json()["items"]}


def _build_table_app(
    root: Path,
    include_source_in_search: bool,
    _monkeypatch: pytest.MonkeyPatch,
) -> FastAPI:
    local_source = root / "source-token" / "local.jpg"
    _make_image(local_source)
    rows = [
        {"path": "gallery/local.jpg", "source": str(local_source)},
        {"path": "gallery/remote.jpg", "source": "https://cdn.example.com/media/remote.jpg"},
    ]
    storage = TableStorage(
        rows,
        root=None,
        include_source_in_search=include_source_in_search,
        skip_indexing=True,
    )
    return create_app_from_storage(storage, show_source=include_source_in_search)


def _build_dataset_app(
    root: Path,
    include_source_in_search: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> FastAPI:
    local_source = root / "source-token" / "local.jpg"
    _make_image(local_source)
    datasets = {
        "gallery": [
            str(local_source),
            "https://cdn.example.com/media/remote.jpg",
        ],
    }
    monkeypatch.setattr(DatasetStorage, "_probe_remote_dimensions", lambda self, tasks, label: None)
    return create_app_from_datasets(datasets, show_source=include_source_in_search)


AppBuilder = Callable[[Path, bool, pytest.MonkeyPatch], FastAPI]


@pytest.mark.parametrize(
    "build_app",
    [
        pytest.param(_build_table_app, id="table"),
        pytest.param(_build_dataset_app, id="dataset"),
    ],
)
def test_search_route_source_token_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    build_app: AppBuilder,
) -> None:
    enabled_app = build_app(tmp_path / "enabled", True, monkeypatch)
    disabled_app = build_app(tmp_path / "disabled", False, monkeypatch)

    with TestClient(enabled_app) as client:
        assert "/gallery/local.jpg" in _search_paths(client, query="source-token")
        assert "/gallery/remote.jpg" in _search_paths(client, query="cdn.example.com")
        assert "/gallery/local.jpg" in _search_paths(client, query="source-token", path="/gallery")
        assert "/gallery/local.jpg" not in _search_paths(client, query="source-token", path="/outside")

    with TestClient(disabled_app) as client:
        assert "/gallery/local.jpg" not in _search_paths(client, query="source-token")
        assert "/gallery/remote.jpg" not in _search_paths(client, query="cdn.example.com")
        assert "/gallery/local.jpg" in _search_paths(client, query="gallery/local.jpg")
