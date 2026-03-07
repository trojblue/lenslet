from __future__ import annotations

from lenslet.server_factory import DEFAULT_THUMB_CACHE_CAP_BYTES, _thumb_cache_from_workspace
from lenslet.thumb_cache import ThumbCache
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
