from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic

from ..search_text import normalize_search_path, path_in_scope
from .state import ItemT, SourceBackedIndexState


@dataclass(slots=True)
class SourceCatalog(Generic[ItemT]):
    state: SourceBackedIndexState[ItemT]
    normalize_item_path: Callable[[str], str]

    def bind(self, state: SourceBackedIndexState[ItemT]) -> None:
        self.state = state

    def lookup_item(self, norm: str) -> ItemT | None:
        return self.state.items.get(norm)

    def path_candidates(self, path: str) -> tuple[str, ...]:
        normalized = self.normalize_item_path(path)
        rooted = f"/{normalized.lstrip('/')}" if normalized else "/"
        candidates: list[str] = []
        for candidate in (path, normalized, path.lstrip("/"), rooted):
            if candidate and candidate not in candidates:
                candidates.append(candidate)
        return tuple(candidates)

    def lookup_source_path(self, path: str) -> str | None:
        for candidate in self.path_candidates(path):
            source = self.state.source_paths.get(candidate)
            if source is not None:
                return source
        return None

    def source_for_path(self, logical_path: str) -> str:
        source = self.lookup_source_path(logical_path)
        if source is None:
            raise FileNotFoundError(logical_path)
        return source

    def total_items(self) -> int:
        return len(self.state.items)

    def items_in_scope(self, path: str) -> list[ItemT]:
        scope_norm = normalize_search_path(path)
        return [
            item
            for item in self.state.items.values()
            if path_in_scope(logical_path=item.path, scope_norm=scope_norm)
        ]

    def count_in_scope(self, path: str) -> int:
        scope_norm = normalize_search_path(path)
        return sum(
            1
            for item in self.state.items.values()
            if path_in_scope(logical_path=item.path, scope_norm=scope_norm)
        )
