"""Common API route registration for Lenslet."""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from ..browse import (
    ToItemFn,
    build_folder_index,
    build_image_metadata,
    build_sidecar,
    build_sidecar_from_meta,
    ensure_image,
    search_results,
    storage_from_request,
)
from ..comparison_export import export_comparison_response
from ..context import get_request_context
from ..media import file_response, thumb_response_async
from ..models import (
    BrowseFolderPathsPayload,
    BrowseFolderPayload,
    BrowseSearchResultsPayload,
    ImageMetadataResponse,
    Sidecar,
    SidecarPatch,
)
from ..permissions import deny_if_mutation_forbidden
from ..runtime import PresenceMetrics
from ..sync import (
    EventBroker,
    IdempotencyCache,
    PresenceTracker,
    apply_patch_to_meta,
    canonical_path,
    ensure_meta_fields,
    format_sse,
    last_event_id_from_request,
    now_iso,
    parse_if_match,
    updated_by_from_request,
)
from .presence import register_presence_routes
from ...storage.base import BrowseStorage

RecordUpdateFn = Callable[[str, dict, str], None]


def _error_response(status: int, error: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": error, "message": message})


def _update_item(
    storage: BrowseStorage,
    path: str,
    body: Sidecar,
    updated_by: str,
    *,
    ensure_meta_fields: Callable[[dict], dict],
    now_iso: Callable[[], str],
    sidecar_from_meta: Callable[[Any, str, dict], Sidecar],
    ) -> Sidecar:
    meta = storage.ensure_metadata(path)
    meta = ensure_meta_fields(meta)
    meta["tags"] = body.tags
    meta["notes"] = body.notes
    meta["star"] = body.star
    meta["version"] = meta.get("version", 1) + 1
    meta["updated_at"] = now_iso()
    meta["updated_by"] = updated_by
    storage.set_metadata(path, meta)
    return sidecar_from_meta(storage, path, meta)


def register_folder_route(
    app: FastAPI,
    to_item: ToItemFn,
) -> None:
    @app.get("/folders", response_model=BrowseFolderPayload)
    def get_folder(
        request: Request,
        path: str = "/",
        recursive: bool = False,
        count_only: bool = False,
    ):
        storage = storage_from_request(request)
        context = get_request_context(request)
        return build_folder_index(
            storage,
            canonical_path(path),
            to_item,
            recursive=recursive,
            count_only=count_only,
            browse_cache=context.recursive_browse_cache,
            hotpath_metrics=context.runtime.hotpath_metrics,
        )


def _folder_index_getter(storage: BrowseStorage) -> Callable[[str], Any]:
    return storage.get_recursive_index


def _collect_folder_paths(storage: BrowseStorage) -> list[str]:
    get_index = _folder_index_getter(storage)
    queue: deque[str] = deque(["/"])
    seen: set[str] = set()

    while queue:
        path = canonical_path(queue.popleft())
        if path in seen:
            continue
        seen.add(path)
        try:
            index = get_index(path)
        except FileNotFoundError:
            continue
        if index is None:
            continue
        for child_name in getattr(index, "dirs", []) or []:
            queue.append(canonical_path(storage.join(path, child_name)))

    return sorted(seen, key=lambda value: (value != "/", value))


def register_common_api_routes(
    app: FastAPI,
    to_item: ToItemFn,
    *,
    meta_lock: threading.Lock,
    presence: PresenceTracker,
    broker: EventBroker,
    presence_metrics: PresenceMetrics,
    idempotency_cache: IdempotencyCache,
    record_update: RecordUpdateFn,
) -> None:
    register_folder_route(app, to_item)

    def _resolve_image_request(path: str, request: Request):
        storage = storage_from_request(request)
        resolved_path = canonical_path(path)
        ensure_image(storage, resolved_path)
        return storage, resolved_path

    @app.get("/folders/paths", response_model=BrowseFolderPathsPayload)
    def get_folder_paths(request: Request):
        storage = storage_from_request(request)
        return BrowseFolderPathsPayload(paths=_collect_folder_paths(storage))

    @app.get("/item")
    def get_item(path: str, request: Request):
        storage, path = _resolve_image_request(path, request)
        return build_sidecar(storage, path)

    @app.get("/metadata", response_model=ImageMetadataResponse)
    def get_metadata(path: str, request: Request):
        storage, path = _resolve_image_request(path, request)
        return build_image_metadata(storage, path)

    @app.post("/export-comparison")
    async def export_comparison(request: Request):
        storage = storage_from_request(request)
        try:
            payload = await request.json()
        except Exception:
            return _error_response(400, "invalid_json", "request body must be valid JSON")
        return export_comparison_response(storage, payload)

    @app.put("/item")
    def put_item(path: str, body: Sidecar, request: Request):
        context = get_request_context(request)
        if denied := deny_if_mutation_forbidden(request, writes_enabled=context.workspace.can_write):
            return denied
        storage, path = _resolve_image_request(path, request)
        updated_by = updated_by_from_request(request)
        with meta_lock:
            sidecar = _update_item(
                storage,
                path,
                body,
                updated_by,
                ensure_meta_fields=ensure_meta_fields,
                now_iso=now_iso,
                sidecar_from_meta=build_sidecar_from_meta,
            )
            meta_snapshot = dict(storage.ensure_metadata(path))
        record_update(path, meta_snapshot)
        return sidecar

    @app.patch("/item")
    def patch_item(path: str, body: SidecarPatch, request: Request):
        context = get_request_context(request)
        if denied := deny_if_mutation_forbidden(request, writes_enabled=context.workspace.can_write):
            return denied
        storage, path = _resolve_image_request(path, request)
        idem_key = request.headers.get("Idempotency-Key")
        if not idem_key:
            raise HTTPException(400, "Idempotency-Key header required")
        cached = idempotency_cache.get(idem_key)
        if cached:
            status, payload = cached
            return JSONResponse(status_code=status, content=payload)

        if_match = parse_if_match(request.headers.get("If-Match"))
        if request.headers.get("If-Match") and if_match is None:
            payload = {"error": "invalid_if_match", "message": "If-Match must be an integer version"}
            idempotency_cache.set(idem_key, 400, payload)
            return JSONResponse(status_code=400, content=payload)

        expected = body.base_version
        if if_match is not None:
            if expected is not None and expected != if_match:
                payload = {"error": "version_mismatch", "message": "If-Match and base_version disagree"}
                idempotency_cache.set(idem_key, 400, payload)
                return JSONResponse(status_code=400, content=payload)
            expected = if_match

        if expected is None:
            payload = {"error": "missing_base_version", "message": "base_version or If-Match is required"}
            idempotency_cache.set(idem_key, 400, payload)
            return JSONResponse(status_code=400, content=payload)

        updated = False
        with meta_lock:
            meta = storage.ensure_metadata(path)
            meta = ensure_meta_fields(meta)
            if expected is not None and expected != meta.get("version", 1):
                current = build_sidecar_from_meta(storage, path, meta).model_dump()
                payload = {"error": "version_conflict", "current": current}
                idempotency_cache.set(idem_key, 409, payload)
                return JSONResponse(status_code=409, content=payload)

            updated = apply_patch_to_meta(meta, body)
            if updated:
                meta["version"] = meta.get("version", 1) + 1
                meta["updated_at"] = now_iso()
                meta["updated_by"] = updated_by_from_request(request)
                storage.set_metadata(path, meta)
            meta_snapshot = dict(meta)
        if updated:
            record_update(path, meta_snapshot)
        sidecar = build_sidecar_from_meta(storage, path, meta_snapshot).model_dump()
        idempotency_cache.set(idem_key, 200, sidecar)
        return JSONResponse(status_code=200, content=sidecar)

    register_presence_routes(
        app,
        presence,
        broker,
        metrics=presence_metrics,
    )

    @app.get("/events")
    async def events(request: Request):
        broker.ensure_loop()
        queue = broker.register()
        last_event_id = last_event_id_from_request(request)

        async def event_stream():
            try:
                for record in broker.replay(last_event_id):
                    yield format_sse(record)
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        record = await asyncio.wait_for(queue.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
                        continue
                    yield format_sse(record)
            finally:
                broker.unregister(queue)

        response = StreamingResponse(event_stream(), media_type="text/event-stream")
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Connection"] = "keep-alive"
        return response

    @app.get("/thumb")
    async def get_thumb(path: str, request: Request):
        storage, path = _resolve_image_request(path, request)
        runtime = get_request_context(request).runtime
        return await thumb_response_async(
            storage,
            path,
            request,
            runtime.thumb_queue,
            runtime.thumb_cache,
            hotpath_metrics=runtime.hotpath_metrics,
        )

    @app.get("/file")
    def get_file(path: str, request: Request):
        storage, path = _resolve_image_request(path, request)
        runtime = get_request_context(request).runtime
        return file_response(storage, path, request=request, hotpath_metrics=runtime.hotpath_metrics)

    @app.get("/search", response_model=BrowseSearchResultsPayload)
    def search(request: Request, q: str = "", path: str = "/", limit: int = 100):
        storage = storage_from_request(request)
        return search_results(storage, to_item, q, canonical_path(path), limit)
