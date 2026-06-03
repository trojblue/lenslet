from __future__ import annotations

import logging
import threading
import time

from lenslet.web.cache.browse import RecursiveBrowseCache, RecursiveCachedItemSnapshot
from lenslet.web.cache.browse import CACHE_PERSIST_QUEUED, CACHE_PERSIST_SKIPPED, CACHE_PERSIST_WRITTEN
from lenslet.web.cache.browse_snapshot import RecursiveSnapshotWindow
from lenslet.web.browse import _record_recursive_cache_persist_status
from lenslet.web.hotpath import HotpathTelemetry


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


def test_recursive_snapshot_window_round_trips_payloads() -> None:
    items = [_snapshot("/animals/cat.jpg", 1), _snapshot("/animals/dog.jpg", 2)]
    window = RecursiveSnapshotWindow(
        scope_path="/animals",
        sort_mode="name",
        generation="gen",
        items=tuple(items),
    )

    payload = items[0].to_payload()
    restored = RecursiveCachedItemSnapshot.from_payload(payload)

    assert window.total_items == 2
    assert window.scope_path == "/animals"
    assert payload == {
        "path": "/animals/cat.jpg",
        "name": "cat.jpg",
        "mime": "image/jpeg",
        "width": 640,
        "height": 480,
        "size": 2049,
        "mtime": 1700000001.0,
        "source": "s3://bucket/source-0001",
        "metrics": {"score": 1.0},
    }
    assert restored.path == "/animals/cat.jpg"
    assert restored.metrics == {"score": 1.0}


def test_recursive_snapshot_window_round_trips_metric_labels() -> None:
    item = RecursiveCachedItemSnapshot(
        path="/animals/cat.jpg",
        name="cat.jpg",
        mime="image/jpeg",
        width=640,
        height=480,
        size=2048,
        mtime=1700000000.0,
        metrics={"style": 0.0},
        metric_labels={"style": "anime"},
    )

    restored = RecursiveCachedItemSnapshot.from_payload(item.to_payload())

    assert restored.metrics == {"style": 0.0}
    assert restored.metric_labels == {"style": "anime"}


def test_recursive_snapshot_window_round_trips_categoricals() -> None:
    item = RecursiveCachedItemSnapshot(
        path="/gallery/a.jpg",
        name="a.jpg",
        mime="image/jpeg",
        width=8,
        height=6,
        size=1,
        mtime=1.0,
        categoricals={"l0r_viewpoint_family": "frontal"},
    )

    restored = RecursiveCachedItemSnapshot.from_payload(item.to_payload())

    assert restored.categoricals == {"l0r_viewpoint_family": "frontal"}


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


def test_recursive_browse_cache_save_reports_persistence_status(tmp_path):
    persisted = RecursiveBrowseCache(
        cache_dir=tmp_path / "browse-cache",
        max_disk_bytes=20_000,
    )
    _window, written_status = persisted.save(
        "/gallery",
        "scan",
        "gen-1",
        [_snapshot("/gallery/a.jpg", seed=1)],
    )

    memory_only = RecursiveBrowseCache(max_disk_bytes=20_000)
    _window, skipped_status = memory_only.save(
        "/gallery",
        "scan",
        "gen-1",
        [_snapshot("/gallery/a.jpg", seed=1)],
    )

    assert written_status == CACHE_PERSIST_WRITTEN
    assert skipped_status == CACHE_PERSIST_SKIPPED


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

    _window, queued_status = cache.save(
        "/gallery",
        "scan",
        "gen-1",
        [_snapshot("/gallery/persist-later.jpg", seed=99)],
        defer_persist=True,
    )
    assert queued_status == CACHE_PERSIST_QUEUED
    assert started.wait(timeout=1.0) is True

    _window, duplicate_status = cache.save(
        "/gallery",
        "scan",
        "gen-1",
        [_snapshot("/gallery/duplicate.jpg", seed=100)],
        defer_persist=True,
    )
    assert duplicate_status == CACHE_PERSIST_SKIPPED

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


def test_recursive_cache_persist_status_metrics_are_distinct() -> None:
    telemetry = HotpathTelemetry()

    _record_recursive_cache_persist_status(telemetry, CACHE_PERSIST_WRITTEN)
    _record_recursive_cache_persist_status(telemetry, CACHE_PERSIST_QUEUED)
    _record_recursive_cache_persist_status(telemetry, CACHE_PERSIST_SKIPPED)

    counters = telemetry.snapshot().counters
    assert counters["folders_recursive_cache_persist_write_total"] == 1
    assert counters["folders_recursive_cache_persist_queued_total"] == 1
    assert counters["folders_recursive_cache_persist_skipped_total"] == 1


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
