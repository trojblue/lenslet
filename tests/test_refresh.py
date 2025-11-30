from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from lenslet.server import create_app, create_app_from_datasets
from lenslet.storage.memory import MemoryStorage


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4), color=(32, 64, 128)).save(path, format="JPEG")


def test_invalidate_subtree_drops_cache_and_rebuilds(tmp_path: Path):
    root = tmp_path
    folder_a = root / "a"
    folder_b = root / "b"
    img_a1 = folder_a / "one.jpg"
    img_b1 = folder_b / "side.jpg"

    _make_image(img_a1)
    _make_image(img_b1)

    storage = MemoryStorage(str(root))

    # Prime caches
    idx_a = storage.get_index("/a")
    idx_b = storage.get_index("/b")
    assert len(idx_a.items) == 1
    assert len(idx_b.items) == 1

    storage.get_thumbnail("/a/one.jpg")
    storage.get_dimensions("/a/one.jpg")
    assert "/a/one.jpg" in storage._thumbnails  # type: ignore[attr-defined]
    assert "/a/one.jpg" in storage._dimensions  # type: ignore[attr-defined]

    # Mutate filesystem under /a
    img_a2 = folder_a / "two.jpg"
    _make_image(img_a2)

    # Cached index should remain stale until refresh
    assert len(storage.get_index("/a").items) == 1

    storage.invalidate_subtree("/a")

    refreshed = storage.get_index("/a")
    assert len(refreshed.items) == 2

    # Cache entries under /a were purged, /b untouched
    assert "/a/one.jpg" not in storage._thumbnails  # type: ignore[attr-defined]
    assert "/a/one.jpg" not in storage._dimensions  # type: ignore[attr-defined]
    assert len(storage.get_index("/b").items) == 1


def test_refresh_endpoint_reindexes_folder(tmp_path: Path):
    root = tmp_path
    shots = root / "shots"
    img1 = shots / "first.jpg"
    img2 = shots / "second.jpg"
    _make_image(img1)

    app = create_app(str(root))
    client = TestClient(app)

    first = client.get("/folders", params={"path": "/shots"})
    assert first.status_code == 200
    assert len(first.json()["items"]) == 1

    _make_image(img2)

    # Still cached before refresh
    stale = client.get("/folders", params={"path": "/shots"})
    assert len(stale.json()["items"]) == 1

    refresh = client.post("/refresh", params={"path": "/shots"})
    assert refresh.status_code == 200
    assert refresh.json()["ok"] is True

    updated = client.get("/folders", params={"path": "/shots"})
    assert len(updated.json()["items"]) == 2


def test_refresh_endpoint_dataset_mode_is_noop():
    app = create_app_from_datasets({"demo": []})
    client = TestClient(app)

    resp = client.post("/refresh", params={"path": "/demo"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert "static" in payload.get("note", "")
