from pathlib import Path

import pytest
from PIL import Image

from lenslet.web.cache.browse import RecursiveBrowseCache
from lenslet.web.browse import warm_recursive_cache
from lenslet.storage.memory import MemoryIndexBuildError, MemoryStorage
from lenslet.storage.memory.index import local_index_worker_count


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color=(16, 32, 64)).save(path, format="JPEG")


def test_high_fanout_root_indexes_all_child_dirs(tmp_path: Path):
    for i in range(MemoryStorage.LEAF_BATCH_MAX_DIRS + 4):
        (tmp_path / f"task_{i:04d}").mkdir(parents=True, exist_ok=True)

    storage = MemoryStorage(str(tmp_path))

    root_index = storage.load_index("/")
    assert root_index is not None
    assert len(root_index.dirs) == MemoryStorage.LEAF_BATCH_MAX_DIRS + 4


def test_local_index_worker_count_respects_cpu_total_and_max() -> None:
    assert local_index_worker_count(total=0, max_workers=16, cpu_count=lambda: 8) == 0
    assert local_index_worker_count(total=2, max_workers=16, cpu_count=lambda: 8) == 2
    assert local_index_worker_count(total=100, max_workers=16, cpu_count=lambda: 8) == 8
    assert local_index_worker_count(total=100, max_workers=16, cpu_count=lambda: None) == 1


def test_small_folder_index_builds_expected_items(tmp_path: Path):
    _make_image(tmp_path / "task_a" / "one.jpg")
    _make_image(tmp_path / "task_a" / "two.jpg")

    storage = MemoryStorage(str(tmp_path))

    index = storage.load_index("/task_a")
    assert index is not None
    assert {item.name for item in index.items} == {"one.jpg", "two.jpg"}


def test_recursive_index_build_uses_lightweight_item_shape(tmp_path: Path):
    _make_image(tmp_path / "task_a" / "one.jpg")
    _make_image(tmp_path / "task_a" / "two.jpg")
    storage = MemoryStorage(str(tmp_path))

    index = storage.load_recursive_index("/task_a")
    assert index is not None
    assert all(item.width == 0 for item in index.items)
    assert all(item.height == 0 for item in index.items)


def test_full_index_rebuilds_after_recursive_lightweight_cache(tmp_path: Path):
    _make_image(tmp_path / "task_a" / "one.jpg")
    _make_image(tmp_path / "task_a" / "two.jpg")
    storage = MemoryStorage(str(tmp_path))

    lightweight = storage.load_recursive_index("/task_a")
    assert lightweight is not None
    assert all(item.width == 0 for item in lightweight.items)

    full = storage.load_index("/task_a")
    assert full is not None
    assert all(item.width > 0 for item in full.items)
    assert all(item.height > 0 for item in full.items)


def test_index_build_raises_for_unreadable_item(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_image(tmp_path / "task_a" / "one.jpg")
    _make_image(tmp_path / "task_a" / "two.jpg")
    storage = MemoryStorage(str(tmp_path))
    original_resolve_path = storage.local.resolve_path

    def _failing_resolve_path(path: str) -> str:
        if path.endswith("/two.jpg"):
            raise OSError("stat blocked")
        return original_resolve_path(path)

    monkeypatch.setattr(storage.local, "resolve_path", _failing_resolve_path)

    with pytest.raises(MemoryIndexBuildError, match=r"/task_a/two\.jpg"):
        storage.load_index("/task_a")


def test_warm_recursive_cache_uses_lightweight_indexes(tmp_path: Path, monkeypatch):
    _make_image(tmp_path / "task_a" / "one.jpg")
    _make_image(tmp_path / "task_a" / "two.jpg")
    storage = MemoryStorage(str(tmp_path))
    cache = RecursiveBrowseCache(max_memory_entries=2)

    original_recursive = storage.load_recursive_index

    def _unexpected_load_index(_path: str):
        raise AssertionError("warm recursive cache should use lightweight recursive indexes")

    monkeypatch.setattr(storage, "load_index", _unexpected_load_index)
    monkeypatch.setattr(storage, "load_recursive_index", original_recursive)

    warmed = warm_recursive_cache(storage, "/task_a", cache)
    assert warmed == 2
