from __future__ import annotations

import asyncio
import logging
import threading
import time
from pathlib import Path

import pytest
from fastapi import HTTPException
from PIL import Image

from lenslet.web.cache.thumbs import ThumbCache
from lenslet.web.hotpath import HotpathTelemetry
from lenslet.web.media import thumb_response_async
from lenslet.web.thumbs import (
    MAX_INFLIGHT_THUMBNAILS,
    MAX_QUEUED_THUMBNAILS,
    MAX_THUMBNAIL_WORKERS,
    ThumbnailBusy,
    ThumbnailScheduler,
)


class _ConnectedRequest:
    @staticmethod
    async def is_disconnected() -> bool:
        return False


def _webp_bytes(path: Path) -> bytes:
    Image.new("RGB", (8, 6), color=(20, 40, 60)).save(path, format="WEBP")
    return path.read_bytes()


def test_thumbnail_scheduler_enforces_worker_queue_and_deduplication_caps() -> None:
    scheduler: ThumbnailScheduler[bytes] = ThumbnailScheduler(max_workers=99)
    release = threading.Event()
    all_started = threading.Event()
    started_count = 0
    count_lock = threading.Lock()

    def _block() -> bytes:
        nonlocal started_count
        with count_lock:
            started_count += 1
            if started_count == MAX_THUMBNAIL_WORKERS:
                all_started.set()
        release.wait(timeout=2)
        return b"done"

    try:
        futures = [scheduler.submit(f"active-{index}", _block) for index in range(4)]
        assert all_started.wait(timeout=1)
        stats = scheduler.stats()
        assert stats["workers"] == MAX_THUMBNAIL_WORKERS
        assert stats["active"] == MAX_THUMBNAIL_WORKERS
        assert stats["queue_capacity"] == MAX_QUEUED_THUMBNAILS
        assert stats["inflight_capacity"] == MAX_INFLIGHT_THUMBNAILS
    finally:
        release.set()
        for future in futures:
            assert future.result(timeout=1) == b"done"
        scheduler.close()

    queue_limited: ThumbnailScheduler[bytes] = ThumbnailScheduler(
        max_workers=1,
        max_queue_size=2,
        max_inflight_entries=10,
    )
    started = threading.Event()
    release = threading.Event()
    try:
        active = queue_limited.submit("active", lambda: _wait_and_return(started, release))
        assert started.wait(timeout=1)
        queued = [
            queue_limited.submit("queued-1", lambda: b"one"),
            queue_limited.submit("queued-2", lambda: b"two"),
        ]
        with pytest.raises(ThumbnailBusy, match="queue is full"):
            queue_limited.submit("overflow", lambda: b"overflow")
        assert queue_limited.stats()["queued"] == 2
        assert queue_limited.stats()["inflight"] == 3
    finally:
        release.set()
        assert active.result(timeout=1) == b"active"
        assert {future.result(timeout=1) for future in queued} == {b"one", b"two"}
        queue_limited.close()

    inflight_limited: ThumbnailScheduler[bytes] = ThumbnailScheduler(
        max_workers=1,
        max_queue_size=10,
        max_inflight_entries=2,
    )
    started = threading.Event()
    release = threading.Event()
    try:
        active = inflight_limited.submit("active", lambda: _wait_and_return(started, release))
        assert started.wait(timeout=1)
        queued_future = inflight_limited.submit("queued", lambda: b"queued")
        with pytest.raises(ThumbnailBusy, match="deduplication table is full"):
            inflight_limited.submit("overflow", lambda: b"overflow")
    finally:
        release.set()
        assert active.result(timeout=1) == b"active"
        assert queued_future.result(timeout=1) == b"queued"
        inflight_limited.close()


def _wait_and_return(started: threading.Event, release: threading.Event) -> bytes:
    started.set()
    release.wait(timeout=2)
    return b"active"


