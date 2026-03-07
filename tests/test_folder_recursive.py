from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from lenslet.server import create_app, create_app_from_storage
from lenslet.storage.memory import MemoryStorage


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (4, 4), color=(32, 64, 128)).save(path, format="JPEG")


def _folders_request(client: TestClient, path: str, **params):
    query = {"path": path, **params}
    return client.get("/folders", params=query)


def _recursive(client: TestClient, path: str) -> dict:
    resp = _folders_request(client, path, recursive="1")
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


def test_recursive_rejects_paging_params_and_legacy_flag(tmp_path: Path) -> None:
    root = tmp_path
    for idx in range(6):
        _make_image(root / f"shots/img_{idx:03d}.jpg")

    client = TestClient(create_app(str(root)))
    resp = _folders_request(
        client,
        "/shots",
        recursive="1",
        page="2",
        page_size="1",
        legacy_recursive="1",
    )

    assert resp.status_code == 400
    payload = resp.json()
    assert payload["error"] == "unsupported_query_params"
    for key in ("page", "page_size", "legacy_recursive"):
        assert key in payload["message"]


def test_recursive_cache_reuses_snapshot_between_calls(
    tmp_path: Path,
) -> None:
    root = tmp_path
    for idx in range(12):
        branch = "north" if idx % 2 == 0 else "south"
        _make_image(root / f"dataset/{branch}/img_{idx:03d}.jpg")

    app = create_app(str(root))
    with TestClient(app) as client:
        first = _recursive(client, "/dataset")
        second = _recursive(client, "/dataset")

    assert len(first["items"]) == 12
    assert len(second["items"]) == 12
    assert [item["path"] for item in first["items"]] == [item["path"] for item in second["items"]]


def test_recursive_first_request_uses_lightweight_recursive_getter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path
    _make_image(root / "gallery" / "alpha" / "one.jpg")
    _make_image(root / "gallery" / "beta" / "two.jpg")

    storage = MemoryStorage(str(root))
    app = create_app_from_storage(storage)
    original_recursive = storage.get_index_for_recursive

    def _unexpected_get_index(_path: str):
        raise AssertionError("recursive folder requests should stay on the lightweight getter path")

    monkeypatch.setattr(storage, "get_index", _unexpected_get_index)
    monkeypatch.setattr(storage, "get_index_for_recursive", original_recursive)

    with TestClient(app) as client:
        payload = _recursive(client, "/gallery")

    assert len(payload["items"]) == 2
    assert {item["path"] for item in payload["items"]} == {
        "/gallery/alpha/one.jpg",
        "/gallery/beta/two.jpg",
    }


def test_recursive_count_only_seeds_snapshot_cache_for_payload(tmp_path: Path) -> None:
    root = tmp_path
    for idx in range(8):
        branch = "alpha" if idx % 2 == 0 else "beta"
        _make_image(root / f"gallery/{branch}/img_{idx:03d}.jpg")

    app = create_app(str(root))
    with TestClient(app) as client:
        count_response = _folders_request(
            client,
            "/gallery",
            recursive="1",
            count_only="1",
        )
        assert count_response.status_code == 200
        count_payload = count_response.json()
        assert count_payload["items"] == []
        assert count_payload["totalItems"] == 8

        counters_after_count = client.get("/health").json()["hotpath"]["counters"]
        payload_response = _recursive(client, "/gallery")
        counters_after_payload = client.get("/health").json()["hotpath"]["counters"]

    assert len(payload_response["items"]) == 8
    assert counters_after_count["folders_recursive_cache_miss_total"] >= 1
    assert (
        counters_after_payload["folders_recursive_cache_miss_total"]
        == counters_after_count["folders_recursive_cache_miss_total"]
    )
    assert counters_after_payload["folders_recursive_cache_hit_total"] >= 1
