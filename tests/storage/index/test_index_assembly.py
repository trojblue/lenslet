from __future__ import annotations

from dataclasses import dataclass

from lenslet.storage.index_assembly import ScannedRow, assemble_indexes


@dataclass
class _Item:
    path: str
    width: int
    height: int


@dataclass
class _Index:
    path: str
    generated_at: str
    items: list[_Item]
    dirs: list[str]


def test_assemble_indexes_builds_folder_tree_and_row_maps() -> None:
    cat = _Item(path="cats/one.jpg", width=10, height=8)
    puppy = _Item(path="dogs/puppy/two.jpg", width=7, height=5)

    result = assemble_indexes(
        [
            ScannedRow(
                row_idx=0,
                logical_path=cat.path,
                source="/data/cats/one.jpg",
                folder_norm="cats",
                item=cat,
                discovered_dims=(10, 8),
            ),
            ScannedRow(
                row_idx=1,
                logical_path=puppy.path,
                source="/data/dogs/puppy/two.jpg",
                folder_norm="dogs/puppy",
                item=puppy,
            ),
        ],
        generated_at="2026-05-31T00:00:00+00:00",
        row_count=2,
        index_factory=_Index,
    )

    assert result.indexes[""].dirs == ["cats", "dogs"]
    assert result.indexes["dogs"].dirs == ["puppy"]
    assert result.indexes["cats"].items == [cat]
    assert result.items == {cat.path: cat, puppy.path: puppy}
    assert result.source_paths[puppy.path] == "/data/dogs/puppy/two.jpg"
    assert result.row_dimensions == [(10, 8), (7, 5)]
    assert result.path_to_row == {cat.path: 0, puppy.path: 1}
    assert result.row_to_path == {0: cat.path, 1: puppy.path}
    assert result.dimensions == {cat.path: (10, 8)}
