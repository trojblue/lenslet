from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from lenslet import server_browse
from lenslet.server import create_app


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4), color=(32, 64, 128)).save(path, format="JPEG")


def _recursive(client: TestClient, path: str, **params) -> dict:
    query = {"path": path, "recursive": "1", **params}
    resp = client.get("/folders", params=query)
    assert resp.status_code == 200
    return resp.json()


def test_recursive_pagination_defaults_and_adjacent_windows(tmp_path: Path):
    root = tmp_path
    for idx in range(230):
        if idx % 2 == 0:
            rel = f"parent/a/img_{idx:03d}.jpg"
        else:
            rel = f"parent/b/img_{idx:03d}.jpg"
        _make_image(root / rel)

    client = TestClient(create_app(str(root)))

    page1 = _recursive(client, "/parent")
    page2 = _recursive(client, "/parent", page="2")

    assert page1["page"] == 1
    assert page1["pageSize"] == 200
    assert page1["pageCount"] == 2
    assert page1["totalItems"] == 230
    assert len(page1["items"]) == 200
    assert len(page2["items"]) == 30

    page1_paths = [item["path"] for item in page1["items"]]
    page2_paths = [item["path"] for item in page2["items"]]
    combined = page1_paths + page2_paths

    assert page1_paths == sorted(page1_paths)
    assert page2_paths == sorted(page2_paths)
    assert len(set(page1_paths).intersection(page2_paths)) == 0
    assert len(set(combined)) == 230


def test_recursive_pagination_is_stable_between_calls(tmp_path: Path):
    root = tmp_path
    _make_image(root / "root/zeta/top.jpg")
    _make_image(root / "root/alpha/one.jpg")
    _make_image(root / "root/mid/two.jpg")
    _make_image(root / "root/alpha/deep/three.jpg")

    client = TestClient(create_app(str(root)))

    first = _recursive(client, "/root", page="1", page_size="2")
    second = _recursive(client, "/root", page="1", page_size="2")

    first_paths = [item["path"] for item in first["items"]]
    second_paths = [item["path"] for item in second["items"]]
    assert first_paths == second_paths
    assert first_paths == sorted(first_paths)


def test_recursive_pagination_rejects_invalid_values(tmp_path: Path):
    root = tmp_path
    _make_image(root / "parent/top.jpg")

    client = TestClient(create_app(str(root)))

    bad_cases = [
        ({"path": "/parent", "recursive": "1", "page": "0"}, "page must be >= 1"),
        ({"path": "/parent", "recursive": "1", "page_size": "-1"}, "page_size must be >= 1"),
        ({"path": "/parent", "recursive": "1", "page": "abc"}, "page must be an integer"),
        ({"path": "/parent", "recursive": "1", "page_size": "abc"}, "page_size must be an integer"),
    ]

    for query, message in bad_cases:
        resp = client.get("/folders", params=query)
        assert resp.status_code == 400
        assert resp.json()["detail"] == message


def test_recursive_page_size_is_clamped(tmp_path: Path):
    root = tmp_path
    _make_image(root / "parent/top.jpg")
    _make_image(root / "parent/child/nested.jpg")

    client = TestClient(create_app(str(root)))
    payload = _recursive(client, "/parent", page_size="99999")

    assert payload["page"] == 1
    assert payload["pageSize"] == 500
    assert payload["pageCount"] == 1
    assert payload["totalItems"] == 2
    assert len(payload["items"]) == 2


def test_recursive_legacy_mode_returns_full_payload(tmp_path: Path):
    root = tmp_path
    for idx in range(12):
        _make_image(root / f"gallery/set/img_{idx:03d}.jpg")

    client = TestClient(create_app(str(root)))

    paged = _recursive(client, "/gallery", page_size="5")
    legacy = _recursive(client, "/gallery", page_size="5", legacy_recursive="1")

    assert len(paged["items"]) == 5
    assert paged["page"] == 1
    assert paged["pageSize"] == 5
    assert paged["pageCount"] == 3
    assert paged["totalItems"] == 12

    assert len(legacy["items"]) == 12
    assert legacy["page"] is None
    assert legacy["pageSize"] is None
    assert legacy["pageCount"] is None
    assert legacy["totalItems"] is None


def test_recursive_pagination_reuses_cached_snapshot_between_pages(
    tmp_path: Path,
    monkeypatch,
):
    root = tmp_path
    for idx in range(30):
        branch = "alpha" if idx % 2 == 0 else "beta"
        _make_image(root / f"gallery/{branch}/img_{idx:03d}.jpg")

    collect_calls = {"count": 0}
    original = server_browse._collect_recursive_cached_items

    def _counting_collect(*args, **kwargs):
        collect_calls["count"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(server_browse, "_collect_recursive_cached_items", _counting_collect)

    client = TestClient(create_app(str(root)))

    first = _recursive(client, "/gallery", page_size="10")
    second = _recursive(client, "/gallery", page="2", page_size="10")

    assert first["totalItems"] == 30
    assert second["totalItems"] == 30
    assert len(first["items"]) == 10
    assert len(second["items"]) == 10
    assert collect_calls["count"] == 1


def test_recursive_pagination_reuses_persisted_cache_after_restart(
    tmp_path: Path,
    monkeypatch,
):
    root = tmp_path
    for idx in range(24):
        branch = "north" if idx % 2 == 0 else "south"
        _make_image(root / f"dataset/{branch}/img_{idx:03d}.jpg")

    first_app = create_app(str(root))
    with TestClient(first_app) as client:
        first_payload = _recursive(client, "/dataset", page_size="12")
    assert first_payload["totalItems"] == 24

    collect_calls = {"count": 0}
    original = server_browse._collect_recursive_cached_items

    def _counting_collect(*args, **kwargs):
        collect_calls["count"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(server_browse, "_collect_recursive_cached_items", _counting_collect)

    second_app = create_app(str(root))
    with TestClient(second_app) as client:
        second_payload = _recursive(client, "/dataset", page_size="12")

    assert second_payload["totalItems"] == 24
    assert collect_calls["count"] == 0
