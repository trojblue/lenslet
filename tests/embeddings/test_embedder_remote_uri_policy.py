from __future__ import annotations

from pathlib import Path

import pytest

from lenslet.embeddings import embedder


def test_read_bytes_rejects_http_uri_by_default() -> None:
    with pytest.raises(ValueError, match="Remote URIs are disabled"):
        embedder._read_bytes("http://example.com/image.jpg", allow_remote_uris=False)


def test_read_bytes_rejects_s3_uri_by_default() -> None:
    with pytest.raises(ValueError, match="Remote URIs are disabled"):
        embedder._read_bytes("s3://bucket/key.jpg", allow_remote_uris=False)


def test_read_bytes_reads_local_file_when_remote_disabled(tmp_path: Path) -> None:
    path = tmp_path / "sample.bin"
    payload = b"abc123"
    path.write_bytes(payload)

    assert embedder._read_bytes(str(path), allow_remote_uris=False) == payload
