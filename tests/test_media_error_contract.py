from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from lenslet.media_errors import MediaDecodeError
from lenslet.server_factory import create_app_from_storage
from lenslet.storage.memory import MemoryStorage


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color=(32, 96, 160)).save(path, format="JPEG")


def test_memory_storage_raises_decode_error_for_invalid_image_bytes(tmp_path: Path) -> None:
    broken = tmp_path / "gallery" / "broken.jpg"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_bytes(b"not an image")
    storage = MemoryStorage(str(tmp_path))

    with pytest.raises(MediaDecodeError, match="decode failed"):
        storage.get_thumbnail("/gallery/broken.jpg")

    with pytest.raises(MediaDecodeError, match="decode failed"):
        storage.get_dimensions("gallery/broken.jpg")


def test_thumb_route_maps_decode_failures_to_422(tmp_path: Path, monkeypatch) -> None:
    _make_image(tmp_path / "gallery" / "sample.jpg")
    storage = MemoryStorage(str(tmp_path))

    def _raise(_path: str) -> bytes:
        raise MediaDecodeError("/gallery/sample.jpg", "corrupt payload")

    monkeypatch.setattr(storage, "get_thumbnail", _raise)

    with TestClient(create_app_from_storage(storage)) as client:
        response = client.get("/thumb", params={"path": "/gallery/sample.jpg"})

    assert response.status_code == 422
    assert response.json()["detail"] == "failed to decode source image"


def test_og_route_logs_media_failures_instead_of_silently_skipping(
    tmp_path: Path,
    monkeypatch,
    caplog,
) -> None:
    _make_image(tmp_path / "gallery" / "sample.jpg")
    storage = MemoryStorage(str(tmp_path))

    def _raise(_path: str) -> bytes:
        raise MediaDecodeError("/gallery/sample.jpg", "corrupt payload")

    monkeypatch.setattr(storage, "get_thumbnail", _raise)

    with caplog.at_level(logging.WARNING):
        with TestClient(create_app_from_storage(storage, og_preview=True)) as client:
            response = client.get("/og-image", params={"path": "/gallery/sample.jpg"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert "og thumbnail generation failed" in caplog.text
