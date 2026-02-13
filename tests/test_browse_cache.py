from __future__ import annotations

from lenslet.browse_cache import RecursiveBrowseCache, RecursiveCachedItemSnapshot


def _snapshot(path: str, seed: int) -> RecursiveCachedItemSnapshot:
    return RecursiveCachedItemSnapshot(
        path=path,
        name=path.rsplit("/", 1)[-1],
        mime="image/jpeg",
        width=640,
        height=480,
        size=2048 + seed,
        mtime=1700000000.0 + float(seed),
        source=f"s3://bucket/source-{seed:04d}",
        metrics={"score": float(seed)},
    )


def test_recursive_browse_cache_enforces_disk_cap(tmp_path):
    cap_bytes = 8_000
    cache = RecursiveBrowseCache(
        cache_dir=tmp_path / "browse-cache",
        max_disk_bytes=cap_bytes,
        max_memory_entries=3,
    )

    for idx in range(8):
        items = [
            _snapshot(f"/scope_{idx}/img_{img_idx:03d}.jpg", seed=idx * 100 + img_idx)
            for img_idx in range(40)
        ]
        cache.save(f"/scope_{idx}", "scan", f"gen-{idx}", items)

    assert cache.disk_usage_bytes() <= cap_bytes


def test_recursive_browse_cache_invalidate_path_clears_matching_entries(tmp_path):
    cache = RecursiveBrowseCache(
        cache_dir=tmp_path / "browse-cache",
        max_disk_bytes=20_000,
        max_memory_entries=4,
    )
    cache.save("/gallery", "scan", "gen-1", [_snapshot("/gallery/a.jpg", seed=1)])

    before = cache.load("/gallery", "scan", "gen-1")
    assert before is not None

    cache.invalidate_path("/gallery")

    after = cache.load("/gallery", "scan", "gen-1")
    assert after is None
