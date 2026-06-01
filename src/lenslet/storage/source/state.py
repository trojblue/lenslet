from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, Protocol, TypeVar

from ..image_media import ImageMime


class SourceBackedItem(Protocol):
    path: str
    name: str
    mime: ImageMime
    width: int
    height: int
    size: int
    mtime: float
    url: str | None
    source: str | None
    metrics: dict[str, float]


ItemT = TypeVar("ItemT", bound=SourceBackedItem)


@dataclass
class SourceBackedIndexState(Generic[ItemT]):
    items: dict[str, ItemT] = field(default_factory=dict)
    source_paths: dict[str, str] = field(default_factory=dict)
    dimensions: dict[str, tuple[int, int]] = field(default_factory=dict)


@dataclass
class SourceRowIndexState:
    row_dimensions: list[tuple[int, int] | None] = field(default_factory=list)
    path_to_row: dict[str, int] = field(default_factory=dict)
    row_to_path: dict[int, str] = field(default_factory=dict)
