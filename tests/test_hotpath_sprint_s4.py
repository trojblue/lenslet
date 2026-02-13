from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from lenslet.server import (
    HotpathTelemetry,
    _thumb_response_async,
    create_app,
    create_app_from_datasets,
    create_app_from_storage,
    create_app_from_table,
)
from lenslet.storage.dataset import DatasetStorage
from lenslet.storage.table import TableStorage
from lenslet.thumbs import ThumbnailScheduler


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (10, 8), color=(48, 96, 144)).save(path, format="JPEG")


def _seed_gallery(root: Path) -> None:
    _make_image(root / "gallery" / "a.jpg")
    _make_image(root / "gallery" / "b.jpg")
    _make_image(root / "gallery" / "sub" / "c.jpg")


def _build_memory_app(root: Path) -> tuple[object, str, str]:
    return create_app(str(root)), "/gallery", "/gallery/a.jpg"


def _build_table_app(root: Path) -> tuple[object, str, str]:
    rows = [
        {"path": "/gallery/a.jpg", "source": str(root / "gallery" / "a.jpg")},
        {"path": "/gallery/b.jpg", "source": str(root / "gallery" / "b.jpg")},
        {"path": "/gallery/sub/c.jpg", "source": str(root / "gallery" / "sub" / "c.jpg")},
    ]
    return create_app_from_table(rows, base_dir=None), "/gallery", "/gallery/a.jpg"


def _build_dataset_app(root: Path) -> tuple[object, str, str]:
    datasets = {
        "demo": [
            str(root / "gallery" / "a.jpg"),
            str(root / "gallery" / "b.jpg"),
            str(root / "gallery" / "sub" / "c.jpg"),
        ],
    }
    return create_app_from_datasets(datasets), "/demo", "/demo/a.jpg"


AppBuilder = Callable[[Path], tuple[object, str, str]]


APP_BUILDERS = [
    pytest.param(_build_memory_app, id="memory"),
    pytest.param(_build_table_app, id="table"),
    pytest.param(_build_dataset_app, id="dataset"),
]


def _assert_recursive_page(
    payload: dict[str, Any],
    *,
    page: int,
    page_size: int,
    page_count: int,
    total_items: int,
    item_count: int,
) -> None:
    assert payload["page"] == page
    assert payload["pageSize"] == page_size
    assert payload["pageCount"] == page_count
    assert payload["totalItems"] == total_items
    assert len(payload["items"]) == item_count


def _assert_local_file_stream_response(response) -> None:
    assert response.status_code == 200
    assert response.headers.get("accept-ranges") == "bytes"
    assert response.headers.get("content-type", "").startswith("image/jpeg")
    assert response.content


@pytest.mark.parametrize("build_app", APP_BUILDERS)
def test_recursive_pagination_contract_across_app_modes(tmp_path: Path, build_app: AppBuilder) -> None:
    _seed_gallery(tmp_path)
    app, folder_path, _ = build_app(tmp_path)

    with TestClient(app) as client:
        page1_resp = client.get(
            "/folders",
            params={"path": folder_path, "recursive": "1", "page": "1", "page_size": "2"},
        )
        page2_resp = client.get(
            "/folders",
            params={"path": folder_path, "recursive": "1", "page": "2", "page_size": "2"},
        )
        legacy_resp = client.get(
            "/folders",
            params={"path": folder_path, "recursive": "1", "page_size": "2", "legacy_recursive": "1"},
        )

    assert page1_resp.status_code == 200
    assert page2_resp.status_code == 200
    assert legacy_resp.status_code == 400

    page1 = page1_resp.json()
    page2 = page2_resp.json()
    legacy = legacy_resp.json()

    _assert_recursive_page(page1, page=1, page_size=2, page_count=2, total_items=3, item_count=2)
    _assert_recursive_page(page2, page=2, page_size=2, page_count=2, total_items=3, item_count=1)

    page1_paths = [item["path"] for item in page1["items"]]
    page2_paths = [item["path"] for item in page2["items"]]
    assert page1_paths == sorted(page1_paths)
    assert page2_paths == sorted(page2_paths)
    assert set(page1_paths).isdisjoint(set(page2_paths))
    assert len(set(page1_paths + page2_paths)) == 3

    assert "legacy_recursive=1 is retired" in legacy["detail"]


