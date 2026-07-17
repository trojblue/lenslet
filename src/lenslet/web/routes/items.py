from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from ..browse import (
    build_image_metadata,
    build_sidecar,
    build_sidecar_from_state,
    ensure_image,
    storage_from_request,
)
from ..context import get_request_context
from ..models import ErrorResponse, ImageMetadataResponse, Sidecar, SidecarConflictResponse, SidecarPatch
from ..permissions import deny_if_mutation_forbidden
from ..record_update import RecordUpdateFn
from ..paths import canonical_path
from ..request_headers import parse_if_match
from ..sidecars import (
    apply_patch_to_sidecar,
    updated_by_from_request,
)
from ..sync.events import IdempotencyCache, IdempotencyPayload
from ..time import now_iso
from ..sync.labels import LabelPersistenceError
from ...storage.base import ItemRouteStorage, SidecarState
from ...storage.sidecar_state import copy_sidecar_state, ensure_sidecar_fields
from ...diagnostics import mark_request_handler_started, request_phase

PatchError = tuple[int, IdempotencyPayload]


@dataclass(frozen=True, slots=True)
class PatchApplicationResult:
    status: int
    payload: IdempotencyPayload
    event_id: int | None = None


def _error_response(status: int, error: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": error, "message": message})


def _label_persistence_error_response() -> JSONResponse:
    return _error_response(500, "label_persistence_failed", "failed to persist label update")


def _resolve_image_request(path: str, request: Request) -> tuple[ItemRouteStorage, str]:
    storage = storage_from_request(request)
    resolved_path = canonical_path(path)
    ensure_image(storage, resolved_path)
    return storage, resolved_path


def _put_item_sidecar_state(
    base_sidecar_state: SidecarState,
    body: Sidecar,
    updated_by: str,
    *,
    ensure_sidecar_fields: Callable[[SidecarState], SidecarState],
    now_iso: Callable[[], str],
) -> SidecarState:
    sidecar_state = ensure_sidecar_fields(copy_sidecar_state(base_sidecar_state))
    sidecar_state["tags"] = list(body.tags)
    sidecar_state["notes"] = body.notes
    sidecar_state["star"] = body.star
    sidecar_state["version"] = sidecar_state.get("version", 1) + 1
    sidecar_state["updated_at"] = now_iso()
    sidecar_state["updated_by"] = updated_by
    return sidecar_state


def _resolve_patch_expected_version(
    body: SidecarPatch,
    if_match_header: str | None,
) -> tuple[int | None, PatchError | None]:
    if_match = parse_if_match(if_match_header)
    if if_match_header and if_match is None:
        return None, (400, {"error": "invalid_if_match", "message": "If-Match must be an integer version"})

    expected = body.base_version
    if if_match is not None:
        if expected is not None and expected != if_match:
            return None, (400, {"error": "version_mismatch", "message": "If-Match and base_version disagree"})
        expected = if_match

    if expected is None:
        return None, (400, {"error": "missing_base_version", "message": "base_version or If-Match is required"})
    return expected, None


def _apply_sidecar_patch(
    storage: ItemRouteStorage,
    path: str,
    body: SidecarPatch,
    expected_version: int,
    updated_by: str,
    record_update: RecordUpdateFn,
) -> PatchApplicationResult:
    current_sidecar_state = ensure_sidecar_fields(copy_sidecar_state(storage.get_sidecar_readonly(path)))
    if expected_version != current_sidecar_state.get("version", 1):
        current = build_sidecar_from_state(storage, path, current_sidecar_state).model_dump()
        return PatchApplicationResult(409, {"error": "version_conflict", "current": current})

    next_sidecar_state = copy_sidecar_state(current_sidecar_state)
    updated = apply_patch_to_sidecar(next_sidecar_state, body)
    if not updated:
        payload = build_sidecar_from_state(storage, path, current_sidecar_state).model_dump()
        return PatchApplicationResult(200, payload)

    next_sidecar_state["version"] = next_sidecar_state.get("version", 1) + 1
    next_sidecar_state["updated_at"] = now_iso()
    next_sidecar_state["updated_by"] = updated_by
    sidecar_snapshot = copy_sidecar_state(next_sidecar_state)
    event_id = record_update(
        path,
        sidecar_snapshot,
        "item-updated",
        lambda: storage.set_sidecar(path, copy_sidecar_state(sidecar_snapshot)),
    )
    payload = build_sidecar_from_state(storage, path, sidecar_snapshot).model_dump()
    return PatchApplicationResult(200, payload, event_id)


def _cached_json_response(
    idempotency_cache: IdempotencyCache,
    key: str,
    status: int,
    payload: IdempotencyPayload,
) -> JSONResponse:
    idempotency_cache.set(key, status, payload)
    return JSONResponse(status_code=status, content=payload)


def register_item_routes(
    app: FastAPI,
    *,
    record_update: RecordUpdateFn,
) -> None:
    mutation_error_responses = {
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    }

    @app.get("/item")
    def get_item(path: str, request: Request) -> Sidecar:
        storage, path = _resolve_image_request(path, request)
        return build_sidecar(storage, path)

    @app.get("/metadata", response_model=ImageMetadataResponse)
    def get_metadata(path: str, request: Request) -> ImageMetadataResponse:
        storage, path = _resolve_image_request(path, request)
        return build_image_metadata(storage, path)

    @app.put("/item", response_model=Sidecar, responses=mutation_error_responses)
    def put_item(path: str, body: Sidecar, request: Request) -> Sidecar | JSONResponse:
        mark_request_handler_started()
        context = get_request_context(request)
        if denied := deny_if_mutation_forbidden(request, writes_enabled=context.workspace.can_write):
            return denied
        storage, path = _resolve_image_request(path, request)
        runtime = context.runtime
        updated_by = updated_by_from_request(request)
        with request_phase("mutation"):
            event_id: int | None = None
            with runtime.sidecar_lock:
                sidecar_snapshot = _put_item_sidecar_state(
                    storage.get_sidecar_readonly(path),
                    body,
                    updated_by,
                    ensure_sidecar_fields=ensure_sidecar_fields,
                    now_iso=now_iso,
                )
                try:
                    event_id = record_update(
                        path,
                        sidecar_snapshot,
                        "item-updated",
                        lambda: storage.set_sidecar(path, copy_sidecar_state(sidecar_snapshot)),
                    )
                except LabelPersistenceError:
                    return _label_persistence_error_response()
                sidecar = build_sidecar_from_state(storage, path, sidecar_snapshot)
            if event_id is not None and context.workspace.can_write:
                with request_phase("writer"):
                    runtime.snapshotter.maybe_write(storage, event_id)
            return sidecar

    @app.patch(
        "/item",
        response_model=Sidecar,
        responses={**mutation_error_responses, 409: {"model": SidecarConflictResponse}},
    )
    def patch_item(path: str, body: SidecarPatch, request: Request) -> JSONResponse:
        mark_request_handler_started()
        context = get_request_context(request)
        if denied := deny_if_mutation_forbidden(request, writes_enabled=context.workspace.can_write):
            return denied
        storage, path = _resolve_image_request(path, request)
        runtime = context.runtime
        idempotency_cache = runtime.idempotency_cache
        idem_key = request.headers.get("Idempotency-Key")
        if not idem_key:
            return _error_response(400, "missing_idempotency_key", "Idempotency-Key header required")
        cached = idempotency_cache.get(idem_key)
        if cached:
            status, payload = cached
            return JSONResponse(status_code=status, content=payload)

        expected, error = _resolve_patch_expected_version(body, request.headers.get("If-Match"))
        if error is not None:
            status, payload = error
            return _cached_json_response(idempotency_cache, idem_key, status, payload)
        if expected is None:
            return _cached_json_response(
                idempotency_cache,
                idem_key,
                400,
                {"error": "missing_base_version", "message": "base_version or If-Match is required"},
            )

        with request_phase("mutation"):
            try:
                with runtime.sidecar_lock:
                    result = _apply_sidecar_patch(
                        storage,
                        path,
                        body,
                        expected,
                        updated_by_from_request(request),
                        record_update,
                    )
            except LabelPersistenceError:
                return _label_persistence_error_response()
            if result.event_id is not None and context.workspace.can_write:
                with request_phase("writer"):
                    runtime.snapshotter.maybe_write(storage, result.event_id)
            return _cached_json_response(idempotency_cache, idem_key, result.status, result.payload)
