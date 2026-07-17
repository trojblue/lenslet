from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ..storage.base import SidecarState
from .sync.events import SyncEventName


class RecordUpdateFn(Protocol):
    def __call__(
        self,
        path: str,
        sidecar_state: SidecarState,
        event_type: SyncEventName,
        commit: Callable[[], None],
        *,
        mutation_id: str | None = None,
        changed_fields: tuple[str, ...] = (),
    ) -> int: ...
