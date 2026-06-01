from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import logging
from pathlib import Path

from lenslet.web.cache.og import OgImageCache


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


def test_og_cache_records_write_failures(tmp_path, monkeypatch, caplog):
    cache = OgImageCache(tmp_path)

    def _fail(_self: Path, _target: Path) -> None:
        raise OSError("forced replace failure")

    monkeypatch.setattr(Path, "replace", _fail)
    with caplog.at_level(logging.WARNING):
        assert cache.set("k1", b"data-1") is False

    assert cache.last_failure is not None
    assert cache.last_failure.operation == "write"
    assert "og cache write failed" in caplog.text


def test_og_cache_holds_write_lock_around_mutating_write_steps(tmp_path, monkeypatch):
    cache = OgImageCache(tmp_path)
    lock_states: list[bool] = []
    mark_written = cache._mark_written

    def _mark(path: Path) -> None:
        lock_states.append(cache._lock.locked())
        mark_written(path)

    def _prune() -> None:
        lock_states.append(cache._lock.locked())

    monkeypatch.setattr(cache, "_mark_written", _mark)
    monkeypatch.setattr(cache, "_prune_if_needed", _prune)

    assert cache.set("k1", b"data-1") is True
    assert lock_states == [True, True]


def test_og_cache_concurrent_same_key_writes_do_not_share_tmp_path(tmp_path):
    cache = OgImageCache(tmp_path)
    payloads = [f"data-{idx}".encode("ascii") for idx in range(12)]

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(lambda payload: cache.set("same-key", payload), payloads))

    assert all(results)
    assert cache.get("same-key") in payloads
    assert not list(tmp_path.rglob("*.tmp"))
