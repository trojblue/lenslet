import types
import urllib.request

import pytest

from lenslet.storage.dataset import DatasetStorage


class _FakeResponse:
    """Minimal context manager to fake urllib responses."""

    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):  # pragma: no cover - nothing to clean up
        return False

    def read(self) -> bytes:
        return self._payload


@pytest.fixture
def http_image_url():
    return "https://example.com/path/cat.jpg"


def test_http_url_index_and_read(monkeypatch, http_image_url):
    """HTTP/HTTPS URLs should be indexed and readable like local/S3 entries."""

    # Prepare storage with a single HTTP image
    ds = DatasetStorage({"web": [http_image_url]})

    # The logical path should be present in the index
    logical_path = "/web/cat.jpg"
    assert ds.exists(logical_path)
    idx = ds.get_index("/web")
    assert len(idx.items) == 1
    assert idx.items[0].path == logical_path
    assert idx.items[0].url == http_image_url

    # Mock network fetch when reading bytes
    payload = b"fake-image-data"

    def _fake_urlopen(url):
        assert url == http_image_url
        return _FakeResponse(payload)

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    data = ds.read_bytes(logical_path)
    assert data == payload

