from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from lenslet.server import create_app
from lenslet.web.factory import create_app_from_storage
from lenslet.storage.memory import MemoryStorage


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color=(32, 96, 160)).save(path, format="JPEG")


def test_og_route_rejects_unknown_style(tmp_path: Path) -> None:
    _make_image(tmp_path / "gallery" / "a.jpg")

    app = create_app(str(tmp_path), og_preview=True)
    with TestClient(app) as client:
        response = client.get("/og-image", params={"style": "unknown-style"})

    assert response.status_code == 400
    assert "unsupported style" in response.json()["detail"]


def test_og_route_returns_fallback_image_for_empty_dataset(tmp_path: Path) -> None:
    app = create_app(str(tmp_path), og_preview=True)

    with TestClient(app) as client:
        response = client.get("/og-image")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


def test_og_route_returns_500_when_index_lookup_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _make_image(tmp_path / "gallery" / "a.jpg")
    storage = MemoryStorage(str(tmp_path))

    def _raise(_path: str):
        raise RuntimeError("index offline")

    monkeypatch.setattr(storage, "get_index", _raise)

    with TestClient(create_app_from_storage(storage, og_preview=True)) as client:
        response = client.get("/og-image", params={"path": "/gallery"})

    assert response.status_code == 500
    assert response.json()["detail"] == "failed to build og preview"
