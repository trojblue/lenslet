from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import lenslet.server_factory as server_factory
import lenslet.server_routes_index as server_routes_index
from lenslet.server import create_app, create_app_from_datasets
from lenslet.storage.memory import MemoryStorage
from lenslet.storage.table import TableStorage
from lenslet.workspace import Workspace


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4), color=(32, 64, 128)).save(path, format="JPEG")


def _make_colored_image(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4), color=color).save(path, format="JPEG")


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
    meta = storage.ensure_metadata("/a/one.jpg")
    meta["notes"] = "stale"
    storage.set_metadata("/a/one.jpg", meta)
    assert storage.get_cached_thumbnail("/a/one.jpg") is not None
    assert "/a/one.jpg" in dict(storage.metadata_items())

    # Mutate filesystem under /a
    img_a2 = folder_a / "two.jpg"
    _make_image(img_a2)

    # Cached index should remain stale until refresh
    assert len(storage.get_index("/a").items) == 1

    storage.invalidate_subtree("/a")

    refreshed = storage.get_index("/a")
    assert len(refreshed.items) == 2

    # Cache entries under /a were purged, /b untouched
    assert storage.get_cached_thumbnail("/a/one.jpg") is None
    assert "/a/one.jpg" not in dict(storage.metadata_items())
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

    meta = storage.ensure_metadata("/a/one.jpg")
    meta["notes"] = "keep me"
    meta["tags"] = ["tagged"]
    meta["star"] = 4
    storage.set_metadata("/a/one.jpg", meta)

    storage.invalidate_subtree("/a", clear_metadata=False)

    assert storage.get_cached_thumbnail("/a/one.jpg") is None

    preserved = storage.ensure_metadata("/a/one.jpg")
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

    health_before = client.get("/health").json()
    assert health_before["refresh"]["enabled"] is True
    before = health_before["indexing"]["generation"]

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

    health = client.get("/health")
    assert health.status_code == 200
    refresh_health = health.json().get("refresh", {})
    assert refresh_health.get("enabled") is False
    assert "static" in str(refresh_health.get("note", ""))

    resp = client.post("/refresh", params={"path": "/demo"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert "static" in payload.get("note", "")


def test_refresh_swaps_health_index_og_and_views_from_current_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "gallery-root"
    first_image = root / "shots" / "first.jpg"
    second_image = root / "shots" / "second.jpg"
    _make_colored_image(first_image, (255, 32, 32))
    _make_colored_image(second_image, (32, 200, 64))

    workspace_a = Workspace(root=tmp_path / "alpha" / ".lenslet", can_write=True)
    workspace_b = Workspace(root=tmp_path / "beta" / ".lenslet", can_write=True)
    workspace_a.write_views({
        "version": 1,
        "views": [{"id": "alpha-view", "name": "Alpha", "pool": {"kind": "folder", "path": "/shots"}, "view": {}}],
    })
    workspace_b.write_views({
        "version": 1,
        "views": [{"id": "beta-view", "name": "Beta", "pool": {"kind": "folder", "path": "/shots"}, "view": {}}],
    })

    storage_a = TableStorage(
        [{"path": "/shots/first.jpg", "source": str(first_image)}],
        root=None,
        skip_indexing=True,
    )
    storage_b = TableStorage(
        [
            {"path": "/shots/first.jpg", "source": str(first_image)},
            {"path": "/shots/second.jpg", "source": str(second_image)},
        ],
        root=None,
        skip_indexing=True,
    )
    preindex_states = [
        (storage_a, workspace_a, "sig-a"),
        (storage_b, workspace_b, "sig-b"),
    ]

    def _fake_ensure_preindex_storage(*_args, **_kwargs):
        assert preindex_states, "unexpected extra preindex rebuild"
        return preindex_states.pop(0)

    monkeypatch.setattr(server_factory, "_ensure_preindex_storage", _fake_ensure_preindex_storage)

    app = create_app(str(root), og_preview=True)
    with TestClient(app) as client:
        health_before = client.get("/health")
        assert health_before.status_code == 200
        health_before_payload = health_before.json()
        assert health_before_payload["mode"] == "table"
        assert health_before_payload["refresh"]["enabled"] is True
        assert health_before_payload["browse_cache"]["path"] == str(workspace_a.browse_cache_dir())

        views_before = client.get("/views")
        assert views_before.status_code == 200
        assert views_before.json()["views"][0]["id"] == "alpha-view"

        html_before = client.get("/index.html", params={"path": "/shots"})
        assert html_before.status_code == 200
        assert "Lenslet: alpha" in html_before.text
        assert "(1 images)" in html_before.text

        og_before = client.get("/og-image", params={"path": "/shots"})
        assert og_before.status_code == 200

        refresh = client.post("/refresh", params={"path": "/shots"})
        assert refresh.status_code == 200
        assert refresh.json()["ok"] is True

        health_after = client.get("/health")
        assert health_after.status_code == 200
        health_after_payload = health_after.json()
        assert health_after_payload["browse_cache"]["path"] == str(workspace_b.browse_cache_dir())
        assert health_after_payload["indexing"]["generation"] != health_before_payload["indexing"]["generation"]
        assert app.state.runtime.snapshotter._workspace.root == workspace_b.root  # type: ignore[attr-defined]
        assert app.state.runtime.thumb_cache.root == workspace_b.thumb_cache_dir()  # type: ignore[union-attr]

        views_after = client.get("/views")
        assert views_after.status_code == 200
        assert views_after.json()["views"][0]["id"] == "beta-view"

        html_after = client.get("/index.html", params={"path": "/shots"})
        assert html_after.status_code == 200
        assert "Lenslet: beta" in html_after.text
        assert "(2 images)" in html_after.text

        app.state.runtime.snapshotter._min_updates = 1
        app.state.runtime.snapshotter._min_interval = 0.0
        thumb_after = client.get("/thumb", params={"path": "/shots/first.jpg"})
        assert thumb_after.status_code == 200
        update_after = client.put(
            "/item",
            params={"path": "/shots/first.jpg"},
            json={"tags": ["beta"], "notes": "workspace-b", "star": 5},
        )
        assert update_after.status_code == 200

        og_after = client.get("/og-image", params={"path": "/shots"})
        assert og_after.status_code == 200
        assert og_after.content != og_before.content

    thumb_cache_b = workspace_b.thumb_cache_dir()
    assert thumb_cache_b is not None
    assert list(thumb_cache_b.rglob("*.webp")), "expected refreshed thumb cache writes in workspace_b"
    snapshot_b = workspace_b.labels_snapshot_path()
    assert snapshot_b is not None and snapshot_b.exists()

    thumb_cache_a = workspace_a.thumb_cache_dir()
    if thumb_cache_a is not None:
        assert not list(thumb_cache_a.rglob("*.webp"))
    snapshot_a = workspace_a.labels_snapshot_path()
    if snapshot_a is not None:
        assert not snapshot_a.exists()


def test_index_shell_is_cached_once_per_process(tmp_path: Path, monkeypatch) -> None:
    _make_image(tmp_path / "gallery" / "sample.jpg")
    server_routes_index._load_frontend_shell.cache_clear()
    app = create_app(str(tmp_path), og_preview=True)

    index_path = Path(server_routes_index.__file__).resolve().parent / "frontend" / "index.html"
    original_read_text = Path.read_text
    calls = {"count": 0}

    def _counting_read_text(self: Path, *args, **kwargs):
        if self.resolve() == index_path.resolve():
            calls["count"] += 1
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _counting_read_text)

    with TestClient(app) as client:
        first = client.get("/index.html", params={"path": "/gallery"})
        second = client.get("/index.html", params={"path": "/gallery"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert calls["count"] == 1


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
):
    root = tmp_path
    _make_image(root / "gallery" / "child" / "a.jpg")
    _make_image(root / "gallery" / "child" / "b.jpg")

    app = create_app(str(root))
    client = TestClient(app)

    first = client.get("/folders", params={"path": "/gallery", "recursive": "1"})
    assert first.status_code == 200
    assert len(first.json()["items"]) == 2

    _make_image(root / "gallery" / "child" / "c.jpg")
    refresh = client.post("/refresh", params={"path": "/gallery/child"})
    assert refresh.status_code == 200
    assert refresh.json()["ok"] is True

    second = client.get("/folders", params={"path": "/gallery", "recursive": "1"})
    assert second.status_code == 200
    assert len(second.json()["items"]) == 3
