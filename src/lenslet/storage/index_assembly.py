from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(slots=True)
class ScannedRow:
    row_idx: int
    logical_path: str
    source: str
    folder_norm: str
    item: Any
    discovered_dims: tuple[int, int] | None = None


@dataclass(slots=True)
class IndexAssemblyResult:
    indexes: dict[str, Any]
    items: dict[str, Any]
    source_paths: dict[str, str]
    row_dimensions: list[tuple[int, int] | None]
    path_to_row: dict[str, int]
    row_to_path: dict[int, str] | list[str | None]
    dimensions: dict[str, tuple[int, int]]
    remote_tasks: list[tuple[str, Any, str, str]] = field(default_factory=list)
    skipped_local_disabled: int = 0
    skipped_local_outside_root: int = 0
    skipped_local_resolved_outside_root: int = 0
    skipped_local_missing: int = 0


def assemble_indexes(
    rows: list[ScannedRow],
    *,
    generated_at: str,
    row_count: int,
    index_factory: Callable[..., Any],
) -> IndexAssemblyResult:
    indexes: dict[str, Any] = {}
    items: dict[str, Any] = {}
    source_paths: dict[str, str] = {}
    row_dimensions: list[tuple[int, int] | None] = [None] * row_count
    path_to_row: dict[str, int] = {}
    row_to_path: dict[int, str] = {}
    dimensions: dict[str, tuple[int, int]] = {}
    dir_children: dict[str, set[str]] = {}
    seen_folders: set[str] = set()

    for row in rows:
        items[row.logical_path] = row.item
        source_paths[row.logical_path] = row.source
        row_dimensions[row.row_idx] = (row.item.width, row.item.height)
        path_to_row[row.logical_path] = row.row_idx
        row_to_path[row.row_idx] = row.logical_path

        if row.discovered_dims:
            dimensions[row.logical_path] = row.discovered_dims

        index = indexes.get(row.folder_norm)
        if index is None:
            index = index_factory(
                path="/" + row.folder_norm if row.folder_norm else "/",
                generated_at=generated_at,
                items=[],
                dirs=[],
            )
            indexes[row.folder_norm] = index
        index.items.append(row.item)

        if row.folder_norm not in seen_folders:
            seen_folders.add(row.folder_norm)
            parts = row.folder_norm.split("/") if row.folder_norm else []
            for depth in range(len(parts)):
                parent = "/".join(parts[:depth])
                child = parts[depth]
                dir_children.setdefault(parent, set()).add(child)

    if "" not in indexes:
        indexes[""] = index_factory(path="/", generated_at=generated_at, items=[], dirs=[])

    for parent, children in dir_children.items():
        index = indexes.get(parent)
        if index is None:
            index = index_factory(
                path="/" + parent if parent else "/",
                generated_at=generated_at,
                items=[],
                dirs=[],
            )
            indexes[parent] = index
        index.dirs = sorted(children)
    return IndexAssemblyResult(
        indexes=indexes,
        items=items,
        source_paths=source_paths,
        row_dimensions=row_dimensions,
        path_to_row=path_to_row,
        row_to_path=row_to_path,
        dimensions=dimensions,
    )
