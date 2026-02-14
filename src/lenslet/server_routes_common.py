"""Common API route registration for Lenslet."""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from PIL import Image
from pydantic import ValidationError

from .server_models import (
    EXPORT_COMPARISON_REQUEST_ADAPTER,
    FolderIndex,
    ImageMetadataResponse,
    SearchResult,
    Sidecar,
    SidecarPatch,
)
from .server_sync import PresenceTracker


RecordUpdateFn = Callable[[str, dict, str], None]


def _update_item(
    storage,
    path: str,
    body: Sidecar,
    updated_by: str,
    *,
    ensure_meta_fields: Callable[[dict], dict],
    now_iso: Callable[[], str],
    sidecar_from_meta: Callable[[dict], Sidecar],
) -> Sidecar:
    meta = storage.get_metadata(path)
    meta = ensure_meta_fields(meta)
    meta["tags"] = body.tags
    meta["notes"] = body.notes
    meta["star"] = body.star
    meta["version"] = meta.get("version", 1) + 1
    meta["updated_at"] = now_iso()
    meta["updated_by"] = updated_by
    storage.set_metadata(path, meta)
    return sidecar_from_meta(meta)


def register_folder_route(
    app: FastAPI,
    to_item,
    *,
    hotpath_metrics: Any | None = None,
) -> None:
    from . import server as _server

    @app.get("/folders", response_model=FolderIndex)
    def get_folder(
        request: Request,
        path: str = "/",
        recursive: bool = False,
    ):
        unsupported = [
            name
            for name in ("page", "page_size", "legacy_recursive")
            if name in request.query_params
        ]
        if unsupported:
            unsupported_list = ", ".join(unsupported)
            supported_list = ", ".join(("path", "recursive"))
            return _server._error_response(
                400,
                "unsupported_query_params",
                f"unsupported query parameters: {unsupported_list}; "
                f"supported parameters: {supported_list}",
            )
        storage = _server._storage_from_request(request)
        browse_cache = getattr(app.state, "recursive_browse_cache", None)
        return _server._build_folder_index(
            storage,
            _server._canonical_path(path),
            to_item,
            recursive=recursive,
            browse_cache=browse_cache,
            hotpath_metrics=hotpath_metrics,
        )


