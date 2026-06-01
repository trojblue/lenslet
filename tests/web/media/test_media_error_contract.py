from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from lenslet.media_errors import MediaDecodeError, MediaReadError, RemoteMediaReadError
from lenslet.server import StorageAppOptions
from lenslet.web.browse import build_image_metadata
from lenslet.web.app.factory import create_app_from_storage
from lenslet.web.media import file_response, thumb_response_async
from lenslet.web.thumbs import ThumbnailScheduler
from lenslet.storage.memory import MemoryStorage
from lenslet.storage.table import TableStorage, TableStorageOptions


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color=(32, 96, 160)).save(path, format="JPEG")


def test_memory_storage_raises_decode_error_for_invalid_image_bytes(tmp_path: Path) -> None:
    broken = tmp_path / "gallery" / "broken.jpg"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_bytes(b"not an image")
    storage = MemoryStorage(str(tmp_path))

    with pytest.raises(MediaDecodeError, match="decode failed"):
        storage.get_or_build_thumbnail("/gallery/broken.jpg")

    with pytest.raises(MediaDecodeError, match="decode failed"):
        storage.load_dimensions("gallery/broken.jpg")


def test_memory_get_dimensions_does_not_decode_source_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_image(tmp_path / "gallery" / "sample.jpg")
    storage = MemoryStorage(str(tmp_path))

    def fail_read(_path: str):
        raise AssertionError("get_dimensions must not read source bytes")

    with monkeypatch.context() as patched:
        patched.setattr(storage, "_read_dimensions_fast", fail_read)
        patched.setattr(storage, "read_bytes", fail_read)
        assert storage.get_dimensions("/gallery/sample.jpg") == (0, 0)

    assert storage.load_dimensions("/gallery/sample.jpg") == (8, 8)
    assert storage.get_dimensions("/gallery/sample.jpg") == (8, 8)


def test_memory_load_dimensions_maps_source_read_failure_to_read_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_image(tmp_path / "gallery" / "sample.jpg")
    storage = MemoryStorage(str(tmp_path))

    monkeypatch.setattr(storage, "_load_dimensions_fast", lambda _path: None)

    def fail_read(_path: str) -> bytes:
        raise PermissionError("blocked")

    monkeypatch.setattr(storage, "read_bytes", fail_read)

    with pytest.raises(MediaReadError, match="read failed"):
        storage.load_dimensions("/gallery/sample.jpg")


def _table_storage_without_cached_dimensions(tmp_path: Path) -> TableStorage:
    image_path = tmp_path / "gallery" / "sample.jpg"
    _make_image(image_path)
    storage = TableStorage(
        [{"path": "gallery/sample.jpg", "source": str(image_path)}],
        options=TableStorageOptions(
            root=None,
            source_column="source",
            path_column="path",
            skip_dimension_probe=True,
        ),
    )
    storage._dimensions.clear()
    item = storage._lookup_item(storage._normalize_source_item_path("/gallery/sample.jpg"))
    assert item is not None
    item.width = 0
    item.height = 0
    return storage


def test_source_backed_load_dimensions_maps_source_read_failure_to_read_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _table_storage_without_cached_dimensions(tmp_path)

    def fail_read(_path: str) -> bytes:
        raise PermissionError("blocked")

    monkeypatch.setattr(storage, "read_bytes", fail_read)

    with pytest.raises(MediaReadError, match="read failed"):
        storage.load_dimensions("/gallery/sample.jpg")


def test_source_backed_load_dimensions_maps_decode_failure_to_decode_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _table_storage_without_cached_dimensions(tmp_path)

    monkeypatch.setattr(storage, "read_bytes", lambda _path: b"not an image")

    with pytest.raises(MediaDecodeError, match="decode failed"):
        storage.load_dimensions("/gallery/sample.jpg")


def test_thumb_route_maps_decode_failures_to_422(tmp_path: Path, monkeypatch) -> None:
    _make_image(tmp_path / "gallery" / "sample.jpg")
    storage = MemoryStorage(str(tmp_path))

    def _raise(_path: str) -> bytes:
        raise MediaDecodeError("/gallery/sample.jpg", "corrupt payload")

    monkeypatch.setattr(storage, "get_or_build_thumbnail", _raise)

    with TestClient(create_app_from_storage(storage)) as client:
        response = client.get("/thumb", params={"path": "/gallery/sample.jpg"})

    assert response.status_code == 422
    assert response.json()["detail"] == "failed to decode source image"


def test_file_response_maps_remote_permission_failure_to_403() -> None:
    class Storage:
        @staticmethod
        def guess_mime(_path: str) -> str:
            return "image/jpeg"

        @staticmethod
        def resolve_local_file_path(_path: str) -> None:
            return None

        @staticmethod
        def read_bytes(path: str) -> bytes:
            raise RemoteMediaReadError(path, "https://example.test/a.jpg", "permission", "HTTP 403")

    with pytest.raises(HTTPException) as exc_info:
        file_response(Storage(), "/remote/a.jpg")

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "remote source access denied"


