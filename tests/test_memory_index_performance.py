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

