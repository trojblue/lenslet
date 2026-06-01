from __future__ import annotations

from fastapi import FastAPI, Request, Response

from ..browse import ensure_image, storage_from_request
from ..context import get_request_context
from ..media import file_response, thumb_response_async
from ..paths import canonical_path
from ...storage.base import MediaStorage


def _resolve_media_request(path: str, request: Request) -> tuple[MediaStorage, str]:
    storage = storage_from_request(request)
    resolved_path = canonical_path(path)
    ensure_image(storage, resolved_path)
    return storage, resolved_path


def register_media_routes(app: FastAPI) -> None:
    @app.get("/thumb")
    async def get_thumb(path: str, request: Request) -> Response:
        storage, path = _resolve_media_request(path, request)
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
    def get_file(path: str, request: Request) -> Response:
        storage, path = _resolve_media_request(path, request)
        runtime = get_request_context(request).runtime
        return file_response(storage, path, request=request, hotpath_metrics=runtime.hotpath_metrics)
