from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient
from PIL import Image

from lenslet.cli import _prepare_table_cache
from lenslet.server import create_app, create_app_from_storage


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
    assert health.json().get("refresh", {}).get("enabled") is False

    resp = client.get("/folders", params={"path": "/"})
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload["items"]) == 2
    assert payload["metricKeys"] == ["clip_aesthetic"]
    metrics = [item.get("metrics") for item in payload["items"]]
    assert any(m and "clip_aesthetic" in m for m in metrics)
    assert all("__index_level_0__" not in (item_metrics or {}) for item_metrics in metrics)


def test_parquet_folder_payload_exposes_sorted_metric_keys(tmp_path: Path):
    root = tmp_path
    img_a = root / "gallery" / "a.jpg"
    img_b = root / "gallery" / "b.jpg"
    _make_image(img_a)
    _make_image(img_b)

    _write_parquet(root / "items.parquet", {
        "path": ["gallery/a.jpg", "gallery/b.jpg"],
        "quality_score": [0.8, 0.3],
        "clip_aesthetic": [0.4, 0.2],
        "__index_level_0__": [11, 12],
    })

    client = TestClient(create_app(str(root)))

    payload = client.get("/folders", params={"path": "/gallery"}).json()
    recursive_payload = client.get("/folders", params={"path": "/gallery", "recursive": "1"}).json()

    assert payload["metricKeys"] == ["clip_aesthetic", "quality_score"]
    assert recursive_payload["metricKeys"] == ["clip_aesthetic", "quality_score"]
    assert all(
        "__index_level_0__" not in (item.get("metrics") or {})
        for item in payload["items"]
    )
    assert all(
        "__index_level_0__" not in (item.get("metrics") or {})
        for item in recursive_payload["items"]
    )


def test_views_no_write_mode(tmp_path: Path):
    root = tmp_path
    _make_image(root / "only.jpg")
    _write_parquet(root / "items.parquet", {"image_id": [1], "path": ["only.jpg"]})

    app = create_app(str(root), no_write=True)
    client = TestClient(app)

    get_views = client.get("/views")
    assert get_views.status_code == 200
    assert get_views.json()["views"] == []

    payload = {"version": 1, "views": [{"id": "demo", "name": "Demo", "pool": {"kind": "folder", "path": "/"}, "view": {"filters": {"and": []}, "sort": {"kind": "builtin", "key": "added", "dir": "desc"}}}]}
    put_views = client.put("/views", json=payload)
    assert put_views.status_code == 200
    assert not (root / ".lenslet").exists()
    saved = client.get("/views")
    assert saved.status_code == 200
    assert saved.json()["views"] == payload["views"]


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


def test_standalone_parquet_auto_detects_safe_absolute_source_root(tmp_path: Path):
    outputs = tmp_path / "outputs"
    dataset = tmp_path / "dataset"
    outputs.mkdir(parents=True, exist_ok=True)

    img_a = dataset / "a.jpg"
    img_b = dataset / "b.jpg"
    _make_image(img_a)
    _make_image(img_b)

    parquet_path = outputs / "items.parquet"
    _write_parquet(parquet_path, {
        "path": [str(img_a), str(img_b)],
        "quality_score": [0.9, 0.4],
    })

    storage = _prepare_table_cache(
        parquet_path=parquet_path,
        base_dir=None,
        source_column=None,
        cache_wh=False,
        skip_indexing=True,
        auto_detect_root=True,
    )

    assert storage.root == str(dataset)
    assert len(storage._items) == 2

    client = TestClient(create_app_from_storage(storage))
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["total_images"] == 2
