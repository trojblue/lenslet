from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import FastAPI

from .cache.thumbs import ThumbCache
from .lifecycle import register_lifecycle_handlers
from .sync.events import EventBroker, IdempotencyCache
from .sync.labels import LabelSyncLocks, SnapshotWriter, init_sync_state
from .sync.presence import PresenceMetrics, PresenceTracker
from .thumbs import ThumbnailScheduler
from ..storage.base import BrowseAppStorage
from ..storage.table.query_coordinator import TableQueryCoordinator
from ..workspace import Workspace

if TYPE_CHECKING:
    from .hotpath import HotpathTelemetry


@dataclass(frozen=True)
class AppRuntime:
    sidecar_lock: threading.Lock
    log_lock: threading.Lock
    broker: EventBroker
    idempotency_cache: IdempotencyCache
    snapshotter: SnapshotWriter
    sync_state: dict[str, int]
    presence: PresenceTracker
    presence_metrics: PresenceMetrics
    presence_prune_interval: float
    thumb_queue: ThumbnailScheduler
    thumb_cache: ThumbCache | None
    hotpath_metrics: HotpathTelemetry
    query_coordinator: TableQueryCoordinator


@dataclass(frozen=True, slots=True)
class AppRuntimeSettings:
    presence_view_ttl: float
    presence_edit_ttl: float
    presence_prune_interval: float
    thumb_cache_enabled: bool
    thumb_worker_count: int


@dataclass(frozen=True, slots=True)
class AppRuntimeHooks:
    build_thumb_cache: Callable[[Workspace, bool], ThumbCache | None]
    build_hotpath_metrics: Callable[[FastAPI], HotpathTelemetry]


@dataclass(frozen=True, slots=True)
class AppRuntimeAssembly:
    storage: BrowseAppStorage
    workspace: Workspace
    settings: AppRuntimeSettings
    hooks: AppRuntimeHooks


def build_app_runtime(
    app: FastAPI,
    assembly: AppRuntimeAssembly,
) -> AppRuntime:
    settings = assembly.settings
    hooks = assembly.hooks
    sidecar_lock = threading.Lock()
    log_lock = threading.Lock()
    locks = LabelSyncLocks(sidecar=sidecar_lock, log=log_lock)
    broker, idempotency_cache, snapshotter, max_event_id = init_sync_state(
        assembly.storage,
        assembly.workspace,
        locks,
    )
    sync_state = {"last_event_id": max_event_id}
    presence = PresenceTracker(
        view_ttl=settings.presence_view_ttl,
        edit_ttl=settings.presence_edit_ttl,
    )
    presence_metrics = PresenceMetrics()
    thumb_queue = ThumbnailScheduler(max_workers=settings.thumb_worker_count)
    register_lifecycle_handlers(app, startup=thumb_queue.start, shutdown=thumb_queue.close)
    thumb_cache = hooks.build_thumb_cache(assembly.workspace, settings.thumb_cache_enabled)
    hotpath_metrics = hooks.build_hotpath_metrics(app)
    query_coordinator = TableQueryCoordinator(
        on_analysis_event=hotpath_metrics.record_analysis,
    )
    register_lifecycle_handlers(
        app,
        startup=query_coordinator.start,
        shutdown=query_coordinator.close,
    )
    return AppRuntime(
        sidecar_lock=sidecar_lock,
        log_lock=log_lock,
        broker=broker,
        idempotency_cache=idempotency_cache,
        snapshotter=snapshotter,
        sync_state=sync_state,
        presence=presence,
        presence_metrics=presence_metrics,
        presence_prune_interval=settings.presence_prune_interval,
        thumb_queue=thumb_queue,
        thumb_cache=thumb_cache,
        hotpath_metrics=hotpath_metrics,
        query_coordinator=query_coordinator,
    )