def test_thumbnail_scheduler_joins_identical_work_and_drops_unsubscribed_queue() -> None:
    joined_scheduler: ThumbnailScheduler[bytes] = ThumbnailScheduler(max_workers=1)
    joined_started = threading.Event()
    release_joined = threading.Event()
    joined_calls = 0

    def _joined_once() -> bytes:
        nonlocal joined_calls
        joined_calls += 1
        joined_started.set()
        release_joined.wait(timeout=2)
        return b"shared"

    try:
        first_joined = joined_scheduler.submit("shared", _joined_once)
        assert joined_started.wait(timeout=1)
        second_joined = joined_scheduler.submit(
            "shared",
            lambda: pytest.fail("duplicate operation ran"),
        )
        release_joined.set()
        assert first_joined.result(timeout=1) == b"shared"
        assert second_joined.result(timeout=1) == b"shared"
        assert joined_calls == 1
    finally:
        release_joined.set()
        joined_scheduler.close()

    scheduler: ThumbnailScheduler[bytes] = ThumbnailScheduler(max_workers=1)
    blocker_started = threading.Event()
    release_blocker = threading.Event()
    calls = 0
    try:
        blocker = scheduler.submit(
            "blocker",
            lambda: _wait_and_return(blocker_started, release_blocker),
        )
        assert blocker_started.wait(timeout=1)

        def _once() -> bytes:
            nonlocal calls
            calls += 1
            return b"shared"

        first = scheduler.submit("shared", _once)
        second = scheduler.submit("shared", lambda: pytest.fail("duplicate operation ran"))
        assert scheduler.stats()["waiters"] == 3
        assert scheduler.cancel("shared", first) == "none"
        assert first.cancelled()
        assert scheduler.cancel("shared", second) == "queued"
        assert second.cancelled()
        assert scheduler.stats()["queued"] == 0
        assert calls == 0
    finally:
        release_blocker.set()
        assert blocker.result(timeout=1) == b"active"
        scheduler.close()


def test_foreground_thumbnail_displaces_optional_queued_persistence() -> None:
    scheduler: ThumbnailScheduler[bytes] = ThumbnailScheduler(max_workers=1, max_queue_size=1)
    started = threading.Event()
    release = threading.Event()
    background_calls = 0

    def _background() -> None:
        nonlocal background_calls
        background_calls += 1

    try:
        active = scheduler.submit("active", lambda: _wait_and_return(started, release))
        assert started.wait(timeout=1)
        assert scheduler.submit_background("persist", _background)
        foreground = scheduler.submit("visible", lambda: b"visible")
        assert scheduler.stats()["queued"] == 1
        release.set()
        assert active.result(timeout=1) == b"active"
        assert foreground.result(timeout=1) == b"visible"
        assert background_calls == 0
        assert scheduler.diagnostics()["thumbnail_background_dropped_total"] == 1
    finally:
        release.set()
        scheduler.close()


def test_background_persistence_leaves_workers_available_for_foreground() -> None:
    scheduler: ThumbnailScheduler[bytes] = ThumbnailScheduler(max_workers=2)
    background_started = threading.Event()
    release_background = threading.Event()

    def _background() -> None:
        background_started.set()
        release_background.wait(timeout=2)

    try:
        assert scheduler.submit_background("persist-1", _background)
        assert background_started.wait(timeout=1)
        assert scheduler.submit_background("persist-2", lambda: None)
        foreground = scheduler.submit("visible", lambda: b"visible")
        assert foreground.result(timeout=0.25) == b"visible"
        stats = scheduler.diagnostics()
        assert stats["thumbnail_active_background_work"] == 1
        assert stats["thumbnail_queued_work"] == 1
    finally:
        release_background.set()
        scheduler.close()


