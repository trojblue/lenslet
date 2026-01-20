from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient
from PIL import Image

from lenslet.server import create_app


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 6), color=(20, 40, 60)).save(path, format="JPEG")


def _write_parquet(path: Path, data: dict) -> None:
    table = pa.table(data)
    pq.write_table(table, path)


def test_parquet_items_and_metrics_inline(tmp_path: Path):
    root = tmp_path
    img_a = root / "a.jpg"
    img_b = root / "b.jpg"
    _make_image(img_a)
    _make_image(img_b)

    _write_parquet(root / "items.parquet", {
        "path": ["a.jpg", "b.jpg"],
        "clip_aesthetic": [0.75, 0.12],
    })

    app = create_app(str(root))
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["mode"] == "table"

    resp = client.get("/folders", params={"path": "/"})
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload["items"]) == 2
    metrics = [item.get("metrics") for item in payload["items"]]
    assert any(m and "clip_aesthetic" in m for m in metrics)


def test_views_no_write_mode(tmp_path: Path):
    root = tmp_path
    _make_image(root / "only.jpg")
    _write_parquet(root / "items.parquet", {"image_id": [1], "path": ["only.jpg"]})

    app = create_app(str(root), no_write=True)
    client = TestClient(app)

    get_views = client.get("/views")
    assert get_views.status_code == 200
    assert get_views.json()["views"] == []

    put_views = client.put("/views", json={"version": 1, "views": []})
    assert put_views.status_code == 403
    assert not (root / ".lenslet").exists()


def test_views_persist(tmp_path: Path):
    root = tmp_path
    _make_image(root / "only.jpg")
    _write_parquet(root / "items.parquet", {"image_id": [1], "path": ["only.jpg"]})

    app = create_app(str(root), no_write=False)
    client = TestClient(app)

    payload = {"version": 1, "views": [{"id": "demo", "name": "Demo", "pool": {"kind": "folder", "path": "/"}, "view": {"filters": {"and": []}, "sort": {"kind": "builtin", "key": "added", "dir": "desc"}}}]}
    put_views = client.put("/views", json=payload)
    assert put_views.status_code == 200

    views_path = root / ".lenslet" / "views.json"
    assert views_path.exists()
    saved = client.get("/views")
    assert saved.status_code == 200
    assert saved.json()["views"][0]["id"] == "demo"