def test_metadata_response_maps_remote_permission_failure_to_403() -> None:
    class Storage:
        @staticmethod
        def guess_mime(_path: str) -> str:
            return "image/jpeg"

        @staticmethod
        def read_bytes(path: str) -> bytes:
            raise RemoteMediaReadError(path, "https://example.test/a.jpg", "permission", "HTTP 403")

    with pytest.raises(HTTPException) as exc_info:
        build_image_metadata(Storage(), "/remote/a.jpg")

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "remote source access denied"


def test_metadata_response_maps_raw_io_errors_to_read_failure() -> None:
    class Storage:
        @staticmethod
        def guess_mime(_path: str) -> str:
            return "image/jpeg"

        @staticmethod
        def read_bytes(_path: str) -> bytes:
            raise PermissionError("blocked")

    with pytest.raises(HTTPException) as exc_info:
        build_image_metadata(Storage(), "/gallery/sample.jpg")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "failed to read source image"


def test_metadata_response_propagates_unexpected_read_errors() -> None:
    class Storage:
        @staticmethod
        def guess_mime(_path: str) -> str:
            return "image/jpeg"

        @staticmethod
        def read_bytes(_path: str) -> bytes:
            raise RuntimeError("read bug")

    with pytest.raises(RuntimeError, match="read bug"):
        build_image_metadata(Storage(), "/gallery/sample.jpg")


def test_metadata_response_maps_parser_failure_to_422() -> None:
    class Storage:
        @staticmethod
        def guess_mime(_path: str) -> str:
            return "image/png"

        @staticmethod
        def read_bytes(_path: str) -> bytes:
            return b"not a png"

    with pytest.raises(HTTPException) as exc_info:
        build_image_metadata(Storage(), "/gallery/broken.png")

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "failed to decode source image"


@pytest.mark.parametrize(
    ("category", "expected_status", "expected_detail"),
    [
        ("permission", 403, "remote source access denied"),
        ("timeout", 504, "remote source timed out"),
    ],
)
def test_comparison_export_maps_remote_read_failures_to_shared_status(
    tmp_path: Path,
    monkeypatch,
    category: str,
    expected_status: int,
    expected_detail: str,
) -> None:
    _make_image(tmp_path / "gallery" / "a.jpg")
    _make_image(tmp_path / "gallery" / "b.jpg")
    storage = MemoryStorage(str(tmp_path))
    original_read_bytes = storage.read_bytes

    def _read_bytes(path: str) -> bytes:
        if path.endswith("/b.jpg"):
            raise RemoteMediaReadError(path, "https://example.test/b.jpg", category, "upstream")
        return original_read_bytes(path)

    monkeypatch.setattr(storage, "read_bytes", _read_bytes)

    with TestClient(create_app_from_storage(storage)) as client:
        response = client.post(
            "/export-comparison",
            json={
                "v": 2,
                "paths": ["/gallery/a.jpg", "/gallery/b.jpg"],
                "labels": ["A", "B"],
                "embed_metadata": False,
            },
        )

    assert response.status_code == expected_status
    assert response.json() == {"error": "export_failed", "message": expected_detail}


def test_file_response_propagates_unexpected_local_resolver_errors() -> None:
    class Storage:
        @staticmethod
        def guess_mime(_path: str) -> str:
            return "image/jpeg"

        @staticmethod
        def resolve_local_file_path(_path: str) -> str:
            raise RuntimeError("resolver bug")

        @staticmethod
        def read_bytes(_path: str) -> bytes:
            raise AssertionError("fallback should not hide resolver bugs")

    with pytest.raises(RuntimeError, match="resolver bug"):
        file_response(Storage(), "/gallery/sample.jpg")


def test_file_response_propagates_unexpected_read_errors() -> None:
    class Storage:
        @staticmethod
        def guess_mime(_path: str) -> str:
            return "image/jpeg"

        @staticmethod
        def resolve_local_file_path(_path: str) -> None:
            return None

        @staticmethod
        def read_bytes(_path: str) -> bytes:
            raise RuntimeError("read bug")

    with pytest.raises(RuntimeError, match="read bug"):
        file_response(Storage(), "/gallery/sample.jpg")


def test_file_response_maps_raw_io_errors_to_read_failure() -> None:
    class Storage:
        @staticmethod
        def guess_mime(_path: str) -> str:
            return "image/jpeg"

        @staticmethod
        def resolve_local_file_path(_path: str) -> None:
            return None

        @staticmethod
        def read_bytes(_path: str) -> bytes:
            raise PermissionError("blocked")

    with pytest.raises(HTTPException) as exc_info:
        file_response(Storage(), "/gallery/sample.jpg")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "failed to read source image"


