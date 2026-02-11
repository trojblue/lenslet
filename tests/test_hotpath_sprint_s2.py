from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.testclient import TestClient
from PIL import Image

from lenslet.server import _file_response, create_app
from lenslet.storage.memory import MemoryStorage


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color=(64, 128, 192)).save(path, format="JPEG")


def test_index_og_preview_does_not_call_subtree_count(tmp_path: Path, monkeypatch) -> None:
    _make_image(tmp_path / "gallery" / "sample.jpg")
    app = create_app(str(tmp_path), og_preview=True)
    client = TestClient(app)

    def _fail_subtree_count(*_args, **_kwargs):
        raise AssertionError("subtree_image_count must not be called by /index.html")

    monkeypatch.setattr("lenslet.server.og.subtree_image_count", _fail_subtree_count)

    resp = client.get("/index.html", params={"path": "/gallery"})
    assert resp.status_code == 200
    assert '<meta property="og:title"' in resp.text
    assert '<meta property="og:image"' in resp.text


def test_file_route_streams_local_file_without_read_bytes(tmp_path: Path, monkeypatch) -> None:
    _make_image(tmp_path / "gallery" / "sample.jpg")

    def _fail_read_bytes(self, _path: str) -> bytes:
        raise AssertionError("MemoryStorage.read_bytes should not be used for local /file responses")

    monkeypatch.setattr(MemoryStorage, "read_bytes", _fail_read_bytes)

    client = TestClient(create_app(str(tmp_path)))
    resp = client.get("/file", params={"path": "/gallery/sample.jpg"})

    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("image/jpeg")
    assert resp.headers.get("accept-ranges") == "bytes"
    assert resp.content


def test_file_response_uses_streaming_when_local_source_path_exists(tmp_path: Path) -> None:
    local_path = tmp_path / "sample.jpg"
    _make_image(local_path)

    class _LocalSourceStorage:
        def __init__(self, source_path: Path):
            self._source_path = source_path
            self.read_calls = 0

        def get_source_path(self, _logical_path: str) -> str:
            return str(self._source_path)

        def read_bytes(self, _path: str) -> bytes:
            self.read_calls += 1
            return b"unexpected"

        @staticmethod
        def _guess_mime(_path: str) -> str:
            return "image/jpeg"

    storage = _LocalSourceStorage(local_path)
    response = _file_response(storage, "/logical/sample.jpg")

    assert isinstance(response, FileResponse)
    assert response.path == str(local_path)
    assert response.stat_result is not None
    assert response.stat_result.st_size == local_path.stat().st_size
    assert storage.read_calls == 0


def test_file_response_falls_back_for_non_local_sources() -> None:
    class _RemoteSourceStorage:
        def __init__(self):
            self.read_calls = 0

        @staticmethod
        def get_source_path(_logical_path: str) -> str:
            return "s3://bucket/key.jpg"

        def read_bytes(self, _path: str) -> bytes:
            self.read_calls += 1
            return b"remote-bytes"

        @staticmethod
        def _guess_mime(_path: str) -> str:
            return "image/jpeg"

    storage = _RemoteSourceStorage()
    response = _file_response(storage, "/logical/remote.jpg")

    assert not isinstance(response, FileResponse)
    assert response.media_type == "image/jpeg"
    assert response.body == b"remote-bytes"
    assert storage.read_calls == 1
