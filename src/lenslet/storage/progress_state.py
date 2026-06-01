from __future__ import annotations

from typing import Any


class StorageProgressMixin:
    _progress_bar: Any
    _browse_signature: str

    def _progress(self, done: int, total: int, label: str) -> None:
        self._progress_bar.update(done, total, label)

    def indexing_progress(self) -> dict[str, int | str | bool | None]:
        return self._progress_bar.snapshot()

    def browse_cache_signature(self) -> str:
        return self._browse_signature
