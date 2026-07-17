from __future__ import annotations

import logging
from pathlib import Path

from lenslet.web.app.shared import DEFAULT_THUMB_CACHE_CAP_BYTES, thumb_cache_from_workspace
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

    cache = thumb_cache_from_workspace(workspace, enabled=True)

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


def test_thumb_cache_cleans_atomic_temp_file_after_write_failure(tmp_path, monkeypatch):
    cache_root = tmp_path / "thumbs"
    cache = ThumbCache(cache_root)

    def _fail_replace(_source: Path, _target: Path) -> None:
        raise OSError("forced replace failure")

    monkeypatch.setattr("lenslet.web.cache.thumbs.os.replace", _fail_replace)

    assert not cache.set("a", b"thumbnail")
    assert not list(cache_root.rglob("*.tmp"))
    assert not list(cache_root.rglob("*.webp"))
    assert cache.last_failure is not None
    assert cache.last_failure.operation == "write"


def test_thumb_cache_does_not_fsync_best_effort_thumbnail_files(tmp_path, monkeypatch):
    cache = ThumbCache(tmp_path / "thumbs")

    def _fail_fsync(_fd: int) -> None:
        raise AssertionError("best-effort thumbnail persistence must not fsync")

    monkeypatch.setattr("lenslet.web.cache.thumbs.os.fsync", _fail_fsync)

    assert cache.set("a", b"thumbnail")
