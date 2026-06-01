import urllib.request
from pathlib import Path

import pytest
from PIL import Image

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


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (12, 8), color=(44, 88, 132)).save(path, format="JPEG")


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


@pytest.mark.parametrize(
    ("sources", "expected_items", "expected_dirs"),
    [
        pytest.param(
            "local",
            ["/demo/a.jpg", "/demo/sub/c.jpg"],
            ["sub"],
            id="local",
        ),
        pytest.param(
            [
                "https://example.com/gallery/a.jpg",
                "https://example.com/gallery/sub/c.jpg",
            ],
            ["/demo/a.jpg", "/demo/sub/c.jpg"],
            ["sub"],
            id="http",
        ),
        pytest.param(
            [
                "s3://bucket/gallery/a.jpg",
                "s3://bucket/gallery/sub/c.jpg",
            ],
            ["/demo/a.jpg", "/demo/sub/c.jpg"],
            ["sub"],
            id="s3",
        ),
    ],
)
def test_dataset_storage_keeps_nested_folder_indexes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sources,
    expected_items: list[str],
    expected_dirs: list[str],
) -> None:
    if sources == "local":
        local_a = tmp_path / "gallery" / "a.jpg"
        local_c = tmp_path / "gallery" / "sub" / "c.jpg"
        _make_image(local_a)
        _make_image(local_c)
        source_values = [str(local_a), str(local_c)]
    else:
        source_values = sources
        monkeypatch.setattr(DatasetStorage, "_probe_remote_dimensions", lambda self, tasks, label=None: None)

    storage = DatasetStorage({"demo": source_values})

    demo_index = storage.get_index("/demo")
    assert [item.path for item in demo_index.items] == [expected_items[0]]
    assert demo_index.dirs == expected_dirs

    sub_index = storage.get_index("/demo/sub")
    assert [item.path for item in sub_index.items] == [expected_items[1]]
    assert sub_index.dirs == []


def test_dataset_storage_dedupes_colliding_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    local_cat = tmp_path / "local" / "cat.jpg"
    _make_image(local_cat)
    monkeypatch.setattr(DatasetStorage, "_probe_remote_dimensions", lambda self, tasks, label=None: None)

    storage = DatasetStorage(
        {
            "mixed": [
                str(local_cat),
                "https://example.com/cat.jpg",
            ]
        }
    )

    mixed_index = storage.get_index("/mixed")
    assert [item.path for item in mixed_index.items] == [
        "/mixed/cat.jpg",
        "/mixed/cat-2.jpg",
    ]