@pytest.mark.parametrize("build_app", APP_BUILDERS)
def test_recursive_legacy_rollback_flag_preserves_non_ui_callers(
    tmp_path: Path,
    build_app: AppBuilder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_gallery(tmp_path)
    app, folder_path, _ = build_app(tmp_path)
    monkeypatch.setenv("LENSLET_ENABLE_LEGACY_RECURSIVE_ROLLBACK", "1")

    with TestClient(app) as client:
        legacy_resp = client.get(
            "/folders",
            params={"path": folder_path, "recursive": "1", "page_size": "2", "legacy_recursive": "1"},
        )

    assert legacy_resp.status_code == 200
    legacy = legacy_resp.json()
    assert len(legacy["items"]) == 3
    assert legacy["page"] is None
    assert legacy["pageSize"] is None
    assert legacy["pageCount"] is None
    assert legacy["totalItems"] is None


@pytest.mark.parametrize("build_app", APP_BUILDERS)
def test_file_route_streams_local_files_and_tracks_prefetch_counters(
    tmp_path: Path,
    build_app: AppBuilder,
) -> None:
    _seed_gallery(tmp_path)
    app, _, file_path = build_app(tmp_path)

    with TestClient(app) as client:
        first = client.get("/file", params={"path": file_path})
        second = client.get(
            "/file",
            params={"path": file_path},
            headers={"x-lenslet-prefetch": "viewer"},
        )
        health = client.get("/health")

    assert health.status_code == 200
    _assert_local_file_stream_response(first)
    _assert_local_file_stream_response(second)

    counters = health.json()["hotpath"]["counters"]
    assert counters["file_response_local_stream_total"] >= 2
    assert counters["file_prefetch_viewer_total"] >= 1
    assert counters.get("file_response_fallback_bytes_total", 0) == 0


def test_table_file_route_falls_back_to_read_bytes_for_remote_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_gallery(tmp_path)
    rows = [{"path": "/gallery/a.jpg", "source": str(tmp_path / "gallery" / "a.jpg")}]
    storage = TableStorage(rows, root=None)
    app = create_app_from_storage(storage)
    calls = {"read": 0}

    storage._source_paths["/gallery/a.jpg"] = "s3://bucket/a.jpg"

    def _read_bytes(_path: str) -> bytes:
        calls["read"] += 1
        return b"table-remote"

    monkeypatch.setattr(storage, "read_bytes", _read_bytes)

    with TestClient(app) as client:
        response = client.get("/file", params={"path": "/gallery/a.jpg"})
        health = client.get("/health")

    assert response.status_code == 200
    assert response.content == b"table-remote"
    assert response.headers.get("accept-ranges") is None
    assert calls["read"] == 1
    counters = health.json()["hotpath"]["counters"]
    assert counters["file_response_fallback_bytes_total"] >= 1


def test_dataset_file_route_falls_back_to_read_bytes_for_remote_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_gallery(tmp_path)
    app = create_app_from_datasets({"demo": [str(tmp_path / "gallery" / "a.jpg")]})
    calls = {"read": 0}

    monkeypatch.setattr(DatasetStorage, "get_source_path", lambda self, _path: "s3://bucket/a.jpg")

    def _read_bytes(self, _path: str) -> bytes:
        calls["read"] += 1
        return b"dataset-remote"

    monkeypatch.setattr(DatasetStorage, "read_bytes", _read_bytes)

    with TestClient(app) as client:
        response = client.get("/file", params={"path": "/demo/a.jpg"})
        health = client.get("/health")

    assert response.status_code == 200
    assert response.content == b"dataset-remote"
    assert response.headers.get("accept-ranges") is None
    assert calls["read"] == 1
    counters = health.json()["hotpath"]["counters"]
    assert counters["file_response_fallback_bytes_total"] >= 1


def test_table_mode_og_shell_path_skips_subtree_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_gallery(tmp_path)
    rows = [{"path": "/gallery/a.jpg", "source": str(tmp_path / "gallery" / "a.jpg")}]
    app = create_app_from_table(rows, base_dir=None, og_preview=True)

    def _fail_subtree_count(*_args, **_kwargs):
        raise AssertionError("subtree_image_count must not be called by /index.html")

    monkeypatch.setattr("lenslet.server.og.subtree_image_count", _fail_subtree_count)

    with TestClient(app) as client:
        response = client.get("/index.html", params={"path": "/gallery"})

    assert response.status_code == 200
    assert '<meta property="og:title"' in response.text
    assert '<meta property="og:image"' in response.text


def test_thumb_success_does_not_increment_disconnect_cancellation_metrics() -> None:
    queue: ThumbnailScheduler[bytes | None] = ThumbnailScheduler(max_workers=1)
    try:
        metrics = HotpathTelemetry()

        class Request:
            async def is_disconnected(self) -> bool:
                return False

        class Storage:
            @staticmethod
            def get_thumbnail(_path: str) -> bytes:
                return b"thumb"

        response = asyncio.run(
            _thumb_response_async(
                Storage(),
                "/ok.jpg",
                Request(),
                queue,
                hotpath_metrics=metrics,
            )
        )

        assert response.status_code == 200
        counters = metrics.snapshot()["counters"]
        assert counters.get("thumb_disconnect_cancel_total", 0) == 0
        assert counters.get("thumb_disconnect_cancel_queued_total", 0) == 0
        assert counters.get("thumb_disconnect_cancel_inflight_total", 0) == 0
        assert queue.stats()["inflight"] == 0
    finally:
        queue.close()
