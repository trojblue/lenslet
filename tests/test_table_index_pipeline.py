from __future__ import annotations

from pathlib import Path

import pytest
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


def test_local_resolution_uses_realpath_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    image_path = tmp_path / "one.jpg"
    _make_image(image_path)
    stat = image_path.stat()
    rows = [
        {
            "source": "one.jpg",
            "path": "one.jpg",
            "size": int(stat.st_size),
            "mtime": float(stat.st_mtime),
            "width": 12,
            "height": 9,
        }
    ]

    def _boom(self: TableStorage, source: str) -> str:
        raise AssertionError("strict local resolver called")

    monkeypatch.setattr(TableStorage, "_resolve_local_source", _boom)
    with pytest.raises(AssertionError, match="strict local resolver called"):
        TableStorage(
            rows,
            root=str(tmp_path),
            source_column="source",
            path_column="path",
            skip_indexing=True,
        )


def test_skip_local_realpath_validation_bypasses_strict_resolver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_path = tmp_path / "one.jpg"
    _make_image(image_path)
    stat = image_path.stat()
    rows = [
        {
            "source": "one.jpg",
            "path": "one.jpg",
            "size": int(stat.st_size),
            "mtime": float(stat.st_mtime),
            "width": 12,
            "height": 9,
        }
    ]

    def _boom(self: TableStorage, source: str) -> str:
        raise AssertionError("strict local resolver called")

    monkeypatch.setattr(TableStorage, "_resolve_local_source", _boom)
    storage = TableStorage(
        rows,
        root=str(tmp_path),
        source_column="source",
        path_column="path",
        skip_indexing=True,
        skip_local_realpath_validation=True,
    )
    assert "one.jpg" in storage._items


def test_skip_local_realpath_validation_still_blocks_lexical_escape(tmp_path: Path) -> None:
    rows = [
        {
            "source": "../outside.jpg",
            "path": "outside.jpg",
            "size": 0,
            "mtime": 0.0,
            "width": 0,
            "height": 0,
        }
    ]
    storage = TableStorage(
        rows,
        root=str(tmp_path),
        source_column="source",
        path_column="path",
        skip_indexing=True,
        skip_local_realpath_validation=True,
    )
    assert "outside.jpg" not in storage._items


def test_s3_rows_honor_explicit_path_column(tmp_path: Path) -> None:
    rows = [
        {
            "source": "s3://bucket/raw/first.jpg",
            "display_path": "logical/alpha.jpg",
        },
        {
            "source": "s3://bucket/raw/nested/second.jpg",
            "display_path": "logical/nested/beta.jpg",
        },
    ]

    storage = TableStorage(
        rows,
        root=str(tmp_path),
        source_column="source",
        path_column="display_path",
        skip_indexing=True,
    )

    assert sorted(storage._items.keys()) == [
        "logical/alpha.jpg",
        "logical/nested/beta.jpg",
    ]
    assert storage.path_for_row_index(0) == "logical/alpha.jpg"
    assert storage.path_for_row_index(1) == "logical/nested/beta.jpg"


def test_absolute_local_source_outside_root_is_blocked(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.jpg"
    _make_image(outside)

    rows = [
        {
            "source": str(outside),
            "path": "outside.jpg",
            "size": int(outside.stat().st_size),
            "mtime": float(outside.stat().st_mtime),
            "width": 12,
            "height": 9,
        }
    ]

    storage = TableStorage(
        rows,
        root=str(tmp_path),
        source_column="source",
        path_column="path",
        skip_indexing=True,
    )

    assert "outside.jpg" not in storage._items


def test_absolute_local_source_outside_root_reports_boundary(tmp_path: Path, capsys) -> None:
    outside = tmp_path.parent / "outside-reported.jpg"
    _make_image(outside)

    TableStorage(
        [
            {
                "source": str(outside),
                "path": "outside-reported.jpg",
                "size": int(outside.stat().st_size),
                "mtime": float(outside.stat().st_mtime),
                "width": 12,
                "height": 9,
            }
        ],
        root=str(tmp_path),
        source_column="source",
        path_column="path",
        skip_indexing=True,
    )

    captured = capsys.readouterr()
    assert "outside base_dir boundary" in captured.out
    assert str(tmp_path) in captured.out


def test_skip_local_realpath_validation_blocks_absolute_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-lexical.jpg"
    _make_image(outside)

    rows = [
        {
            "source": str(outside),
            "path": "outside-lexical.jpg",
            "size": int(outside.stat().st_size),
            "mtime": float(outside.stat().st_mtime),
            "width": 12,
            "height": 9,
        }
    ]

    storage = TableStorage(
        rows,
        root=str(tmp_path),
        source_column="source",
        path_column="path",
        skip_indexing=True,
        skip_local_realpath_validation=True,
    )

    assert "outside-lexical.jpg" not in storage._items