def test_thumbnail_admission_failure_returns_explicit_503() -> None:
    scheduler: ThumbnailScheduler[bytes] = ThumbnailScheduler(max_workers=1, max_queue_size=1)
    started = threading.Event()
    release = threading.Event()
    metrics = HotpathTelemetry()
    try:
        active = scheduler.submit("active", lambda: _wait_and_return(started, release))
        assert started.wait(timeout=1)
        queued = scheduler.submit("queued", lambda: b"queued")

        class Storage:
            @staticmethod
            def get_or_build_thumbnail(_path: str) -> bytes:
                return b"unreachable"

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                thumb_response_async(
                    Storage(),
                    "/busy.jpg",
                    _ConnectedRequest(),
                    scheduler,
                    hotpath_metrics=metrics,
                )
            )
        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "thumbnail_busy"
        assert exc_info.value.headers == {"Retry-After": "1"}
        assert metrics.snapshot().counters["thumbnail_busy_total"] == 1
    finally:
        release.set()
        assert active.result(timeout=1) == b"active"
        assert queued.result(timeout=1) == b"queued"
        scheduler.close()


def test_generated_thumbnail_returns_before_best_effort_persistence() -> None:
    scheduler = ThumbnailScheduler(max_workers=1)
    persist_started = threading.Event()
    release_persist = threading.Event()

    class Cache:
        @staticmethod
        def get(_key: str) -> None:
            return None

        @staticmethod
        def set(_key: str, _content: bytes) -> bool:
            persist_started.set()
            release_persist.wait(timeout=2)
            return True

    class Storage:
        @staticmethod
        def get_cached_thumbnail(_path: str) -> None:
            return None

        @staticmethod
        def thumbnail_cache_key(_path: str) -> str:
            return "cache-key"

        @staticmethod
        def get_or_build_thumbnail(_path: str) -> bytes:
            return b"generated"

    try:
        response = asyncio.run(
            thumb_response_async(
                Storage(),
                "/generated.jpg",
                _ConnectedRequest(),
                scheduler,
                Cache(),
            )
        )
        assert response.status_code == 200
        assert response.body == b"generated"
        assert persist_started.wait(timeout=1)
        assert not release_persist.is_set()
    finally:
        release_persist.set()
        scheduler.close()


def test_corrupt_cache_and_failed_write_do_not_fail_generated_response(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    scheduler = ThumbnailScheduler(max_workers=1)
    cache = ThumbCache(tmp_path / "thumbs")
    cache_key = "cache-key"
    assert cache.set(cache_key, b"corrupt")
    generated = _webp_bytes(tmp_path / "generated.webp")
    calls = 0

    class Storage:
        @staticmethod
        def get_cached_thumbnail(_path: str) -> None:
            return None

        @staticmethod
        def thumbnail_cache_key(_path: str) -> str:
            return cache_key

        @staticmethod
        def get_or_build_thumbnail(_path: str) -> bytes:
            nonlocal calls
            calls += 1
            return generated

    try:
        with caplog.at_level(logging.WARNING):
            response = asyncio.run(
                thumb_response_async(
                    Storage(),
                    "/corrupt.jpg",
                    _ConnectedRequest(),
                    scheduler,
                    cache,
                )
            )
        assert response.status_code == 200
        assert response.body == generated
        assert calls == 1
        assert "invalid WebP payload" in caplog.text
        deadline = time.monotonic() + 1
        while scheduler.stats()["inflight"] and time.monotonic() < deadline:
            time.sleep(0.01)
        assert cache.get(cache_key) == generated
    finally:
        scheduler.close()

    failed_scheduler = ThumbnailScheduler(max_workers=1)

    class FailedCache:
        @staticmethod
        def get(_key: str) -> None:
            return None

        @staticmethod
        def set(_key: str, _content: bytes) -> bool:
            return False

    try:
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            response = asyncio.run(
                thumb_response_async(
                    Storage(),
                    "/failed-write.jpg",
                    _ConnectedRequest(),
                    failed_scheduler,
                    FailedCache(),
                )
            )
            deadline = time.monotonic() + 1
            while failed_scheduler.stats()["inflight"] and time.monotonic() < deadline:
                time.sleep(0.01)
        assert response.status_code == 200
        assert response.body == generated
        assert "thumbnail cache persistence failed" in caplog.text
    finally:
        failed_scheduler.close()
