from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ..storage.base import SidecarState
from .sync.events import IdempotencyPayload, SyncEventName
from .sync.persistence import AcceptedEventIdentity, LabelPersistenceStatus


@dataclass(frozen=True, slots=True)
class RecordUpdateResult:
    event_id: int
    accepted_event: AcceptedEventIdentity
    persistence: LabelPersistenceStatus
    mutation_payload: IdempotencyPayload


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
        mutation_sidecar_payload: IdempotencyPayload | None = None,
    ) -> RecordUpdateResult: ...
