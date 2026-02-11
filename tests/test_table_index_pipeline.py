from __future__ import annotations

from pathlib import Path

from PIL import Image

from lenslet.storage.table import TableStorage


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (12, 9), color=(60, 90, 120)).save(path, format="JPEG")


def test_metrics_column_overrides_scalar_metric_values(tmp_path: Path) -> None:
    image_path = tmp_path / "one.jpg"
    _make_image(image_path)

    rows = [
        {
            "source": str(image_path),
            "path": "one.jpg",
            "clip_aesthetic": 0.11,
            "metrics": {
                "clip_aesthetic": 0.91,
                "quality_score": 0.42,
            },
        }
    ]

    storage = TableStorage(rows, skip_indexing=True)
    item = storage._items["one.jpg"]

    assert abs(item.metrics["clip_aesthetic"] - 0.91) < 1e-9
    assert abs(item.metrics["quality_score"] - 0.42) < 1e-9


def test_duplicate_logical_paths_keep_stable_row_mappings(tmp_path: Path) -> None:
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    _make_image(first)
    _make_image(second)

    rows = [
        {"source": str(first), "path": "dup.jpg"},
        {"source": str(second), "path": "dup.jpg"},
    ]

    storage = TableStorage(rows, skip_indexing=True)

    assert storage.path_for_row_index(0) == "dup.jpg"
    assert storage.path_for_row_index(1) == "dup-2.jpg"
    assert storage.row_index_for_path("dup.jpg") == 0
    assert storage.row_index_for_path("dup-2.jpg") == 1

    root_index = storage.get_index("/")
    assert [item.path for item in root_index.items] == ["dup.jpg", "dup-2.jpg"]
