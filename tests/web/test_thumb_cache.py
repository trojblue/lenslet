from __future__ import annotations

import logging
from pathlib import Path

from lenslet.web.factory import DEFAULT_THUMB_CACHE_CAP_BYTES, _thumb_cache_from_workspace
from lenslet.web.cache.thumbs import ThumbCache
from lenslet.workspace import Workspace


def test_thumb_cache_enforces_max_disk_bytes(tmp_path):
    cache = ThumbCache(tmp_path / "thumbs", max_disk_bytes=10)

    cache.set("a", b"12345678")
    cache.set("b", b"12345678")

    cached_files = list((tmp_path / "thumbs").rglob("*.webp"))
    total_bytes = sum(path.stat().st_size for path in cached_files)

    assert total_bytes <= 10


def test_thumb_cache_from_workspace_uses_default_cap(tmp_path):
    workspace = Workspace(root=tmp_path / ".lenslet", can_write=True, is_temp=False)

    cache = _thumb_cache_from_workspace(workspace, enabled=True)

    assert isinstance(cache, ThumbCache)
    assert cache.max_disk_bytes == DEFAULT_THUMB_CACHE_CAP_BYTES


def test_thumb_cache_records_read_failures(tmp_path, monkeypatch, caplog):
    cache = ThumbCache(tmp_path / "thumbs")

    def _fail(_self: Path) -> bytes:
        raise OSError("forced read failure")

    monkeypatch.setattr(Path, "read_bytes", _fail)
    with caplog.at_level(logging.WARNING):
        assert cache.get("a") is None

    assert cache.last_failure is not None
    assert cache.last_failure.operation == "read"
    assert "thumb cache read failed" in caplog.text
