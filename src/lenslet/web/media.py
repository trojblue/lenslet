"""Media and thumbnail response helpers for Lenslet."""

from __future__ import annotations

import asyncio
import os
import stat
from typing import TYPE_CHECKING, Literal

from fastapi import HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse

from ..media_errors import MediaDecodeError, MediaError, MediaReadError, RemoteMediaReadError
from ..storage.base import MediaStorage
from .cache.thumbs import ThumbCache
from .thumbs import ThumbnailScheduler

if TYPE_CHECKING:
    from .hotpath import HotpathTelemetry


class _ClientDisconnected(Exception):
    pass


def thumb_worker_count() -> int:
    cpu = os.cpu_count() or 2
    return max(1, min(4, cpu))


_FAST_PATH_FALLBACK_ERRORS = (OSError, ValueError)
_MEDIA_RESPONSE_ERRORS = (FileNotFoundError, MediaError)
_SAFE_STREAM_HEADERS = (
    "content-length",
    "content-range",
    "accept-ranges",
    "cache-control",
    "etag",
    "last-modified",
)


def _get_cached_thumbnail(storage: MediaStorage, path: str) -> bytes | None:
    get_cached = getattr(storage, "get_cached_thumbnail", None)
    if get_cached is None:
        return None
    try:
        return get_cached(path)
    except _FAST_PATH_FALLBACK_ERRORS:
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


def _thumb_cache_key(storage: MediaStorage, path: str) -> str | None:
    cache_key = getattr(storage, "thumbnail_cache_key", None)
    if cache_key is None:
        return None
    try:
        return cache_key(path)
    except _FAST_PATH_FALLBACK_ERRORS:
        return None


def media_failure_to_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(404, "file not found")
    if isinstance(exc, MediaDecodeError):
        return HTTPException(422, "failed to decode source image")
    if isinstance(exc, RemoteMediaReadError):
        if exc.category == "permission":
            return HTTPException(403, "remote source access denied")
        if exc.category == "timeout":
            return HTTPException(504, "remote source timed out")
        return HTTPException(502, "failed to read remote source")
    if isinstance(exc, MediaReadError):
        return HTTPException(500, "failed to read source image")
    return HTTPException(500, "failed to generate thumbnail")


def _existing_local_file(source: str) -> tuple[str, os.stat_result] | None:
    source_path = os.path.abspath(os.path.expanduser(source))
    try:
        stat_result = os.stat(source_path)
    except OSError:
        return None
    if not stat.S_ISREG(stat_result.st_mode):
        return None
    return source_path, stat_result


def _resolve_local_file_path(
    storage: MediaStorage,
    path: str,
) -> tuple[str, os.stat_result] | None:
    resolver = getattr(storage, "resolve_local_file_path", None)
    if resolver is None:
        return None
    try:
        source = resolver(path)
    except _FAST_PATH_FALLBACK_ERRORS:
        return None
    if source is None:
        return None
    return _existing_local_file(source)


def _remote_stream_response(
    storage: MediaStorage,
    path: str,
    request: Request | None,
) -> Response | None:
    opener = getattr(storage, "open_remote_media_stream", None)
    if opener is None:
        return None
    try:
        stream = opener(
            path,
            range_header=request.headers.get("range") if request is not None else None,
        )
    except _MEDIA_RESPONSE_ERRORS as exc:
        raise media_failure_to_http_error(exc) from exc
    except _FAST_PATH_FALLBACK_ERRORS as exc:
        read_error = MediaReadError.from_exception(path, exc)
        raise media_failure_to_http_error(read_error) from exc
    if stream is None:
        return None

    upstream_headers = getattr(stream, "headers", {}) or {}
    headers = {
        key: value
        for key in _SAFE_STREAM_HEADERS
        for value in (upstream_headers.get(key),)
        if value is not None
    }
    if "accept-ranges" not in headers:
        headers["accept-ranges"] = "bytes"
    media_type = upstream_headers.get("content-type") or storage.guess_mime(path)
    status_code = 206 if getattr(stream, "status_code", 200) == 206 else 200
    return StreamingResponse(
        stream.iter_bytes(),
        status_code=status_code,
        media_type=media_type,
        headers=headers,
    )


async def thumb_response_async(
    storage: MediaStorage,
    path: str,
    request: Request,
    queue: ThumbnailScheduler,
    thumb_cache: ThumbCache | None = None,
    hotpath_metrics: HotpathTelemetry | None = None,
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

    future = queue.submit(path, lambda: storage.get_or_build_thumbnail(path))
    try:
        thumb = await _await_thumbnail(request, future)
    except _ClientDisconnected:
        cancel_state = queue.cancel(path, future)
        if hotpath_metrics is not None:
            hotpath_metrics.increment("thumb_disconnect_cancel_total")
            if cancel_state in ("queued", "inflight"):
                hotpath_metrics.increment(f"thumb_disconnect_cancel_{cancel_state}_total")
        return Response(status_code=204)
    except _MEDIA_RESPONSE_ERRORS as exc:
        raise media_failure_to_http_error(exc) from exc
    except _FAST_PATH_FALLBACK_ERRORS as exc:
        read_error = MediaReadError.from_exception(path, exc)
        raise media_failure_to_http_error(read_error) from exc

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


def file_response(
    storage: MediaStorage,
    path: str,
    request: Request | None = None,
    hotpath_metrics: HotpathTelemetry | None = None,
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
    remote_stream = _remote_stream_response(storage, path, request)
    if remote_stream is not None:
        if hotpath_metrics is not None:
            hotpath_metrics.increment("file_response_remote_stream_total")
        return remote_stream
    if hotpath_metrics is not None:
        hotpath_metrics.increment("file_response_fallback_bytes_total")
    try:
        data = storage.read_bytes(path)
    except _MEDIA_RESPONSE_ERRORS as exc:
        raise media_failure_to_http_error(exc) from exc
    except _FAST_PATH_FALLBACK_ERRORS as exc:
        read_error = MediaReadError.from_exception(path, exc)
        raise media_failure_to_http_error(read_error) from exc
    return Response(content=data, media_type=media_type)