def register_common_api_routes(
    app: FastAPI,
    to_item,
    *,
    meta_lock: threading.Lock,
    presence: PresenceTracker,
    broker,
    presence_metrics,
    idempotency_cache,
    record_update: RecordUpdateFn,
    thumb_queue,
    thumb_cache,
    hotpath_metrics,
) -> None:
    from . import server as _server

    register_folder_route(app, to_item, hotpath_metrics=hotpath_metrics)

    def _resolve_image_request(path: str, request: Request):
        storage = _server._storage_from_request(request)
        canonical_path = _server._canonical_path(path)
        _server._ensure_image(storage, canonical_path)
        return storage, canonical_path

    @app.get("/item")
    def get_item(path: str, request: Request):
        storage, path = _resolve_image_request(path, request)
        return _server._build_sidecar(storage, path)

    @app.get("/metadata", response_model=ImageMetadataResponse)
    def get_metadata(path: str, request: Request):
        storage, path = _resolve_image_request(path, request)
        return _server._build_image_metadata(storage, path)

    @app.post("/export-comparison")
    async def export_comparison(request: Request):
        storage = _server._storage_from_request(request)
        try:
            payload = await request.json()
        except Exception:
            return _server._error_response(400, "invalid_json", "request body must be valid JSON")

        try:
            body = EXPORT_COMPARISON_REQUEST_ADAPTER.validate_python(payload)
        except ValidationError as exc:
            return _server._error_response(400, "invalid_request", _server._first_validation_error_detail(exc))

        canonical_paths = [_server._canonical_path(path) for path in body.paths]
        for path in canonical_paths:
            try:
                _server._ensure_image(storage, path)
            except HTTPException as exc:
                return _server._path_validation_error_response(exc)

        try:
            normalized_labels = _server._normalize_export_labels(
                body.labels,
                max_labels=len(canonical_paths),
            )
        except ValueError as exc:
            return _server._error_response(400, "invalid_labels", str(exc))

        ordered_paths, ordered_labels = _server._resolve_export_paths_and_labels(
            canonical_paths,
            normalized_labels,
            body.reverse_order,
        )

        images: list[Image.Image] = []
        source_formats: list[str] = []
        try:
            for path in ordered_paths:
                image, source_format = _server._load_export_image(storage, path)
                images.append(image)
                source_formats.append(source_format)
            exported_png = _server._build_export_png(
                images,
                ordered_labels,
                embed_metadata=body.embed_metadata,
                ordered_paths=ordered_paths,
                source_formats=source_formats,
                reversed_order=body.reverse_order,
            )
        except HTTPException as exc:
            return _server._comparison_export_error_response(exc)
        finally:
            for image in images:
                image.close()

        filename = _server._comparison_export_filename(body.reverse_order)
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return Response(content=exported_png, media_type="image/png", headers=headers)

    @app.put("/item")
    def put_item(path: str, body: Sidecar, request: Request):
        storage, path = _resolve_image_request(path, request)
        updated_by = _server._updated_by_from_request(request)
        with meta_lock:
            sidecar = _update_item(
                storage,
                path,
                body,
                updated_by,
                ensure_meta_fields=_server._ensure_meta_fields,
                now_iso=_server._now_iso,
                sidecar_from_meta=_server._sidecar_from_meta,
            )
            meta_snapshot = dict(storage.get_metadata(path))
        record_update(path, meta_snapshot)
        client_id = _server._client_id_from_request(request)
        if client_id:
            gallery_id = _server._gallery_id_from_path(path)
            _server._touch_presence_edit(presence, broker, gallery_id, client_id)
        return sidecar

    @app.patch("/item")
    def patch_item(path: str, body: SidecarPatch, request: Request):
        storage, path = _resolve_image_request(path, request)
        idem_key = request.headers.get("Idempotency-Key")
        if not idem_key:
            raise HTTPException(400, "Idempotency-Key header required")
        cached = idempotency_cache.get(idem_key)
        if cached:
            status, payload = cached
            return JSONResponse(status_code=status, content=payload)

        if_match = _server._parse_if_match(request.headers.get("If-Match"))
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
            meta = storage.get_metadata(path)
            meta = _server._ensure_meta_fields(meta)
            if expected is not None and expected != meta.get("version", 1):
                current = _server._sidecar_from_meta(meta).model_dump()
                payload = {"error": "version_conflict", "current": current}
                idempotency_cache.set(idem_key, 409, payload)
                return JSONResponse(status_code=409, content=payload)

            updated = _server._apply_patch_to_meta(meta, body)
            if updated:
                meta["version"] = meta.get("version", 1) + 1
                meta["updated_at"] = _server._now_iso()
                meta["updated_by"] = _server._updated_by_from_request(request)
                storage.set_metadata(path, meta)
            meta_snapshot = dict(meta)
        if updated:
            record_update(path, meta_snapshot)
            client_id = _server._client_id_from_request(request)
            if client_id:
                gallery_id = _server._gallery_id_from_path(path)
                _server._touch_presence_edit(presence, broker, gallery_id, client_id)
        sidecar = _server._sidecar_from_meta(meta_snapshot).model_dump()
        idempotency_cache.set(idem_key, 200, sidecar)
        return JSONResponse(status_code=200, content=sidecar)

    _server._register_presence_routes(
        app,
        presence,
        broker,
        metrics=presence_metrics,
    )

    @app.get("/events")
    async def events(request: Request):
        broker.ensure_loop()
        queue = broker.register()
        last_event_id = _server._last_event_id_from_request(request)

        async def event_stream():
            try:
                for record in broker.replay(last_event_id):
                    yield _server._format_sse(record)
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        record = await asyncio.wait_for(queue.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
                        continue
                    yield _server._format_sse(record)
            finally:
                broker.unregister(queue)

        response = StreamingResponse(event_stream(), media_type="text/event-stream")
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Connection"] = "keep-alive"
        return response

    @app.get("/thumb")
    async def get_thumb(path: str, request: Request):
        storage, path = _resolve_image_request(path, request)
        return await _server._thumb_response_async(
            storage,
            path,
            request,
            thumb_queue,
            thumb_cache,
            hotpath_metrics=hotpath_metrics,
        )

    @app.get("/file")
    def get_file(path: str, request: Request):
        storage, path = _resolve_image_request(path, request)
        return _server._file_response(storage, path, request=request, hotpath_metrics=hotpath_metrics)

    @app.get("/search", response_model=SearchResult)
    def search(request: Request, q: str = "", path: str = "/", limit: int = 100):
        storage = _server._storage_from_request(request)
        return _server._search_results(storage, to_item, q, _server._canonical_path(path), limit)
