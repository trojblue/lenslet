from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from lenslet.server import create_app


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
