from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable

from fastapi import FastAPI
from typing_extensions import TypedDict

from .lifecycle import register_lifecycle_handlers
from .runtime import AppRuntime
from .sync.events import EventBroker, PresenceEventData
from .sync.presence import PresenceCount, PresenceMetrics, PresenceTracker

_PRESENCE_PRUNE_INTERVAL_ATTR = "lenslet_presence_prune_interval"
_PRESENCE_PRUNE_TASK_ATTR = "lenslet_presence_prune_task"


class PresenceRuntimePayload(TypedDict):
    view_ttl_seconds: float
    edit_ttl_seconds: float
    prune_interval_seconds: float
    active_clients: int
    active_scopes: int
    stale_pruned_total: int
    invalid_lease_total: int
    replay_miss_total: int
    replay_buffer_size: int
    replay_buffer_capacity: int
    replay_oldest_event_id: int | None
    replay_newest_event_id: int | None
    connected_sse_clients: int


def presence_runtime_payload(
    *,
    presence: PresenceTracker,
    broker: EventBroker,
    metrics: PresenceMetrics,
    prune_interval_seconds: float,
) -> PresenceRuntimePayload:
    presence_diag = presence.diagnostics()
    broker_diag = broker.diagnostics()
    metric_diag = metrics.snapshot()
    return {
        "view_ttl_seconds": presence.view_ttl_seconds,
        "edit_ttl_seconds": presence.edit_ttl_seconds,
        "prune_interval_seconds": prune_interval_seconds,
        "active_clients": presence_diag["active_clients"],
        "active_scopes": presence_diag["active_scopes"],
        "stale_pruned_total": presence_diag["stale_pruned_total"],
        "invalid_lease_total": metric_diag["invalid_lease_total"],
        "replay_miss_total": broker_diag["replay_miss_total"],
        "replay_buffer_size": broker_diag["buffer_size"],
        "replay_buffer_capacity": broker_diag["buffer_capacity"],
        "replay_oldest_event_id": broker_diag["oldest_event_id"],
        "replay_newest_event_id": broker_diag["newest_event_id"],
        "connected_sse_clients": broker_diag["connected_sse_clients"],
    }


def presence_count_payload(count: PresenceCount) -> PresenceEventData:
    return {
        "gallery_id": count.gallery_id,
        "viewing": count.viewing,
        "editing": count.editing,
    }


def publish_presence_deltas(
    broker: EventBroker,
    previous: dict[str, PresenceCount],
    current: dict[str, PresenceCount],
) -> None:
    if previous == current:
        return
    gallery_ids = sorted(set(previous) | set(current))
    for gallery_id in gallery_ids:
        before = previous.get(gallery_id)
        after = current.get(gallery_id)
        before_tuple = (before.viewing, before.editing) if before else (0, 0)
        after_tuple = (after.viewing, after.editing) if after else (0, 0)
        if before_tuple == after_tuple:
            continue
        broker.publish(
            "presence",
            {"gallery_id": gallery_id, "viewing": after_tuple[0], "editing": after_tuple[1]},
        )


def run_presence_prune_cycle(
    presence: PresenceTracker,
    broker: EventBroker,
    previous: dict[str, PresenceCount],
) -> dict[str, PresenceCount]:
    current = presence.snapshot_counts()
    publish_presence_deltas(broker, previous, current)
    return current


def _presence_runtime_key(runtime) -> tuple[int, int]:
    return (id(runtime.presence), id(runtime.broker))


async def _run_presence_prune_loop(
    interval: float,
    get_runtime: Callable[[], AppRuntime],
) -> None:
    previous: dict[str, PresenceCount] = {}
    previous_runtime_key: tuple[int, int] | None = None

    while True:
        await asyncio.sleep(interval)
        runtime = get_runtime()
        runtime_key = _presence_runtime_key(runtime)
        if runtime_key != previous_runtime_key:
            previous = runtime.presence.snapshot_counts()
            previous_runtime_key = runtime_key
            continue
        previous = run_presence_prune_cycle(runtime.presence, runtime.broker, previous)


def install_presence_prune_loop(
    app: FastAPI,
    interval_seconds: float,
    get_runtime: Callable[[], AppRuntime],
) -> None:
    interval = interval_seconds if interval_seconds > 0 else 5.0
    setattr(app.state, _PRESENCE_PRUNE_INTERVAL_ATTR, interval)
    setattr(app.state, _PRESENCE_PRUNE_TASK_ATTR, None)

    def _start_presence_prune_loop() -> None:
        task: asyncio.Task[None] | None = getattr(app.state, _PRESENCE_PRUNE_TASK_ATTR, None)
        if task is not None and not task.done():
            return
        interval = getattr(app.state, _PRESENCE_PRUNE_INTERVAL_ATTR)
        task = asyncio.create_task(_run_presence_prune_loop(interval, get_runtime))
        setattr(app.state, _PRESENCE_PRUNE_TASK_ATTR, task)

    async def _stop_presence_prune_loop() -> None:
        task: asyncio.Task[None] | None = getattr(app.state, _PRESENCE_PRUNE_TASK_ATTR, None)
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        setattr(app.state, _PRESENCE_PRUNE_TASK_ATTR, None)

    register_lifecycle_handlers(
        app,
        startup=_start_presence_prune_loop,
        shutdown=_stop_presence_prune_loop,
    )