def test_thumb_response_propagates_unexpected_memory_cache_errors() -> None:
    class Request:
        @staticmethod
        async def is_disconnected() -> bool:
            return False

    class Storage:
        @staticmethod
        def get_cached_thumbnail(_path: str) -> bytes | None:
            raise RuntimeError("cache bug")

        @staticmethod
        def get_or_build_thumbnail(_path: str) -> bytes:
            return b"thumb"

    queue: ThumbnailScheduler[bytes | None] = ThumbnailScheduler(max_workers=1)
    try:
        with pytest.raises(RuntimeError, match="cache bug"):
            asyncio.run(thumb_response_async(Storage(), "/gallery/sample.jpg", Request(), queue))
    finally:
        queue.close()


def test_thumb_response_propagates_unexpected_generation_errors() -> None:
    class Request:
        @staticmethod
        async def is_disconnected() -> bool:
            return False

    class Storage:
        @staticmethod
        def get_or_build_thumbnail(_path: str) -> bytes:
            raise RuntimeError("thumbnail bug")

    queue: ThumbnailScheduler[bytes | None] = ThumbnailScheduler(max_workers=1)
    try:
        with pytest.raises(RuntimeError, match="thumbnail bug"):
            asyncio.run(thumb_response_async(Storage(), "/gallery/sample.jpg", Request(), queue))
    finally:
        queue.close()


def test_thumb_response_maps_raw_io_errors_to_read_failure() -> None:
    class Request:
        @staticmethod
        async def is_disconnected() -> bool:
            return False

    class Storage:
        @staticmethod
        def get_or_build_thumbnail(_path: str) -> bytes:
            raise PermissionError("blocked")

    queue: ThumbnailScheduler[bytes | None] = ThumbnailScheduler(max_workers=1)
    try:
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(thumb_response_async(Storage(), "/gallery/sample.jpg", Request(), queue))
    finally:
        queue.close()

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "failed to read source image"


def test_og_route_returns_422_when_all_candidate_tiles_fail(
    tmp_path: Path,
    monkeypatch,
    caplog,
) -> None:
    _make_image(tmp_path / "gallery" / "sample.jpg")
    storage = MemoryStorage(str(tmp_path))

    def _raise(_path: str) -> bytes:
        raise MediaDecodeError("/gallery/sample.jpg", "corrupt payload")

    monkeypatch.setattr(storage, "get_or_build_thumbnail", _raise)

    with caplog.at_level(logging.WARNING):
        with TestClient(create_app_from_storage(storage, options=StorageAppOptions(og_preview=True))) as client:
            response = client.get("/og-image", params={"path": "/gallery/sample.jpg"})

    assert response.status_code == 422
    assert response.json()["detail"] == "failed to decode source image"
    assert "og thumbnail generation failed" in caplog.text


@pytest.mark.parametrize(
    ("category", "expected_status", "expected_detail"),
    [
        ("permission", 403, "remote source access denied"),
        ("timeout", 504, "remote source timed out"),
    ],
)
def test_og_route_maps_remote_thumbnail_failures_to_shared_status(
    tmp_path: Path,
    monkeypatch,
    caplog,
    category: str,
    expected_status: int,
    expected_detail: str,
) -> None:
    _make_image(tmp_path / "gallery" / "sample.jpg")
    storage = MemoryStorage(str(tmp_path))

    def _raise(path: str) -> bytes:
        raise RemoteMediaReadError(path, "https://example.test/sample.jpg", category, "upstream")

    monkeypatch.setattr(storage, "get_or_build_thumbnail", _raise)

    with caplog.at_level(logging.WARNING):
        with TestClient(create_app_from_storage(storage, options=StorageAppOptions(og_preview=True))) as client:
            response = client.get("/og-image", params={"path": "/gallery/sample.jpg"})

    assert response.status_code == expected_status
    assert response.json()["detail"] == expected_detail
    assert "og thumbnail generation failed" in caplog.text


def test_og_route_keeps_rendering_when_other_tiles_succeed(
    tmp_path: Path,
    monkeypatch,
    caplog,
) -> None:
    _make_image(tmp_path / "gallery" / "good.jpg")
    _make_image(tmp_path / "gallery" / "bad.jpg")
    storage = MemoryStorage(str(tmp_path))
    original_get_or_build_thumbnail = storage.get_or_build_thumbnail

    def _patched_thumbnail(path: str) -> bytes:
        if path.endswith("/bad.jpg"):
            raise MediaDecodeError("/gallery/bad.jpg", "corrupt payload")
        return original_get_or_build_thumbnail(path)

    monkeypatch.setattr(storage, "get_or_build_thumbnail", _patched_thumbnail)

    with caplog.at_level(logging.WARNING):
        with TestClient(create_app_from_storage(storage, options=StorageAppOptions(og_preview=True))) as client:
            response = client.get("/og-image", params={"path": "/gallery"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert "og thumbnail generation failed" in caplog.text
