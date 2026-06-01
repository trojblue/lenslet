"""Presence route registration and lifecycle helpers for Lenslet."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from ..auth import request_client_id
from ..context import AppContext, get_app_context, get_request_context
from ..models import (
    ErrorResponse,
    PresenceCountPayload,
    PresenceInvalidLeaseResponse,
    PresenceLeavePayload,
    PresenceLeaveResponse,
    PresenceMovePayload,
    PresenceMoveResponse,
    PresencePayload,
    PresenceScopeMismatchResponse,
    PresenceSessionResponse,
)
from ..permissions import deny_if_mutation_forbidden
from ..presence_runtime import PresenceRuntimePayload, presence_count_payload, presence_runtime_payload
from ..paths import canonical_path
from ..sync.events import EventBroker
from ..sync.presence import (
    PresenceCount,
    PresenceLeaseError,
    PresenceMetrics,
    PresenceScopeError,
    PresenceTracker,
)


def presence_payload_for_client(
    count: PresenceCount,
    client_id: str,
    lease_id: str,
) -> PresenceSessionResponse:
    payload = {
        **presence_count_payload(count),
        "client_id": client_id,
        "lease_id": lease_id,
    }
    return PresenceSessionResponse.model_validate(payload)


def presence_count_for_gallery(counts: list[PresenceCount], gallery_id: str) -> PresenceCount:
    for count in counts:
        if count.gallery_id == gallery_id:
            return count
    return PresenceCount(gallery_id=gallery_id, viewing=0, editing=0)


def publish_presence_counts(broker: EventBroker, counts: list[PresenceCount]) -> None:
    for count in counts:
        broker.publish("presence", presence_count_payload(count))


def presence_invalid_lease_payload(gallery_id: str, client_id: str) -> PresenceInvalidLeaseResponse:
    return PresenceInvalidLeaseResponse(
        error="invalid_lease",
        gallery_id=gallery_id,
        client_id=client_id,
    )


def presence_scope_mismatch_payload(
    exc: PresenceScopeError,
    requested_gallery_id: str,
    client_id: str,
) -> PresenceScopeMismatchResponse:
    return PresenceScopeMismatchResponse(
        error="scope_mismatch",
        requested_gallery_id=requested_gallery_id,
        actual_gallery_id=exc.actual_gallery_id,
        client_id=client_id,
    )


def _presence_mutation_context(request: Request) -> tuple[AppContext, JSONResponse | None]:
    context = get_request_context(request)
    denied = deny_if_mutation_forbidden(request, writes_enabled=context.workspace.can_write)
    return context, denied


def require_presence_client_id(request: Request) -> str:
    client_id = request_client_id(request)
    if client_id:
        return client_id
    raise HTTPException(500, "presence identity unavailable")


def _invalid_lease_response(
    metrics: PresenceMetrics,
    *,
    gallery_id: str,
    client_id: str,
) -> JSONResponse:
    metrics.record_invalid_lease()
    payload = presence_invalid_lease_payload(gallery_id=gallery_id, client_id=client_id)
    return JSONResponse(status_code=409, content=payload.model_dump())


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
    return JSONResponse(status_code=409, content=payload.model_dump())


def register_presence_routes(
    app: FastAPI,
) -> None:
    mutation_denial_response = {403: {"model": ErrorResponse}}
    invalid_lease_response = {
        **mutation_denial_response,
        409: {"model": PresenceInvalidLeaseResponse},
    }
    scoped_conflict_response = {
        **mutation_denial_response,
        409: {"model": PresenceInvalidLeaseResponse | PresenceScopeMismatchResponse},
    }

    def _presence_diag(request: Request) -> PresenceRuntimePayload:
        runtime = get_request_context(request).runtime
        return presence_runtime_payload(
            presence=runtime.presence,
            broker=runtime.broker,
            metrics=runtime.presence_metrics,
            prune_interval_seconds=runtime.presence_prune_interval,
        )

    @app.get("/presence/diagnostics")
    def presence_diagnostics(request: Request) -> PresenceRuntimePayload:
        return _presence_diag(request)

    @app.post(
        "/presence/join",
        response_model=PresenceSessionResponse,
        responses=invalid_lease_response,
    )
    def presence_join(body: PresencePayload, request: Request) -> PresenceSessionResponse | JSONResponse:
        context, denied = _presence_mutation_context(request)
        if denied:
            return denied
        runtime = context.runtime
        presence = runtime.presence
        broker = runtime.broker
        gallery_id = canonical_path(body.gallery_id)
        client_id = require_presence_client_id(request)
        try:
            lease_id, counts = presence.join(gallery_id, client_id, lease_id=body.lease_id)
        except PresenceLeaseError:
            return _invalid_lease_response(runtime.presence_metrics, gallery_id=gallery_id, client_id=client_id)
        publish_presence_counts(broker, counts)
        current = presence_count_for_gallery(counts, gallery_id)
        return presence_payload_for_client(current, client_id, lease_id)

    @app.post(
        "/presence/move",
        response_model=PresenceMoveResponse,
        responses=scoped_conflict_response,
    )
    def presence_move(body: PresenceMovePayload, request: Request) -> PresenceMoveResponse | JSONResponse:
        context, denied = _presence_mutation_context(request)
        if denied:
            return denied
        runtime = context.runtime
        presence = runtime.presence
        broker = runtime.broker
        from_gallery_id = canonical_path(body.from_gallery_id)
        to_gallery_id = canonical_path(body.to_gallery_id)
        client_id = require_presence_client_id(request)
        try:
            response_lease_id = body.lease_id
            counts = presence.move(
                from_gallery_id=from_gallery_id,
                to_gallery_id=to_gallery_id,
                client_id=client_id,
                lease_id=body.lease_id,
            )
        except PresenceLeaseError:
            return _invalid_lease_response(runtime.presence_metrics, gallery_id=from_gallery_id, client_id=client_id)
        except PresenceScopeError as exc:
            return _scope_mismatch_response(
                exc,
                requested_gallery_id=from_gallery_id,
                client_id=client_id,
            )
        publish_presence_counts(broker, counts)
        from_scope = presence_count_for_gallery(counts, from_gallery_id)
        to_scope = presence_count_for_gallery(counts, to_gallery_id)
        return PresenceMoveResponse(
            client_id=client_id,
            lease_id=response_lease_id,
            from_scope=PresenceCountPayload.model_validate(presence_count_payload(from_scope)),
            to_scope=PresenceCountPayload.model_validate(presence_count_payload(to_scope)),
        )

    @app.post(
        "/presence/leave",
        response_model=PresenceLeaveResponse,
        responses=scoped_conflict_response,
    )
    def presence_leave(body: PresenceLeavePayload, request: Request) -> PresenceLeaveResponse | JSONResponse:
        context, denied = _presence_mutation_context(request)
        if denied:
            return denied
        runtime = context.runtime
        presence = runtime.presence
        broker = runtime.broker
        gallery_id = canonical_path(body.gallery_id)
        client_id = require_presence_client_id(request)
        try:
            removed, counts = presence.leave(gallery_id=gallery_id, client_id=client_id, lease_id=body.lease_id)
        except PresenceLeaseError:
            return _invalid_lease_response(runtime.presence_metrics, gallery_id=gallery_id, client_id=client_id)
        except PresenceScopeError as exc:
            return _scope_mismatch_response(
                exc,
                requested_gallery_id=gallery_id,
                client_id=client_id,
            )
        publish_presence_counts(broker, counts)
        current = presence_count_for_gallery(counts, gallery_id)
        payload = presence_payload_for_client(current, client_id, body.lease_id).model_dump()
        payload["removed"] = removed
        return PresenceLeaveResponse.model_validate(payload)
