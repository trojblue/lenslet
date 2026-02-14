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


def test_recursive_returns_full_sorted_list(tmp_path: Path) -> None:
    root = tmp_path
    for idx in range(42):
        branch = "alpha" if idx % 2 == 0 else "beta"
        _make_image(root / f"gallery/{branch}/img_{idx:03d}.jpg")

    client = TestClient(create_app(str(root)))
    payload = _recursive(client, "/gallery")

    assert payload["page"] is None
    assert payload["pageSize"] is None
    assert payload["pageCount"] is None
    assert payload["totalItems"] is None
    assert len(payload["items"]) == 42

    item_paths = [item["path"] for item in payload["items"]]
    assert item_paths == sorted(item_paths)
    assert set(item_paths) == {
        f"/gallery/alpha/img_{idx:03d}.jpg" if idx % 2 == 0 else f"/gallery/beta/img_{idx:03d}.jpg"
        for idx in range(42)
    }


def test_recursive_ignores_paging_params_and_legacy_flag(tmp_path: Path) -> None:
    root = tmp_path
    for idx in range(6):
        _make_image(root / f"shots/img_{idx:03d}.jpg")

    client = TestClient(create_app(str(root)))
    payload = _recursive(client, "/shots", page="2", page_size="1", legacy_recursive="1")

    assert payload["page"] is None
    assert payload["pageSize"] is None
    assert payload["pageCount"] is None
    assert payload["totalItems"] is None
    assert len(payload["items"]) == 6


def test_recursive_cache_reuses_snapshot_between_calls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path
    for idx in range(12):
        branch = "north" if idx % 2 == 0 else "south"
        _make_image(root / f"dataset/{branch}/img_{idx:03d}.jpg")

    collect_calls = {"count": 0}
    original = server_browse._collect_recursive_cached_items

    def _counting_collect(*args, **kwargs):
        collect_calls["count"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(server_browse, "_collect_recursive_cached_items", _counting_collect)

    app = create_app(str(root))
    with TestClient(app) as client:
        first = _recursive(client, "/dataset")
        second = _recursive(client, "/dataset")

    assert len(first["items"]) == 12
    assert len(second["items"]) == 12
    assert collect_calls["count"] == 1
