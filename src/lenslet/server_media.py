"""Media and thumbnail response helpers for Lenslet."""

from __future__ import annotations

import asyncio
import os
import stat
from typing import Any, Literal

from fastapi import HTTPException, Request, Response
from fastapi.responses import FileResponse

from .thumb_cache import ThumbCache
from .thumbs import ThumbnailScheduler


class _ClientDisconnected(Exception):
    pass


def _thumb_worker_count() -> int:
    cpu = os.cpu_count() or 2
    return max(1, min(4, cpu))


def _get_cached_thumbnail(storage, path: str) -> bytes | None:
    getter = getattr(storage, "get_cached_thumbnail", None)
    if not callable(getter):
        return None
    try:
        return getter(path)
    except Exception:
        return None


async def _await_thumbnail(
    request: Request,
    future,
) -> bytes | None:
    wrapped = asyncio.wrap_future(future)
    while True:
        done, _ = await asyncio.wait({wrapped}, timeout=0.05)
        if done:
            try:
                return wrapped.result()
            except asyncio.CancelledError as exc:
                raise _ClientDisconnected() from exc
        if await request.is_disconnected():
            raise _ClientDisconnected()


def _thumb_cache_key(storage, path: str) -> str | None:
    try:
        return storage.thumbnail_cache_key(path)
    except Exception:
        return None


def _existing_local_file(source: str) -> tuple[str, os.stat_result] | None:
    source_path = os.path.abspath(os.path.expanduser(source))
    try:
        stat_result = os.stat(source_path)
    except OSError:
        return None
    if not stat.S_ISREG(stat_result.st_mode):
        return None
    return source_path, stat_result


def _resolve_local_file_path(storage, path: str) -> tuple[str, os.stat_result] | None:
    try:
        source = storage.resolve_local_file_path(path)
    except Exception:
        return None
    if source is None:
        return None
    return _existing_local_file(source)


async def _thumb_response_async(
    storage,
    path: str,
    request: Request,
    queue: ThumbnailScheduler,
    thumb_cache: ThumbCache | None = None,
    hotpath_metrics: Any | None = None,
) -> Response:
    cached = _get_cached_thumbnail(storage, path)
    if cached is not None:
        return Response(content=cached, media_type="image/webp")

    cache_key = None
    if thumb_cache is not None:
        cache_key = _thumb_cache_key(storage, path)
        if cache_key:
            cached_disk = thumb_cache.get(cache_key)
            if cached_disk is not None:
                return Response(content=cached_disk, media_type="image/webp")

    future = queue.submit(path, lambda: storage.get_thumbnail(path))
    try:
        thumb = await _await_thumbnail(request, future)
    except _ClientDisconnected:
        cancel_state = queue.cancel(path, future)
        if hotpath_metrics is not None:
            hotpath_metrics.increment("thumb_disconnect_cancel_total")
            if cancel_state in ("queued", "inflight"):
                hotpath_metrics.increment(f"thumb_disconnect_cancel_{cancel_state}_total")
        return Response(status_code=204)

    if thumb is None:
        raise HTTPException(500, "failed to generate thumbnail")
    if thumb_cache is not None and cache_key:
        thumb_cache.set(cache_key, thumb)
    return Response(content=thumb, media_type="image/webp")


FilePrefetchContext = Literal["viewer", "compare"]


def _file_prefetch_context(request: Request | None) -> FilePrefetchContext | None:
    if request is None:
        return None
    raw = (request.headers.get("x-lenslet-prefetch") or "").strip().lower()
    if raw == "viewer":
        return "viewer"
    if raw == "compare":
        return "compare"
    return None


def _file_response(
    storage,
    path: str,
    request: Request | None = None,
    hotpath_metrics: Any | None = None,
) -> Response:
    prefetch_context = _file_prefetch_context(request)
    if prefetch_context is not None and hotpath_metrics is not None:
        hotpath_metrics.increment(f"file_prefetch_{prefetch_context}_total")

    media_type = storage.guess_mime(path)
    local_hit = _resolve_local_file_path(storage, path)
    if local_hit is not None:
        local_path, stat_result = local_hit
        if hotpath_metrics is not None:
            hotpath_metrics.increment("file_response_local_stream_total")
        return FileResponse(path=local_path, media_type=media_type, stat_result=stat_result)
    if hotpath_metrics is not None:
        hotpath_metrics.increment("file_response_fallback_bytes_total")
    data = storage.read_bytes(path)
    return Response(content=data, media_type=media_type)
