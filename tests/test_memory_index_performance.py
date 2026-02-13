from pathlib import Path

from PIL import Image

from lenslet.storage.memory import MemoryStorage


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color=(16, 32, 64)).save(path, format="JPEG")


def test_high_fanout_root_skips_leaf_batch_probe(tmp_path: Path, monkeypatch):
    for i in range(MemoryStorage.LEAF_BATCH_MAX_DIRS + 4):
        (tmp_path / f"task_{i:04d}").mkdir(parents=True, exist_ok=True)

    storage = MemoryStorage(str(tmp_path))
    called = False

    def _probe(path: str, dirs: list[str]) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(storage._leaf_batch, "maybe_prepare", _probe)  # type: ignore[attr-defined]

    root_index = storage.get_index("/")
    assert root_index is not None
    assert len(root_index.dirs) == MemoryStorage.LEAF_BATCH_MAX_DIRS + 4
    assert called is False


def test_small_folder_index_build_avoids_parallel_overhead(tmp_path: Path, monkeypatch):
    _make_image(tmp_path / "task_a" / "one.jpg")
    _make_image(tmp_path / "task_a" / "two.jpg")

    storage = MemoryStorage(str(tmp_path))

    def _unexpected_workers(total: int) -> int:
        raise AssertionError("small folders should not spin up parallel indexing workers")

    monkeypatch.setattr(storage, "_effective_workers", _unexpected_workers)  # type: ignore[attr-defined]

    index = storage.get_index("/task_a")
    assert index is not None
    assert {item.name for item in index.items} == {"one.jpg", "two.jpg"}


def test_recursive_index_build_skips_dimension_probe(tmp_path: Path, monkeypatch):
    _make_image(tmp_path / "task_a" / "one.jpg")
    _make_image(tmp_path / "task_a" / "two.jpg")
    storage = MemoryStorage(str(tmp_path))

    def _fail_dimensions(_path: str):
        raise AssertionError("recursive lightweight index should not read dimensions eagerly")

    monkeypatch.setattr(storage, "_read_dimensions_fast", _fail_dimensions)

    index = storage.get_index_for_recursive("/task_a")
    assert index is not None
    assert all(item.width == 0 for item in index.items)
    assert all(item.height == 0 for item in index.items)


def test_full_index_rebuilds_after_recursive_lightweight_cache(tmp_path: Path):
    _make_image(tmp_path / "task_a" / "one.jpg")
    _make_image(tmp_path / "task_a" / "two.jpg")
    storage = MemoryStorage(str(tmp_path))

    lightweight = storage.get_index_for_recursive("/task_a")
    assert lightweight is not None
    assert all(item.width == 0 for item in lightweight.items)

    full = storage.get_index("/task_a")
    assert full is not None
    assert all(item.width > 0 for item in full.items)
    assert all(item.height > 0 for item in full.items)
