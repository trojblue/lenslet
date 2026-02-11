from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import FastAPI

from .server_sync import PresenceTracker, _init_sync_state
from .thumbs import ThumbnailScheduler
from .workspace import Workspace


class PresenceMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._invalid_lease_total = 0

    def record_invalid_lease(self) -> None:
        with self._lock:
            self._invalid_lease_total += 1

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {"invalid_lease_total": self._invalid_lease_total}


@dataclass(frozen=True)
class AppRuntime:
    meta_lock: threading.Lock
    log_lock: threading.Lock
    broker: Any
    idempotency_cache: Any
    snapshotter: Any
    sync_state: dict[str, int]
    presence: PresenceTracker
    presence_metrics: PresenceMetrics
    thumb_queue: ThumbnailScheduler
    thumb_cache: Any
    hotpath_metrics: Any


def build_app_runtime(
    app: FastAPI,
    *,
    storage,
    workspace: Workspace,
    presence_view_ttl: float,
    presence_edit_ttl: float,
    presence_prune_interval: float,
    presence_lifecycle_v2: bool,
    thumb_cache_enabled: bool,
    thumb_worker_count: int,
    build_thumb_cache: Callable[[Workspace, bool], Any],
    install_presence_prune_loop: Callable[[FastAPI, PresenceTracker, Any, float], None],
    build_hotpath_metrics: Callable[[FastAPI], Any],
) -> AppRuntime:
    meta_lock = threading.Lock()
    log_lock = threading.Lock()
    broker, idempotency_cache, snapshotter, max_event_id = _init_sync_state(
        storage,
        workspace,
        meta_lock,
        log_lock,
    )
    sync_state = {"last_event_id": max_event_id}
    presence = PresenceTracker(view_ttl=presence_view_ttl, edit_ttl=presence_edit_ttl)
    presence_metrics = PresenceMetrics()
    app.state.sync_broker = broker
    app.state.presence_lifecycle_v2_enabled = presence_lifecycle_v2
    install_presence_prune_loop(app, presence, broker, presence_prune_interval)
    thumb_queue = ThumbnailScheduler(max_workers=thumb_worker_count)
    thumb_cache = build_thumb_cache(workspace, thumb_cache_enabled)
    hotpath_metrics = build_hotpath_metrics(app)
    return AppRuntime(
        meta_lock=meta_lock,
        log_lock=log_lock,
        broker=broker,
        idempotency_cache=idempotency_cache,
        snapshotter=snapshotter,
        sync_state=sync_state,
        presence=presence,
        presence_metrics=presence_metrics,
        thumb_queue=thumb_queue,
        thumb_cache=thumb_cache,
        hotpath_metrics=hotpath_metrics,
    )
