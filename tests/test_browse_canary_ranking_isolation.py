from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from lenslet.server import create_app


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 12), color=(35, 80, 130)).save(path, format="JPEG")


def test_browse_mode_canary_keeps_rank_routes_isolated(tmp_path: Path) -> None:
    _make_image(tmp_path / "sample.jpg")
    app = create_app(str(tmp_path))
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    health_payload = health.json()
    assert health_payload["ok"] is True
    assert health_payload["mode"] != "ranking"

    folders = client.get("/folders")
    assert folders.status_code == 200

    rank_dataset = client.get("/rank/dataset")
    assert rank_dataset.status_code == 404

    index_html = client.get("/")
    assert index_html.status_code == 200
    assert "<html" in index_html.text.lower()
