from __future__ import annotations

from collections.abc import Callable

from ..storage.base import SidecarState
from .sync.events import SyncEventName

RecordUpdateFn = Callable[[str, SidecarState, SyncEventName, Callable[[], None]], int]
