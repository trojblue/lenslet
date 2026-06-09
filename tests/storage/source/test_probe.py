from __future__ import annotations

from dataclasses import dataclass
import socket

from lenslet.storage.image_media import read_dimensions_from_bytes
from lenslet.storage.source import probe_headers
from lenslet.storage.source.state import SourceBackedIndexState, SourceRowIndexState
from lenslet.storage.source.probe import (
    RemoteDimensionProbeContext,
    probe_remote_dimensions,
)
from lenslet.storage.source.probe_headers import (
    get_remote_header_bytes,
    get_remote_header_info,
    parse_content_length,
    parse_content_range,
    remote_url_has_public_address,
)


@dataclass
class _Item:
    width: int = 0
    height: int = 0
    size: int = 0


_JPEG_DIMENSION_HEADER = b"\xff\xd8\xff\xc0\x00\x11\x08\x00\x09\x00\x0c"


class _HeaderResponse:
    headers = {"Content-Length": str(len(_JPEG_DIMENSION_HEADER))}

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info) -> None:
        return None

    def read(self, _max_bytes: int) -> bytes:
        return _JPEG_DIMENSION_HEADER


def _addrinfo(address: str):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]


def test_remote_url_public_address_guard_accepts_public_https_host() -> None:
    assert remote_url_has_public_address(
        "https://images.example.test/path",
        resolver=lambda host, port, type: _addrinfo("93.184.216.34"),
    )


def test_remote_url_public_address_guard_rejects_private_resolution() -> None:
    assert not remote_url_has_public_address(
        "https://images.example.test/path",
        resolver=lambda host, port, type: _addrinfo("10.0.0.7"),
    )


def test_remote_url_public_address_guard_rejects_localhost_literals() -> None:
    assert not remote_url_has_public_address("http://127.0.0.1/image")
    assert not remote_url_has_public_address("http://[::1]/image")


def test_remote_url_public_address_guard_rejects_non_default_ports() -> None:
    assert not remote_url_has_public_address(
        "https://images.example.test:8443/path",
        resolver=lambda host, port, type: _addrinfo("93.184.216.34"),
    )


def test_remote_url_public_address_guard_rejects_credentials() -> None:
    assert not remote_url_has_public_address(
        "https://user:password@images.example.test/path",
        resolver=lambda host, port, type: _addrinfo("93.184.216.34"),
    )


def test_parse_content_headers_ignore_invalid_totals() -> None:
    assert parse_content_range("bytes 0-99/1234") == 1234
    assert parse_content_range("bytes 0-99/*") is None
    assert parse_content_range("not-a-range") is None
    assert parse_content_length("2048") == 2048
    assert parse_content_length("unknown") is None


def test_remote_header_bytes_sends_image_probe_headers(monkeypatch) -> None:
    captured_headers: dict[str, str] = {}

    def fake_open(request, *args, **kwargs):  # noqa: ANN001, ARG001
        captured_headers.update({key.lower(): value for key, value in request.header_items()})
        return _HeaderResponse()

    monkeypatch.setattr(probe_headers, "open_http_url", fake_open)

    header, total = get_remote_header_bytes("https://images.example.test/r2/encoded-key", max_bytes=64)

    assert header == _JPEG_DIMENSION_HEADER
    assert total == len(_JPEG_DIMENSION_HEADER)
    assert captured_headers["range"] == "bytes=0-63"
    assert captured_headers["accept"].startswith("image/")
    assert captured_headers["user-agent"] == "lenslet-image-probe/1.0"


def test_remote_header_info_parses_extensionless_image_from_magic_header() -> None:
    dims, total = get_remote_header_info(
        "https://images.example.test/r2/encoded-key",
        "encoded-key",
        max_bytes=64,
        read_dimensions_from_bytes=read_dimensions_from_bytes,
        get_remote_header_bytes_fn=lambda _url, _max_bytes: (_JPEG_DIMENSION_HEADER, 321),
    )

    assert dims == (12, 9)
    assert total == 321


def test_probe_remote_dimensions_updates_index_and_row_state() -> None:
    item = _Item()
    index_state = SourceBackedIndexState()
    row_state = SourceRowIndexState(row_dimensions=[None], path_to_row={"/cat.jpg": 0})
    progress: list[tuple[int, int, str]] = []
    context = RemoteDimensionProbeContext(
        effective_remote_workers=lambda total: 1,
        is_s3_uri=lambda source: False,
        get_presigned_url=lambda source: source,
        get_remote_header_info=lambda _url, _name: ((12, 9), 123),
        progress=lambda done, total, label: progress.append((done, total, label)),
    )

    probe_remote_dimensions(
        context,
        index_state,
        row_state,
        [("/cat.jpg", item, "https://images.example.test/cat.jpg", "cat.jpg")],
    )

    assert index_state.dimensions == {"/cat.jpg": (12, 9)}
    assert item.width == 12
    assert item.height == 9
    assert item.size == 123
    assert row_state.row_dimensions == [(12, 9)]
    assert progress == [(1, 1, "remote headers")]


def test_probe_remote_dimensions_skips_failed_s3_presign() -> None:
    item = _Item()
    progress: list[tuple[int, int, str]] = []

    def fail_presign(_source: str) -> str:
        raise RuntimeError("no credentials")

    def fail_header_probe(_url: str, _name: str):
        raise AssertionError("header probe should not run without a presigned URL")

    context = RemoteDimensionProbeContext(
        effective_remote_workers=lambda total: 1,
        is_s3_uri=lambda source: source.startswith("s3://"),
        get_presigned_url=fail_presign,
        get_remote_header_info=fail_header_probe,
        progress=lambda done, total, label: progress.append((done, total, label)),
    )
    index_state = SourceBackedIndexState()

    probe_remote_dimensions(
        context,
        index_state,
        None,
        [("/cat.jpg", item, "s3://bucket/cat.jpg", "cat.jpg")],
    )

    assert index_state.dimensions == {}
    assert item.width == 0
    assert item.height == 0
    assert progress == [(1, 1, "remote headers")]
