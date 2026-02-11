"""Presence route registration and lifecycle helpers for Lenslet."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .server_models import PresenceLeavePayload, PresenceMovePayload, PresencePayload
from .server_runtime import PresenceMetrics
from .server_sync import (
    PresenceCount,
    PresenceLeaseError,
    PresenceScopeError,
    PresenceTracker,
    _canonical_path,
)


def presence_runtime_payload(
    *,
    presence: PresenceTracker,
    broker,
    metrics: PresenceMetrics,
    lifecycle_v2_enabled: bool,
    prune_interval_seconds: float,
) -> dict[str, Any]:
    presence_diag = presence.diagnostics()
    broker_diag = broker.diagnostics()
    metric_diag = metrics.snapshot()
    return {
        "lifecycle_v2_enabled": lifecycle_v2_enabled,
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


def presence_count_payload(count: PresenceCount) -> dict[str, int | str]:
    return {
        "gallery_id": count.gallery_id,
        "viewing": count.viewing,
        "editing": count.editing,
    }


def presence_payload_for_client(
    count: PresenceCount,
    client_id: str,
    lease_id: str,
) -> dict[str, int | str]:
    payload: dict[str, int | str] = presence_count_payload(count)
    payload["client_id"] = client_id
    payload["lease_id"] = lease_id
    return payload


def presence_count_for_gallery(counts: list[PresenceCount], gallery_id: str) -> PresenceCount:
    for count in counts:
        if count.gallery_id == gallery_id:
            return count
    return PresenceCount(gallery_id=gallery_id, viewing=0, editing=0)


def publish_presence_counts(broker, counts: list[PresenceCount]) -> None:
    for count in counts:
        broker.publish("presence", presence_count_payload(count))


def publish_presence_deltas(
    broker,
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


def install_presence_prune_loop(
    app: FastAPI,
    presence: PresenceTracker,
    broker,
    interval_seconds: float,
) -> None:
    interval = interval_seconds if interval_seconds > 0 else 5.0
    app.state.presence_tracker = presence
    app.state.presence_prune_interval = interval
    app.state.presence_prune_task = None

    async def _presence_prune_loop() -> None:
        previous = presence.snapshot_counts()
        while True:
            await asyncio.sleep(interval)
            current = presence.snapshot_counts()
            publish_presence_deltas(broker, previous, current)
            previous = current

    async def _start_presence_prune_loop() -> None:
        existing = getattr(app.state, "presence_prune_task", None)
        if existing is not None and not existing.done():
            return
        app.state.presence_prune_task = asyncio.create_task(_presence_prune_loop())

    async def _stop_presence_prune_loop() -> None:
        task = getattr(app.state, "presence_prune_task", None)
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        app.state.presence_prune_task = None

    app.add_event_handler("startup", _start_presence_prune_loop)
    app.add_event_handler("shutdown", _stop_presence_prune_loop)


def presence_invalid_lease_payload(gallery_id: str, client_id: str) -> dict[str, str]:
    return {
        "error": "invalid_lease",
        "gallery_id": gallery_id,
        "client_id": client_id,
    }


def presence_scope_mismatch_payload(
    exc: PresenceScopeError,
    requested_gallery_id: str,
    client_id: str,
) -> dict[str, str]:
    return {
        "error": "scope_mismatch",
        "requested_gallery_id": requested_gallery_id,
        "actual_gallery_id": exc.actual_gallery_id,
        "client_id": client_id,
    }


def touch_presence_edit(presence: PresenceTracker, broker, gallery_id: str, client_id: str) -> None:
    _, counts = presence.touch_edit(gallery_id, client_id)
    publish_presence_counts(broker, counts)


def require_presence_client_id(client_id: str) -> str:
    if not client_id:
        raise HTTPException(400, "client_id required")
    return client_id


def _invalid_lease_response(
    metrics: PresenceMetrics,
    *,
    gallery_id: str,
    client_id: str,
) -> JSONResponse:
    metrics.record_invalid_lease()
    payload = presence_invalid_lease_payload(gallery_id=gallery_id, client_id=client_id)
    return JSONResponse(status_code=409, content=payload)


def _scope_mismatch_response(
    exc: PresenceScopeError,
    *,
    requested_gallery_id: str,
    client_id: str,
) -> JSONResponse:
    payload = presence_scope_mismatch_payload(
        exc,
        requested_gallery_id=requested_gallery_id,
        client_id=client_id,
    )
    return JSONResponse(status_code=409, content=payload)


def register_presence_routes(
    app: FastAPI,
    presence: PresenceTracker,
    broker,
    *,
    lifecycle_v2_enabled: bool,
    metrics: PresenceMetrics,
) -> None:
    def _presence_diag() -> dict[str, Any]:
        prune_interval = float(getattr(app.state, "presence_prune_interval", 5.0))
        return presence_runtime_payload(
            presence=presence,
            broker=broker,
            metrics=metrics,
            lifecycle_v2_enabled=lifecycle_v2_enabled,
            prune_interval_seconds=prune_interval,
        )

    @app.get("/presence/diagnostics")
    def presence_diagnostics():
        return _presence_diag()

    @app.post("/presence/join")
    def presence_join(body: PresencePayload):
        gallery_id = _canonical_path(body.gallery_id)
        client_id = require_presence_client_id(body.client_id)
        try:
            if lifecycle_v2_enabled:
                lease_id, counts = presence.join(gallery_id, client_id, lease_id=body.lease_id)
            else:
                lease_id, counts = presence.touch_view(gallery_id, client_id, lease_id=body.lease_id)
        except PresenceLeaseError:
            return _invalid_lease_response(metrics, gallery_id=gallery_id, client_id=client_id)
        publish_presence_counts(broker, counts)
        current = presence_count_for_gallery(counts, gallery_id)
        return presence_payload_for_client(current, client_id, lease_id)

    @app.post("/presence/move")
    def presence_move(body: PresenceMovePayload):
        from_gallery_id = _canonical_path(body.from_gallery_id)
        to_gallery_id = _canonical_path(body.to_gallery_id)
        client_id = require_presence_client_id(body.client_id)
        try:
            if lifecycle_v2_enabled:
                response_lease_id = body.lease_id
                counts = presence.move(
                    from_gallery_id=from_gallery_id,
                    to_gallery_id=to_gallery_id,
                    client_id=client_id,
                    lease_id=body.lease_id,
                )
            else:
                response_lease_id, counts = presence.touch_view(
                    to_gallery_id,
                    client_id,
                    lease_id=body.lease_id,
                )
        except PresenceLeaseError:
            return _invalid_lease_response(metrics, gallery_id=from_gallery_id, client_id=client_id)
        except PresenceScopeError as exc:
            return _scope_mismatch_response(
                exc,
                requested_gallery_id=from_gallery_id,
                client_id=client_id,
            )
        publish_presence_counts(broker, counts)
        from_scope = presence_count_for_gallery(counts, from_gallery_id)
        to_scope = presence_count_for_gallery(counts, to_gallery_id)
        return {
            "client_id": client_id,
            "lease_id": response_lease_id,
            "from_scope": presence_count_payload(from_scope),
            "to_scope": presence_count_payload(to_scope),
        }

    @app.post("/presence/leave")
    def presence_leave(body: PresenceLeavePayload):
        gallery_id = _canonical_path(body.gallery_id)
        client_id = require_presence_client_id(body.client_id)
        if not lifecycle_v2_enabled:
            current = presence.snapshot_counts().get(gallery_id, PresenceCount(gallery_id=gallery_id, viewing=0, editing=0))
            payload = presence_payload_for_client(current, client_id, body.lease_id)
            payload["removed"] = False
            payload["mode"] = "legacy_heartbeat"
            return payload
        try:
            removed, counts = presence.leave(gallery_id=gallery_id, client_id=client_id, lease_id=body.lease_id)
        except PresenceLeaseError:
            return _invalid_lease_response(metrics, gallery_id=gallery_id, client_id=client_id)
        except PresenceScopeError as exc:
            return _scope_mismatch_response(
                exc,
                requested_gallery_id=gallery_id,
                client_id=client_id,
            )
        publish_presence_counts(broker, counts)
        current = presence_count_for_gallery(counts, gallery_id)
        payload = presence_payload_for_client(current, client_id, body.lease_id)
        payload["removed"] = removed
        return payload

    @app.post("/presence")
    def presence_heartbeat(body: PresencePayload):
        gallery_id = _canonical_path(body.gallery_id)
        client_id = require_presence_client_id(body.client_id)
        try:
            lease_id, counts = presence.touch_view(gallery_id, client_id, lease_id=body.lease_id)
        except PresenceLeaseError:
            return _invalid_lease_response(metrics, gallery_id=gallery_id, client_id=client_id)
        publish_presence_counts(broker, counts)
        current = presence_count_for_gallery(counts, gallery_id)
        return presence_payload_for_client(current, client_id, lease_id)
