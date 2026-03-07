from __future__ import annotations

from lenslet.og_cache import OgImageCache


def _png_files(root):
    return sorted(root.rglob("*.png"))


def test_og_cache_prunes_oldest_entries_when_over_limit(tmp_path):
    cache = OgImageCache(tmp_path, max_entries=2)

    cache.set("k1", b"data-1")
    cache.set("k2", b"data-2")
    cache.set("k3", b"data-3")

    assert cache.get("k1") is None
    assert cache.get("k2") == b"data-2"
    assert cache.get("k3") == b"data-3"
    assert len(_png_files(tmp_path)) == 2


def test_og_cache_rejects_zero_or_negative_max_entries(tmp_path):
    cache = OgImageCache(tmp_path, max_entries=0)

    cache.set("k1", b"data-1")
    cache.set("k2", b"data-2")

    assert cache.get("k1") is None
    assert cache.get("k2") == b"data-2"
    assert len(_png_files(tmp_path)) == 1
