from __future__ import annotations

import logging
import threading
import time

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


def test_recursive_browse_cache_invalidate_path_keeps_unrelated_persisted_entries(tmp_path):
    cache_dir = tmp_path / "browse-cache"
    seeded = RecursiveBrowseCache(
        cache_dir=cache_dir,
        max_disk_bytes=20_000,
        max_memory_entries=2,
    )
    seeded.save("/", "scan", "gen-root", [_snapshot("/gallery/root.jpg", seed=1)])
    seeded.save("/gallery", "scan", "gen-gallery", [_snapshot("/gallery/a.jpg", seed=2)])
    seeded.save(
        "/gallery/child",
        "scan",
        "gen-child",
        [_snapshot("/gallery/child/b.jpg", seed=3)],
    )
    seeded.save(
        "/gallery/sibling",
        "scan",
        "gen-sibling",
        [_snapshot("/gallery/sibling/c.jpg", seed=4)],
    )
    seeded.save("/other", "scan", "gen-other", [_snapshot("/other/d.jpg", seed=5)])

    cache = RecursiveBrowseCache(
        cache_dir=cache_dir,
        max_disk_bytes=20_000,
        max_memory_entries=2,
    )
    assert cache.load("/", "scan", "gen-root") is not None
    assert cache.load("/gallery/sibling", "scan", "gen-sibling") is not None
    assert cache.load("/other", "scan", "gen-other") is not None

    cache.invalidate_path("/gallery/child")

    assert cache.load("/", "scan", "gen-root") is None
    assert cache.load("/gallery", "scan", "gen-gallery") is None
    assert cache.load("/gallery/child", "scan", "gen-child") is None
    assert cache.load("/gallery/sibling", "scan", "gen-sibling") is not None
    assert cache.load("/other", "scan", "gen-other") is not None


def test_recursive_browse_cache_invalidate_path_cancels_pending_persist_write(tmp_path, monkeypatch):
    cache = RecursiveBrowseCache(
        cache_dir=tmp_path / "browse-cache",
        max_disk_bytes=20_000,
        max_memory_entries=4,
    )
    started = threading.Event()
    release = threading.Event()
    original_save = cache._save_disk_window

    def _blocking_save(window, *, cancel_event=None):
        started.set()
        release.wait(timeout=1.0)
        return original_save(window, cancel_event=cancel_event)

    monkeypatch.setattr(cache, "_save_disk_window", _blocking_save)

    cache.save(
        "/gallery",
        "scan",
        "gen-1",
        [_snapshot("/gallery/persist-later.jpg", seed=99)],
        defer_persist=True,
    )
    assert started.wait(timeout=1.0) is True

    cache.invalidate_path("/gallery")
    release.set()

    deadline = time.monotonic() + 2.0
    while cache._persist_jobs and time.monotonic() < deadline:
        time.sleep(0.01)

    assert cache._persist_jobs == {}
    assert cache.load("/gallery", "scan", "gen-1") is None


def test_recursive_browse_cache_invalidate_path_cancels_pending_warm(tmp_path):
    cache = RecursiveBrowseCache(
        cache_dir=tmp_path / "browse-cache",
        max_disk_bytes=20_000,
        max_memory_entries=4,
    )
    started = threading.Event()
    release = threading.Event()

    def _producer(_cancel_event: threading.Event):
        started.set()
        release.wait(timeout=1.0)
        return [_snapshot("/gallery/later.jpg", seed=42)]

    scheduled = cache.schedule_warm("/gallery", "scan", "gen-1", _producer)
    assert scheduled is True
    assert started.wait(timeout=1.0) is True

    cache.invalidate_path("/gallery")
    release.set()

    deadline = time.monotonic() + 2.0
    while cache.pending_warm_count() > 0 and time.monotonic() < deadline:
        time.sleep(0.01)

    assert cache.pending_warm_count() == 0
    assert cache.load("/gallery", "scan", "gen-1") is None


def test_recursive_browse_cache_records_invalid_disk_payload(tmp_path, caplog):
    cache = RecursiveBrowseCache(
        cache_dir=tmp_path / "browse-cache",
        max_disk_bytes=20_000,
        max_memory_entries=2,
    )
    disk_path = cache._disk_path_for("/gallery", "scan", "gen-1")
    disk_path.parent.mkdir(parents=True, exist_ok=True)
    disk_path.write_bytes(b"not a gzip payload")

    with caplog.at_level(logging.WARNING):
        assert cache.load("/gallery", "scan", "gen-1") is None

    assert cache.last_failure is not None
    assert cache.last_failure.operation == "read"
    assert "browse cache read failed" in caplog.text
