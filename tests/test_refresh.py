from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from lenslet import server_browse
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
    meta = storage.get_metadata("/a/one.jpg")
    meta["notes"] = "stale"
    storage.set_metadata("/a/one.jpg", meta)
    assert "/a/one.jpg" in storage._thumbnails  # type: ignore[attr-defined]
    assert "/a/one.jpg" in storage._dimensions  # type: ignore[attr-defined]
    assert "/a/one.jpg" in storage._metadata  # type: ignore[attr-defined]

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
    assert "/a/one.jpg" not in storage._metadata  # type: ignore[attr-defined]
    assert len(storage.get_index("/b").items) == 1


def test_invalidate_subtree_can_preserve_metadata(tmp_path: Path):
    root = tmp_path
    folder = root / "a"
    img = folder / "one.jpg"
    _make_image(img)

    storage = MemoryStorage(str(root))
    storage.get_index("/a")
    storage.get_thumbnail("/a/one.jpg")
    storage.get_dimensions("/a/one.jpg")

    meta = storage.get_metadata("/a/one.jpg")
    meta["notes"] = "keep me"
    meta["tags"] = ["tagged"]
    meta["star"] = 4
    storage.set_metadata("/a/one.jpg", meta)

    storage.invalidate_subtree("/a", clear_metadata=False)

    assert "/a/one.jpg" not in storage._thumbnails  # type: ignore[attr-defined]
    assert "/a/one.jpg" not in storage._dimensions  # type: ignore[attr-defined]

    preserved = storage.get_metadata("/a/one.jpg")
    assert preserved["notes"] == "keep me"
    assert preserved["tags"] == ["tagged"]
    assert preserved["star"] == 4


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


def test_refresh_updates_indexing_generation_contract(tmp_path: Path):
    root = tmp_path
    shots = root / "shots"
    _make_image(shots / "first.jpg")

    app = create_app(str(root))
    client = TestClient(app)

    before = client.get("/health").json()["indexing"]["generation"]

    _make_image(shots / "second.jpg")
    refresh = client.post("/refresh", params={"path": "/shots"})
    assert refresh.status_code == 200
    assert refresh.json()["ok"] is True

    after = client.get("/health").json()["indexing"]["generation"]
    assert isinstance(before, str) and before
    assert isinstance(after, str) and after
    assert after != before


def test_refresh_endpoint_preserves_sidecar_annotations(tmp_path: Path):
    root = tmp_path
    shots = root / "shots"
    img1 = shots / "first.jpg"
    img2 = shots / "second.jpg"
    _make_image(img1)

    app = create_app(str(root))
    client = TestClient(app)

    put = client.put(
        "/item",
        params={"path": "/shots/first.jpg"},
        json={"tags": ["keep"], "notes": "persist", "star": 5},
    )
    assert put.status_code == 200
    assert put.json()["notes"] == "persist"

    _make_image(img2)
    refresh = client.post("/refresh", params={"path": "/shots"})
    assert refresh.status_code == 200
    assert refresh.json()["ok"] is True

    updated = client.get("/folders", params={"path": "/shots"})
    assert updated.status_code == 200
    assert len(updated.json()["items"]) == 2

    sidecar = client.get("/item", params={"path": "/shots/first.jpg"})
    assert sidecar.status_code == 200
    payload = sidecar.json()
    assert payload["notes"] == "persist"
    assert payload["tags"] == ["keep"]
    assert payload["star"] == 5


def test_refresh_endpoint_dataset_mode_is_noop():
    app = create_app_from_datasets({"demo": []})
    client = TestClient(app)

    resp = client.post("/refresh", params={"path": "/demo"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert "static" in payload.get("note", "")


def test_folders_recursive_includes_descendants(tmp_path: Path):
    root = tmp_path
    parent = root / "parent"
    _make_image(parent / "top.jpg")
    _make_image(parent / "child" / "nested.jpg")
    _make_image(parent / "child" / "grand" / "deep.jpg")

    app = create_app(str(root))
    client = TestClient(app)

    direct = client.get("/folders", params={"path": "/parent"})
    assert direct.status_code == 200
    direct_payload = direct.json()
    assert len(direct_payload["items"]) == 1
    assert {entry["name"] for entry in direct_payload["dirs"]} == {"child"}

    recursive = client.get("/folders", params={"path": "/parent", "recursive": "1"})
    assert recursive.status_code == 200
    recursive_payload = recursive.json()
    assert len(recursive_payload["items"]) == 3
    assert {item["path"] for item in recursive_payload["items"]} == {
        "/parent/top.jpg",
        "/parent/child/nested.jpg",
        "/parent/child/grand/deep.jpg",
    }
    assert {entry["name"] for entry in recursive_payload["dirs"]} == {"child"}


def test_refresh_invalidates_recursive_cache_for_ancestor_scope(
    tmp_path: Path,
    monkeypatch,
):
    root = tmp_path
    _make_image(root / "gallery" / "child" / "a.jpg")
    _make_image(root / "gallery" / "child" / "b.jpg")

    collect_calls = {"count": 0}
    original = server_browse._collect_recursive_cached_items

    def _counting_collect(*args, **kwargs):
        collect_calls["count"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(server_browse, "_collect_recursive_cached_items", _counting_collect)

    app = create_app(str(root))
    client = TestClient(app)

    first = client.get("/folders", params={"path": "/gallery", "recursive": "1"})
    assert first.status_code == 200
    assert len(first.json()["items"]) == 2
    assert collect_calls["count"] == 1

    _make_image(root / "gallery" / "child" / "c.jpg")
    refresh = client.post("/refresh", params={"path": "/gallery/child"})
    assert refresh.status_code == 200
    assert refresh.json()["ok"] is True

    second = client.get("/folders", params={"path": "/gallery", "recursive": "1"})
    assert second.status_code == 200
    assert len(second.json()["items"]) == 3
    assert collect_calls["count"] == 2
