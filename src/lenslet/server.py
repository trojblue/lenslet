"""FastAPI server for Lenslet."""
from __future__ import annotations
import asyncio
import contextlib
import io
import json
import os
import time
import threading
import html
import math
from collections import deque
from dataclasses import dataclass
from urllib.parse import urlparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin, UnidentifiedImageError
from pydantic import ValidationError
from . import og


class NoCacheIndexStaticFiles(StaticFiles):
    """Serve static assets with no-cache for HTML shell.

    Keeps JS/CSS cacheable while forcing index.html to revalidate so
    rebuilt frontends are picked up immediately.
    """

    async def get_response(self, path: str, scope):  # type: ignore[override]
        response = await super().get_response(path, scope)
        if response.media_type == "text/html":
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

from .metadata import read_png_info, read_jpeg_info, read_webp_info
from .embeddings.cache import EmbeddingCache
from .embeddings.config import EmbeddingConfig
from .embeddings.detect import columns_without_embeddings, detect_embeddings, EmbeddingDetection
from .embeddings.index import EmbeddingIndexError, EmbeddingManager
from .storage.memory import MemoryStorage
from .storage.dataset import DatasetStorage
from .storage.table import TableStorage, load_parquet_schema, load_parquet_table
from .thumbs import ThumbnailScheduler
from .thumb_cache import ThumbCache
from .og_cache import OgImageCache
from .workspace import Workspace
from .server_models import (
    DirEntry,
    ExportComparisonRequest,
    EmbeddingRejectedPayload,
    EmbeddingSearchItem,
    EmbeddingSearchRequest,
    EmbeddingSearchResponse,
    EmbeddingSpecPayload,
    EmbeddingsResponse,
    FolderIndex,
    ImageMetadataResponse,
    Item,
    PresenceLeavePayload,
    PresenceMovePayload,
    PresencePayload,
    SearchResult,
    Sidecar,
    SidecarPatch,
    ViewsPayload,
)
from .server_sync import (
    _apply_patch_to_meta,
    _canonical_path,
    _client_id_from_request,
    _ensure_meta_fields,
    _format_sse,
    _gallery_id_from_path,
    _init_sync_state,
    _last_event_id_from_request,
    _now_iso,
    _parse_if_match,
    _sidecar_from_meta,
    _sidecar_payload,
    _updated_by_from_request,
    PresenceCount,
    PresenceLeaseError,
    PresenceScopeError,
    PresenceTracker,
)


def _storage_from_request(request: Request):
    return request.state.storage  # type: ignore[attr-defined]


def _ensure_image(storage, path: str) -> None:
    try:
        storage.validate_image_path(path)
    except FileNotFoundError:
        raise HTTPException(404, "file not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))


def _build_sidecar(storage, path: str) -> Sidecar:
    meta = storage.get_metadata(path)
    return _sidecar_from_meta(meta)


def _build_image_metadata(storage, path: str) -> ImageMetadataResponse:
    mime = storage._guess_mime(path)  # type: ignore[attr-defined]
    if mime not in ("image/png", "image/jpeg", "image/webp"):
        raise HTTPException(415, "metadata reading supports PNG, JPEG, and WebP images only")

    try:
        raw = storage.read_bytes(path)
        if mime == "image/png":
            meta = read_png_info(io.BytesIO(raw))
            fmt = "png"
        elif mime == "image/jpeg":
            meta = read_jpeg_info(io.BytesIO(raw))
            fmt = "jpeg"
        else:
            meta = read_webp_info(io.BytesIO(raw))
            fmt = "webp"
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - unexpected parse errors
        raise HTTPException(500, f"failed to parse metadata: {exc}")

    return ImageMetadataResponse(path=path, format=fmt, meta=meta)


MAX_EXPORT_SOURCE_PIXELS = 64_000_000
MAX_EXPORT_STITCHED_PIXELS = 120_000_000
MAX_EXPORT_METADATA_BYTES = 32 * 1024
MAX_EXPORT_LABELS = 2
MAX_EXPORT_LABEL_CHARS = 120
EXPORT_COMPARISON_METADATA_KEY = "lenslet:comparison"
_UNIBOX_IMAGE_UTILS: tuple[Callable[..., Any], Callable[..., Any]] | None = None


def _error_response(status: int, error: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": error, "message": message})


def _first_validation_error_detail(exc: ValidationError) -> str:
    first = exc.errors()[0] if exc.errors() else {"msg": "invalid request payload", "loc": ()}
    loc = ".".join(str(part) for part in first.get("loc", ()))
    msg = str(first.get("msg", "invalid request payload"))
    return f"{loc}: {msg}" if loc else msg


def _path_validation_error_response(exc: HTTPException) -> JSONResponse:
    message = str(exc.detail)
    if exc.status_code == 404:
        return _error_response(404, "file_not_found", message)
    return _error_response(400, "invalid_path", message)


def _comparison_export_error_response(exc: HTTPException) -> JSONResponse:
    detail = str(exc.detail)
    if exc.status_code == 404:
        return _error_response(404, "file_not_found", detail)
    if exc.status_code == 415:
        return _error_response(415, "unsupported_source_format", detail)
    if exc.status_code == 500 and "unibox is required" in detail:
        return _error_response(500, "unibox_missing", detail)
    if exc.status_code != 400:
        return _error_response(500, "export_failed", detail)
    if "pixel limit" in detail:
        return _error_response(400, "export_too_large", detail)
    if "metadata exceeds configured limit" in detail:
        return _error_response(400, "metadata_too_large", detail)
    if "labels" in detail:
        return _error_response(400, "invalid_labels", detail)
    return _error_response(400, "invalid_request", detail)


def _get_unibox_image_utils() -> tuple[Callable[..., Any], Callable[..., Any]]:
    global _UNIBOX_IMAGE_UTILS
    if _UNIBOX_IMAGE_UTILS is not None:
        return _UNIBOX_IMAGE_UTILS
    try:
        from unibox.utils.image_utils import add_annotation, concatenate_images_horizontally
    except ImportError as exc:
        raise RuntimeError(
            "unibox is required for comparison export. Install with: pip install unibox"
        ) from exc
    _UNIBOX_IMAGE_UTILS = (concatenate_images_horizontally, add_annotation)
    return _UNIBOX_IMAGE_UTILS


def _sanitize_export_label(raw: str) -> str:
    cleaned = "".join(ch for ch in raw if ord(ch) >= 32 and ord(ch) != 127).strip()
    if len(cleaned) > MAX_EXPORT_LABEL_CHARS:
        raise ValueError(f"labels must be <= {MAX_EXPORT_LABEL_CHARS} characters after sanitation")
    return cleaned


def _normalize_export_labels(labels: list[str] | None) -> list[str]:
    if labels is None:
        return []
    if len(labels) > MAX_EXPORT_LABELS:
        raise ValueError(f"expected at most {MAX_EXPORT_LABELS} labels")
    return [_sanitize_export_label(value) for value in labels]


def _default_export_label(path: str, idx: int) -> str:
    name = Path(path).name.strip()
    if name:
        return name[:MAX_EXPORT_LABEL_CHARS]
    return "A" if idx == 0 else "B"


def _resolve_export_paths_and_labels(
    paths: list[str],
    labels: list[str],
    reverse_order: bool,
) -> tuple[list[str], list[str]]:
    ordered_paths = list(paths)
    label_slots = list(labels[:MAX_EXPORT_LABELS])
    label_slots.extend([""] * (MAX_EXPORT_LABELS - len(label_slots)))
    if reverse_order:
        ordered_paths.reverse()
        label_slots.reverse()

    ordered_labels: list[str] = []
    for idx, path in enumerate(ordered_paths):
        label = label_slots[idx]
        ordered_labels.append(label if label else _default_export_label(path, idx))
    return ordered_paths, ordered_labels


def _load_export_image(storage, path: str) -> tuple[Image.Image, str]:
    try:
        raw = storage.read_bytes(path)
    except FileNotFoundError:
        raise HTTPException(404, f"source image not found: {path}")
    except Exception as exc:
        raise HTTPException(500, f"failed to read source image {path}: {exc}")

    try:
        with Image.open(io.BytesIO(raw)) as source:
            source.load()
            source_format = (source.format or "").upper()
            if source_format not in {"PNG", "JPEG", "WEBP"}:
                raise HTTPException(415, f"unsupported source format for {path}")
            width, height = source.size
            if width <= 0 or height <= 0:
                raise HTTPException(415, f"invalid source dimensions for {path}")
            if width * height > MAX_EXPORT_SOURCE_PIXELS:
                raise HTTPException(400, f"source image exceeds pixel limit: {path}")
            return source.copy(), source_format.lower()
    except HTTPException:
        raise
    except UnidentifiedImageError:
        raise HTTPException(415, f"unsupported source format for {path}")
    except OSError as exc:
        raise HTTPException(415, f"failed to decode source image {path}: {exc}")


def _build_export_png(
    images: list[Image.Image],
    labels: list[str],
    *,
    embed_metadata: bool,
    ordered_paths: list[str],
    source_formats: list[str],
    reversed_order: bool,
) -> bytes:
    try:
        concatenate_images_horizontally, add_annotation = _get_unibox_image_utils()
    except RuntimeError as exc:
        raise HTTPException(500, str(exc))

    annotated: list[Image.Image] = []
    stitched: Image.Image | None = None
    try:
        for image, label in zip(images, labels):
            annotated.append(
                _annotate_for_export(
                    image,
                    label,
                    add_annotation=add_annotation,
                )
            )
        if len(annotated) != len(images):
            raise HTTPException(500, "failed to annotate all images")
        max_height = max(image.height for image in annotated)
        stitched = concatenate_images_horizontally(annotated, max_height=max_height)
        if stitched is None:
            raise HTTPException(500, "failed to stitch comparison image")
        stitched_pixels = stitched.width * stitched.height
        if stitched_pixels > MAX_EXPORT_STITCHED_PIXELS:
            raise HTTPException(400, "stitched output exceeds configured pixel limit")

        pnginfo: PngImagePlugin.PngInfo | None = None
        if embed_metadata:
            metadata_payload = {
                "tool": "lenslet.export_comparison",
                "version": 1,
                "paths": ordered_paths,
                "labels": labels,
                "source_formats": source_formats,
                "reversed": reversed_order,
                "exported_at": _now_iso(),
            }
            metadata_text = json.dumps(metadata_payload, separators=(",", ":"), ensure_ascii=True)
            metadata_size = len(metadata_text.encode("utf-8"))
            if metadata_size > MAX_EXPORT_METADATA_BYTES:
                raise HTTPException(400, "embedded metadata exceeds configured limit")
            pnginfo = PngImagePlugin.PngInfo()
            pnginfo.add_text(EXPORT_COMPARISON_METADATA_KEY, metadata_text)

        out = io.BytesIO()
        save_kwargs: dict[str, Any] = {"format": "PNG"}
        if pnginfo is not None:
            save_kwargs["pnginfo"] = pnginfo
        stitched.save(out, **save_kwargs)
        return out.getvalue()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"failed to build comparison image: {exc}")
    finally:
        if stitched is not None:
            stitched.close()
        for image in annotated:
            image.close()


def _comparison_export_filename(reverse_order: bool) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = "_reverse" if reverse_order else ""
    return f"comparison{suffix}_{stamp}.png"


def _annotate_for_export(
    image: Image.Image,
    label: str,
    *,
    add_annotation: Callable[..., Any],
) -> Image.Image:
    try:
        annotated = add_annotation(
            image,
            annotation=label,
            position="top",
            alignment="center",
            size="default",
        )
        if isinstance(annotated, Image.Image):
            return annotated
    except Exception:
        pass
    return _fallback_add_annotation(image, label)


def _fallback_add_annotation(image: Image.Image, label: str) -> Image.Image:
    base = image.convert("RGB")
    font = ImageFont.load_default()
    probe = ImageDraw.Draw(base)
    left, top, right, bottom = probe.textbbox((0, 0), label, font=font)
    text_width = max(1, right - left)
    text_height = max(1, bottom - top)
    padding = 8
    title_height = text_height + (padding * 2)
    canvas = Image.new("RGB", (base.width, base.height + title_height), (255, 255, 255))
    canvas.paste(base, (0, title_height))
    draw = ImageDraw.Draw(canvas)
    text_x = max(0, (canvas.width - text_width) // 2)
    text_y = max(0, (title_height - text_height) // 2)
    draw.text((text_x, text_y), label, fill=(0, 0, 0), font=font)
    return canvas


def _build_item(cached, meta: dict, source: str | None = None) -> Item:
    if source is None:
        source = getattr(cached, "source", None)
    canonical = _canonical_path(cached.path)
    metrics = getattr(cached, "metrics", None)
    if metrics is None:
        metrics = meta.get("metrics")
    return Item(
        path=canonical,
        name=cached.name,
        type=cached.mime,
        w=cached.width,
        h=cached.height,
        size=cached.size,
        hasThumb=True,
        hasMeta=True,
        addedAt=datetime.fromtimestamp(cached.mtime, tz=timezone.utc).isoformat(),
        star=meta.get("star"),
        comments=meta.get("notes", ""),
        url=getattr(cached, "url", None),
        source=source,
        metrics=metrics,
    )


def _child_folder_path(parent: str, child: str) -> str:
    parent_path = _canonical_path(parent)
    return _canonical_path(f"{parent_path.rstrip('/')}/{child}")


RECURSIVE_PAGE_DEFAULT = 1
RECURSIVE_PAGE_SIZE_DEFAULT = 200
RECURSIVE_PAGE_SIZE_MAX = 500


@dataclass(frozen=True)
class _RecursivePaginationWindow:
    page: int
    page_size: int
    page_count: int
    total_items: int
    start: int
    end: int


class HotpathTelemetry:
    """Lightweight in-process counters/timers for hot-path visibility."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {}
        self._timers: dict[str, tuple[int, float]] = {}

    def increment(self, key: str, amount: int = 1) -> None:
        if amount == 0:
            return
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + amount

    def observe_ms(self, key: str, duration_ms: float) -> None:
        if duration_ms < 0:
            duration_ms = 0
        with self._lock:
            count, total = self._timers.get(key, (0, 0.0))
            self._timers[key] = (count + 1, total + duration_ms)

    def snapshot(self, storage=None) -> dict[str, Any]:
        with self._lock:
            counters = dict(self._counters)
            timers = {
                key: {
                    "count": count,
                    "total_ms": round(total_ms, 3),
                    "avg_ms": round(total_ms / count, 3) if count else 0.0,
                }
                for key, (count, total_ms) in self._timers.items()
            }
        s3_creations = _storage_s3_client_creations(storage)
        if s3_creations is not None:
            counters["s3_client_create_total"] = s3_creations
        return {
            "counters": counters,
            "timers_ms": timers,
        }


def _create_hotpath_metrics(app: FastAPI) -> HotpathTelemetry:
    metrics = HotpathTelemetry()
    app.state.hotpath_metrics = metrics
    return metrics


def _labels_health_payload(workspace: Workspace) -> dict[str, Any]:
    if not workspace.can_write:
        return {"enabled": False, "log": None, "snapshot": None}
    return {
        "enabled": True,
        "log": str(workspace.labels_log_path()),
        "snapshot": str(workspace.labels_snapshot_path()),
    }


def _storage_s3_client_creations(storage) -> int | None:
    getter = getattr(storage, "s3_client_creations", None)
    if callable(getter):
        try:
            return int(getter())
        except Exception:
            return None
    raw = getattr(storage, "_s3_client_creations", None)
    if isinstance(raw, int):
        return raw
    return None


def _parse_recursive_pagination_value(name: str, raw: str | None, default: int) -> int:
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(400, f"{name} must be an integer")
    if value <= 0:
        raise HTTPException(400, f"{name} must be >= 1")
    return value


def _resolve_recursive_pagination(page: str | None, page_size: str | None) -> tuple[int, int]:
    resolved_page = _parse_recursive_pagination_value("page", page, RECURSIVE_PAGE_DEFAULT)
    resolved_page_size = _parse_recursive_pagination_value(
        "page_size",
        page_size,
        RECURSIVE_PAGE_SIZE_DEFAULT,
    )
    if resolved_page_size > RECURSIVE_PAGE_SIZE_MAX:
        resolved_page_size = RECURSIVE_PAGE_SIZE_MAX
    return resolved_page, resolved_page_size


def _resolve_recursive_window(total_items: int, page: str | None, page_size: str | None) -> _RecursivePaginationWindow:
    resolved_page, resolved_page_size = _resolve_recursive_pagination(page, page_size)
    page_count = max(1, math.ceil(total_items / resolved_page_size))
    start = (resolved_page - 1) * resolved_page_size
    end = start + resolved_page_size
    return _RecursivePaginationWindow(
        page=resolved_page,
        page_size=resolved_page_size,
        page_count=page_count,
        total_items=total_items,
        start=start,
        end=end,
    )


def _collect_recursive_cached_items(storage, root_path: str, root_index: Any) -> list[Any]:
    queue: deque[tuple[str, Any]] = deque([(root_path, root_index)])
    seen_folders: set[str] = set()
    seen_items: set[str] = set()
    items: list[tuple[str, Any]] = []

    while queue:
        folder_path, folder_index = queue.popleft()
        canonical_folder = _canonical_path(folder_path)
        if canonical_folder in seen_folders:
            continue
        seen_folders.add(canonical_folder)

        for cached in folder_index.items:
            item_path = _canonical_path(getattr(cached, "path", ""))
            if not item_path:
                continue
            if item_path in seen_items:
                continue
            seen_items.add(item_path)
            items.append((item_path, cached))

        for child_name in sorted(folder_index.dirs):
            child_path = _child_folder_path(canonical_folder, child_name)
            if child_path in seen_folders:
                continue
            try:
                child_index = storage.get_index(child_path)
            except (FileNotFoundError, ValueError):
                continue
            queue.append((child_path, child_index))

    items.sort(key=lambda pair: pair[0])
    return [cached for _, cached in items]


def _build_recursive_items(
    storage,
    to_item,
    cached_items: list[Any],
    page: str | None,
    page_size: str | None,
    legacy_recursive: bool,
) -> tuple[list[Item], _RecursivePaginationWindow | None]:
    if legacy_recursive:
        return [to_item(storage, it) for it in cached_items], None

    window = _resolve_recursive_window(len(cached_items), page, page_size)
    page_items = cached_items[window.start:window.end]
    return [to_item(storage, it) for it in page_items], window


def _build_folder_index(
    storage,
    path: str,
    to_item,
    recursive: bool = False,
    page: str | None = None,
    page_size: str | None = None,
    legacy_recursive: bool = False,
    hotpath_metrics: HotpathTelemetry | None = None,
) -> FolderIndex:
    try:
        index = storage.get_index(path)
    except ValueError:
        raise HTTPException(400, "invalid path")
    except FileNotFoundError:
        raise HTTPException(404, "folder not found")

    page_window: _RecursivePaginationWindow | None = None
    if recursive:
        if hotpath_metrics is not None:
            hotpath_metrics.increment("folders_recursive_requests_total")
        traversal_started = time.perf_counter()
        cached_items = _collect_recursive_cached_items(storage, _canonical_path(path), index)
        if hotpath_metrics is not None:
            hotpath_metrics.observe_ms(
                "folders_recursive_traversal_ms",
                (time.perf_counter() - traversal_started) * 1000.0,
            )
            hotpath_metrics.increment("folders_recursive_items_total", len(cached_items))
        items, page_window = _build_recursive_items(
            storage,
            to_item,
            cached_items,
            page=page,
            page_size=page_size,
            legacy_recursive=legacy_recursive,
        )
    else:
        items = [to_item(storage, it) for it in index.items]

    dirs = [DirEntry(name=d, kind="branch") for d in sorted(index.dirs)]

    return FolderIndex(
        path=_canonical_path(path),
        generatedAt=index.generated_at,
        items=items,
        dirs=dirs,
        page=page_window.page if page_window else None,
        pageSize=page_window.page_size if page_window else None,
        pageCount=page_window.page_count if page_window else None,
        totalItems=page_window.total_items if page_window else None,
    )


def _register_folder_route(
    app: FastAPI,
    to_item,
    hotpath_metrics: HotpathTelemetry | None = None,
) -> None:
    @app.get("/folders", response_model=FolderIndex)
    def get_folder(
        path: str = "/",
        recursive: bool = False,
        page: str | None = None,
        page_size: str | None = None,
        legacy_recursive: bool = False,
        request: Request = None,
    ):
        storage = _storage_from_request(request)
        return _build_folder_index(
            storage,
            _canonical_path(path),
            to_item,
            recursive=recursive,
            page=page,
            page_size=page_size,
            legacy_recursive=legacy_recursive,
            hotpath_metrics=hotpath_metrics,
        )


def _update_item(storage, path: str, body: Sidecar, updated_by: str) -> Sidecar:
    meta = storage.get_metadata(path)
    meta = _ensure_meta_fields(meta)
    meta["tags"] = body.tags
    meta["notes"] = body.notes
    meta["star"] = body.star
    meta["version"] = meta.get("version", 1) + 1
    meta["updated_at"] = _now_iso()
    meta["updated_by"] = updated_by
    storage.set_metadata(path, meta)
    return _sidecar_from_meta(meta)


class _ClientDisconnected(Exception):
    pass


def _thumb_worker_count() -> int:
    cpu = os.cpu_count() or 2
    return max(1, min(4, cpu))


def _get_cached_thumbnail(storage, path: str) -> bytes | None:
    cache = getattr(storage, "_thumbnails", None)
    if not isinstance(cache, dict):
        return None
    if path in cache:
        return cache[path]
    normalizer = getattr(storage, "_normalize_path", None)
    if callable(normalizer):
        try:
            norm = normalizer(path)
        except Exception:
            return None
        return cache.get(norm)
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
    source = _thumb_cache_source(storage, path)
    if not source:
        return None
    size = getattr(storage, "thumb_size", "")
    quality = getattr(storage, "thumb_quality", "")
    parts = [source, str(size), str(quality)]
    if not _is_remote_source(source):
        try:
            etag = storage.etag(path)
        except Exception:
            etag = None
        if etag:
            parts.append(str(etag))
    return "|".join(parts)


def _thumb_cache_source(storage, path: str) -> str | None:
    source = None
    getter = getattr(storage, "get_source_path", None)
    if callable(getter):
        try:
            source = getter(path)
        except Exception:
            source = None
    if source is None:
        mapping = getattr(storage, "_source_paths", None)
        if isinstance(mapping, dict):
            source = mapping.get(path)
            if source is None:
                normalizer = getattr(storage, "_normalize_path", None)
                if callable(normalizer):
                    try:
                        norm = normalizer(path)
                        source = mapping.get(norm)
                    except Exception:
                        source = None
    if not source:
        source = path
    if not _is_remote_source(source):
        root = getattr(storage, "root", None)
        if root and not os.path.isabs(source):
            source = os.path.join(root, source)
    return source


def _is_remote_source(source: str) -> bool:
    return source.startswith("s3://") or source.startswith("http://") or source.startswith("https://")


def _existing_local_file(source: str) -> str | None:
    source_path = os.path.abspath(os.path.expanduser(source))
    if not os.path.isfile(source_path):
        return None
    return source_path


def _resolve_local_file_path(storage, path: str) -> str | None:
    source = _thumb_cache_source(storage, path)
    if not source or _is_remote_source(source):
        return None

    resolver = getattr(storage, "_resolve_local_source", None)
    if callable(resolver):
        try:
            source = resolver(source)
        except Exception:
            return None

    local = getattr(storage, "local", None)
    local_resolver = getattr(local, "resolve_path", None)
    if callable(local_resolver):
        try:
            source = local_resolver(path)
        except Exception:
            pass

    return _existing_local_file(source)


def _og_cache_key(workspace: Workspace, style: str, signature: str, path: str) -> str:
    safe_path = og.normalize_path(path)
    return f"og:{style}:{signature}:{safe_path}"


def _dataset_signature(storage, workspace: Workspace) -> str:
    mtime = _dataset_mtime(workspace)
    if mtime is not None:
        return f"parquet:{int(mtime)}"
    try:
        index = storage.get_index("/")
    except Exception:
        return "unknown"
    items = getattr(index, "items", [])
    if not items:
        return "empty"
    max_mtime = 0.0
    for item in items:
        value = getattr(item, "mtime", 0.0) or 0.0
        if value > max_mtime:
            max_mtime = value
    return f"mem:{int(max_mtime)}:{len(items)}"


def _og_path_from_request(path: str | None, request: Request | None) -> str:
    if path:
        return og.normalize_path(path)
    fragment = None
    if request is not None:
        referer = request.headers.get("referer")
        if referer:
            fragment = urlparse(referer).fragment or None
    return og.normalize_path(fragment)


def _dataset_mtime(workspace: Workspace) -> float | None:
    if workspace.views_override is not None:
        name = workspace.views_override.name
        if name.endswith(".lenslet.json"):
            parquet = workspace.views_override.with_name(name[: -len(".lenslet.json")])
            if parquet.exists():
                return parquet.stat().st_mtime
    if workspace.root is not None:
        dataset_root = workspace.root.parent
        items = dataset_root / "items.parquet"
        if items.is_file():
            return items.stat().st_mtime
        try:
            return dataset_root.stat().st_mtime
        except Exception:
            return None
    return None


def _dataset_label(workspace: Workspace) -> str:
    if workspace.views_override is not None:
        name = workspace.views_override.name
        if name.endswith(".lenslet.json"):
            name = name[: -len(".lenslet.json")]
        label = Path(name).stem
        return label or "dataset"
    if workspace.root is not None:
        label = workspace.root.parent.name
        return label or "dataset"
    return "dataset"


def _dataset_count(storage) -> int | None:
    items = getattr(storage, "_items", None)
    if isinstance(items, dict):
        return len(items)
    if isinstance(items, list):
        return len(items)
    indexes = getattr(storage, "_indexes", None)
    if isinstance(indexes, dict):
        root = indexes.get("") or indexes.get("/")
        if root is not None and hasattr(root, "items"):
            try:
                return len(root.items)
            except Exception:
                return None
    return None


class _PresenceMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._invalid_lease_total = 0

    def record_invalid_lease(self) -> None:
        with self._lock:
            self._invalid_lease_total += 1

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {"invalid_lease_total": self._invalid_lease_total}


def _presence_runtime_payload(
    *,
    presence: PresenceTracker,
    broker,
    metrics: _PresenceMetrics,
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


def _presence_count_payload(count: PresenceCount) -> dict[str, int | str]:
    return {
        "gallery_id": count.gallery_id,
        "viewing": count.viewing,
        "editing": count.editing,
    }


def _presence_payload_for_client(
    count: PresenceCount,
    client_id: str,
    lease_id: str,
) -> dict[str, int | str]:
    payload: dict[str, int | str] = _presence_count_payload(count)
    payload["client_id"] = client_id
    payload["lease_id"] = lease_id
    return payload


def _presence_count_for_gallery(counts: list[PresenceCount], gallery_id: str) -> PresenceCount:
    for count in counts:
        if count.gallery_id == gallery_id:
            return count
    return PresenceCount(gallery_id=gallery_id, viewing=0, editing=0)


def _publish_presence_counts(broker, counts: list[PresenceCount]) -> None:
    for count in counts:
        broker.publish("presence", _presence_count_payload(count))


def _publish_presence_deltas(
    broker,
    previous: dict[str, PresenceCount],
    current: dict[str, PresenceCount],
) -> None:
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


def _install_presence_prune_loop(
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
            _publish_presence_deltas(broker, previous, current)
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


def _presence_invalid_lease_payload(gallery_id: str, client_id: str) -> dict[str, str]:
    return {
        "error": "invalid_lease",
        "gallery_id": gallery_id,
        "client_id": client_id,
    }


def _presence_scope_mismatch_payload(
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


def _touch_presence_edit(presence: PresenceTracker, broker, gallery_id: str, client_id: str) -> None:
    _, counts = presence.touch_edit(gallery_id, client_id)
    _publish_presence_counts(broker, counts)


def _require_presence_client_id(client_id: str) -> str:
    if not client_id:
        raise HTTPException(400, "client_id required")
    return client_id


def _register_presence_routes(
    app: FastAPI,
    presence: PresenceTracker,
    broker,
    *,
    lifecycle_v2_enabled: bool,
    metrics: _PresenceMetrics,
) -> None:
    def _presence_diag() -> dict[str, Any]:
        prune_interval = float(getattr(app.state, "presence_prune_interval", 5.0))
        return _presence_runtime_payload(
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
        client_id = _require_presence_client_id(body.client_id)
        try:
            if lifecycle_v2_enabled:
                lease_id, counts = presence.join(gallery_id, client_id, lease_id=body.lease_id)
            else:
                lease_id, counts = presence.touch_view(gallery_id, client_id, lease_id=body.lease_id)
        except PresenceLeaseError:
            metrics.record_invalid_lease()
            payload = _presence_invalid_lease_payload(gallery_id=gallery_id, client_id=client_id)
            return JSONResponse(status_code=409, content=payload)
        _publish_presence_counts(broker, counts)
        current = _presence_count_for_gallery(counts, gallery_id)
        return _presence_payload_for_client(current, client_id, lease_id)

    @app.post("/presence/move")
    def presence_move(body: PresenceMovePayload):
        from_gallery_id = _canonical_path(body.from_gallery_id)
        to_gallery_id = _canonical_path(body.to_gallery_id)
        client_id = _require_presence_client_id(body.client_id)
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
            metrics.record_invalid_lease()
            payload = _presence_invalid_lease_payload(gallery_id=from_gallery_id, client_id=client_id)
            return JSONResponse(status_code=409, content=payload)
        except PresenceScopeError as exc:
            payload = _presence_scope_mismatch_payload(exc, requested_gallery_id=from_gallery_id, client_id=client_id)
            return JSONResponse(status_code=409, content=payload)
        _publish_presence_counts(broker, counts)
        from_scope = _presence_count_for_gallery(counts, from_gallery_id)
        to_scope = _presence_count_for_gallery(counts, to_gallery_id)
        return {
            "client_id": client_id,
            "lease_id": response_lease_id,
            "from_scope": _presence_count_payload(from_scope),
            "to_scope": _presence_count_payload(to_scope),
        }

    @app.post("/presence/leave")
    def presence_leave(body: PresenceLeavePayload):
        gallery_id = _canonical_path(body.gallery_id)
        client_id = _require_presence_client_id(body.client_id)
        if not lifecycle_v2_enabled:
            current = presence.snapshot_counts().get(gallery_id, PresenceCount(gallery_id=gallery_id, viewing=0, editing=0))
            payload = _presence_payload_for_client(current, client_id, body.lease_id)
            payload["removed"] = False
            payload["mode"] = "legacy_heartbeat"
            return payload
        try:
            removed, counts = presence.leave(gallery_id=gallery_id, client_id=client_id, lease_id=body.lease_id)
        except PresenceLeaseError:
            metrics.record_invalid_lease()
            payload = _presence_invalid_lease_payload(gallery_id=gallery_id, client_id=client_id)
            return JSONResponse(status_code=409, content=payload)
        except PresenceScopeError as exc:
            payload = _presence_scope_mismatch_payload(exc, requested_gallery_id=gallery_id, client_id=client_id)
            return JSONResponse(status_code=409, content=payload)
        _publish_presence_counts(broker, counts)
        current = _presence_count_for_gallery(counts, gallery_id)
        payload = _presence_payload_for_client(current, client_id, body.lease_id)
        payload["removed"] = removed
        return payload

    @app.post("/presence")
    def presence_heartbeat(body: PresencePayload):
        gallery_id = _canonical_path(body.gallery_id)
        client_id = _require_presence_client_id(body.client_id)
        try:
            lease_id, counts = presence.touch_view(gallery_id, client_id, lease_id=body.lease_id)
        except PresenceLeaseError:
            metrics.record_invalid_lease()
            payload = _presence_invalid_lease_payload(gallery_id=gallery_id, client_id=client_id)
            return JSONResponse(status_code=409, content=payload)
        _publish_presence_counts(broker, counts)
        current = _presence_count_for_gallery(counts, gallery_id)
        return _presence_payload_for_client(current, client_id, lease_id)


def _inject_meta_tags(html_text: str, tags: str) -> str:
    marker = "</head>"
    idx = html_text.lower().find(marker)
    if idx == -1:
        return html_text + tags
    return html_text[:idx] + tags + html_text[idx:]


def _build_meta_tags(title: str, description: str, image_url: str, logo_url: str | None = None) -> str:
    safe_title = html.escape(title, quote=True)
    safe_desc = html.escape(description, quote=True)
    safe_image = html.escape(image_url, quote=True)
    safe_logo = html.escape(logo_url, quote=True) if logo_url else None
    return "\n".join([
        f'    <meta property="og:title" content="{safe_title}" />',
        f'    <meta property="og:description" content="{safe_desc}" />',
        f'    <meta property="og:image" content="{safe_image}" />',
        f'    <meta property="og:logo" content="{safe_logo}" />' if safe_logo else '',
        '    <meta property="og:type" content="website" />',
        '    <meta name="twitter:card" content="summary_large_image" />',
        f'    <meta name="twitter:title" content="{safe_title}" />',
        f'    <meta name="twitter:description" content="{safe_desc}" />',
        f'    <meta name="twitter:image" content="{safe_image}" />',
        "",
    ])


def _og_cache_from_workspace(workspace: Workspace, enabled: bool) -> OgImageCache | None:
    if not enabled or not workspace.can_write:
        return None
    cache_dir = workspace.og_cache_dir()
    if cache_dir is None:
        return None
    return OgImageCache(cache_dir)


async def _thumb_response_async(
    storage,
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
    hotpath_metrics: HotpathTelemetry | None = None,
) -> Response:
    prefetch_context = _file_prefetch_context(request)
    if prefetch_context is not None and hotpath_metrics is not None:
        hotpath_metrics.increment(f"file_prefetch_{prefetch_context}_total")

    media_type = storage._guess_mime(path)
    local_path = _resolve_local_file_path(storage, path)
    if local_path is not None:
        if hotpath_metrics is not None:
            hotpath_metrics.increment("file_response_local_stream_total")
        return FileResponse(path=local_path, media_type=media_type)
    if hotpath_metrics is not None:
        hotpath_metrics.increment("file_response_fallback_bytes_total")
    data = storage.read_bytes(path)
    return Response(content=data, media_type=media_type)


def _search_results(storage, to_item, q: str, path: str, limit: int) -> SearchResult:
    hits = storage.search(query=q, path=path, limit=limit)
    return SearchResult(items=[to_item(storage, it) for it in hits])


def _attach_storage(app: FastAPI, storage) -> None:
    @app.middleware("http")
    async def attach_storage(request: Request, call_next):
        request.state.storage = storage
        response = await call_next(request)
        return response


def _mount_frontend(app: FastAPI) -> None:
    frontend_dist = Path(__file__).parent / "frontend"
    if frontend_dist.is_dir():
        app.mount("/", NoCacheIndexStaticFiles(directory=str(frontend_dist), html=True), name="frontend")


def _build_index_title(label: str, total_count: int | None) -> str:
    title = f"Lenslet: {label}"
    if total_count is None:
        return title
    return f"{title} ({total_count:,} images)"


def _build_index_description(label: str, scope_path: str) -> str:
    if scope_path == "/":
        return f"Browse {label} gallery"
    return f"Browse {label} gallery in {scope_path}"


def _register_index_routes(app: FastAPI, storage, workspace: Workspace, og_preview: bool) -> None:
    frontend_dist = Path(__file__).parent / "frontend"
    index_path = frontend_dist / "index.html"
    if not index_path.is_file():
        return

    def render_index(request: Request):
        html_text = index_path.read_text(encoding="utf-8")
        if og_preview:
            label = _dataset_label(workspace)
            scope_path = og.normalize_path(request.query_params.get("path"))
            title = _build_index_title(label, _dataset_count(storage))
            description = _build_index_description(label, scope_path)
            image_url = request.url_for("og_image")
            path_param = request.query_params.get("path")
            if path_param:
                image_url = image_url.include_query_params(path=path_param)
            image_url = str(image_url)
            base = str(request.base_url)
            logo_url = f"{base}favicon.ico"
            tags = _build_meta_tags(title, description, image_url, logo_url)
            html_text = _inject_meta_tags(html_text, tags)
        response = Response(content=html_text, media_type="text/html")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    app.get("/", include_in_schema=False)(render_index)
    app.get("/index.html", include_in_schema=False)(render_index)


def _register_og_routes(app: FastAPI, storage, workspace: Workspace, enabled: bool) -> None:
    og_cache = _og_cache_from_workspace(workspace, enabled=enabled)

    @app.get("/og-image", include_in_schema=False, name="og_image")
    def og_image(request: Request, style: str = og.OG_STYLE, path: str | None = None):
        label = _dataset_label(workspace)
        if not enabled:
            return Response(content=og.fallback_og_image(label), media_type="image/png")
        style_key = style if style == og.OG_STYLE else og.OG_STYLE
        sample_path = _og_path_from_request(path, request)
        signature = _dataset_signature(storage, workspace)
        cache_key = _og_cache_key(workspace, style_key, signature, sample_path)
        if og_cache is not None:
            cached = og_cache.get(cache_key)
            if cached is not None:
                return Response(content=cached, media_type="image/png")

        sample_count = og.OG_IMAGES_X * og.OG_IMAGES_Y
        tiles: list[list[list[tuple[int, int, int]]]] = []
        for path in og.sample_paths(storage, sample_path, sample_count):
            try:
                thumb = storage.get_thumbnail(path)
            except Exception:
                thumb = None
            if not thumb:
                continue
            grid = og.pixel_tile_grid(thumb, og.OG_PIXELS_PER_IMAGE)
            if grid is not None:
                tiles.append(grid)
            if len(tiles) >= sample_count:
                break

        if not tiles:
            data = og.fallback_og_image(label)
        else:
            data = og.render_pixel_mosaic(
                tiles=tiles,
                width=og.OG_IMAGE_WIDTH,
                height=og.OG_IMAGE_HEIGHT,
                images_x=og.OG_IMAGES_X,
                images_y=og.OG_IMAGES_Y,
                pixels_per_image=og.OG_PIXELS_PER_IMAGE,
                gap=og.OG_TILE_GAP,
            )

        if og_cache is not None:
            og_cache.set(cache_key, data)
        return Response(content=data, media_type="image/png")


def _register_views_routes(app: FastAPI, workspace: Workspace) -> None:
    @app.get("/views", response_model=ViewsPayload)
    def get_views():
        return workspace.load_views()

    @app.put("/views", response_model=ViewsPayload)
    def put_views(body: ViewsPayload):
        payload = body.model_dump()
        workspace.save_views(payload)
        return body


def _resolve_embedding_detection(
    parquet_path: str,
    embedding_config: EmbeddingConfig | None,
) -> EmbeddingDetection:
    config = embedding_config or EmbeddingConfig()
    try:
        schema = load_parquet_schema(parquet_path)
    except Exception as exc:
        print(f"[lenslet] Warning: failed to read embedding schema: {exc}")
        return EmbeddingDetection.empty()
    try:
        return detect_embeddings(schema, config)
    except Exception as exc:
        print(f"[lenslet] Warning: failed to detect embeddings: {exc}")
        return EmbeddingDetection.empty()


def _build_embedding_manager(
    parquet_path: str,
    storage: TableStorage,
    detection: EmbeddingDetection,
    cache: EmbeddingCache | None = None,
    preload: bool = False,
    prefer_faiss: bool = True,
) -> EmbeddingManager | None:
    if not parquet_path:
        return None
    try:
        manager = EmbeddingManager(
            parquet_path=parquet_path,
            detection=detection.available,
            rejected=detection.rejected,
            row_to_path=storage.row_index_map(),
            cache=cache,
            prefer_faiss=prefer_faiss,
        )
        if preload:
            manager.preload()
        return manager
    except Exception as exc:
        print(f"[lenslet] Warning: failed to initialize embeddings: {exc}")
        return None


def _register_embedding_routes(
    app: FastAPI,
    storage,
    manager: EmbeddingManager | None,
) -> None:
    @app.get("/embeddings", response_model=EmbeddingsResponse)
    def get_embeddings():
        if manager is None:
            return EmbeddingsResponse()
        return EmbeddingsResponse(
            embeddings=[
                EmbeddingSpecPayload(
                    name=spec.name,
                    dimension=spec.dimension,
                    dtype=spec.dtype,
                    metric=spec.metric,
                )
                for spec in manager.available
            ],
            rejected=[
                EmbeddingRejectedPayload(name=rej.name, reason=rej.reason)
                for rej in manager.rejected
            ],
        )

    @app.post("/embeddings/search", response_model=EmbeddingSearchResponse)
    def search_embeddings(body: EmbeddingSearchRequest, request: Request = None):
        if manager is None:
            raise HTTPException(404, "embedding search unavailable")
        if not body.embedding:
            raise HTTPException(400, "embedding is required")
        if manager.get_spec(body.embedding) is None:
            raise HTTPException(404, "embedding not found")
        has_path = body.query_path is not None
        has_vector = body.query_vector_b64 is not None
        if has_path == has_vector:
            raise HTTPException(400, "provide exactly one of query_path or query_vector_b64")
        top_k = body.top_k
        if top_k <= 0 or top_k > 1000:
            raise HTTPException(400, "top_k must be between 1 and 1000")
        if body.min_score is not None and not math.isfinite(body.min_score):
            raise HTTPException(400, "min_score must be a finite number")

        try:
            if body.query_path is not None:
                path = _canonical_path(body.query_path)
                _ensure_image(storage, path)
                row_index = storage.row_index_for_path(path)
                if row_index is None:
                    raise HTTPException(404, "query_path not found")
                matches = manager.search_by_path(
                    body.embedding,
                    row_index=row_index,
                    top_k=top_k,
                    min_score=body.min_score,
                )
            else:
                matches = manager.search_by_vector(
                    body.embedding,
                    vector_b64=body.query_vector_b64 or "",
                    top_k=top_k,
                    min_score=body.min_score,
                )
        except EmbeddingIndexError as exc:
            raise HTTPException(400, str(exc))

        return EmbeddingSearchResponse(
            embedding=body.embedding,
            items=[
                EmbeddingSearchItem(
                    row_index=match.row_index,
                    path=_canonical_path(match.path),
                    score=match.score,
                )
                for match in matches
            ],
        )


RecordUpdateFn = Callable[[str, dict, str], None]


def _build_record_update(
    storage,
    *,
    broker,
    workspace: Workspace,
    log_lock: threading.Lock,
    snapshotter,
    sync_state: dict[str, int],
) -> RecordUpdateFn:
    def _record_update(path: str, meta: dict, event_type: str = "item-updated") -> None:
        payload = _sidecar_payload(path, meta)
        event_id = broker.publish(event_type, payload)
        sync_state["last_event_id"] = event_id
        if workspace.can_write:
            entry = {"id": event_id, "type": event_type, **payload}
            try:
                with log_lock:
                    workspace.append_labels_log(entry)
            except Exception as exc:
                print(f"[lenslet] Warning: failed to append labels log: {exc}")
            snapshotter.maybe_write(storage, event_id)

    return _record_update


def _register_common_api_routes(
    app: FastAPI,
    to_item,
    *,
    meta_lock: threading.Lock,
    presence: PresenceTracker,
    broker,
    lifecycle_v2_enabled: bool,
    presence_metrics,
    idempotency_cache,
    record_update: RecordUpdateFn,
    thumb_queue: ThumbnailScheduler,
    thumb_cache: ThumbCache | None,
    hotpath_metrics: HotpathTelemetry | None,
) -> None:
    _register_folder_route(app, to_item, hotpath_metrics=hotpath_metrics)

    @app.get("/item")
    def get_item(path: str, request: Request = None):
        storage = _storage_from_request(request)
        path = _canonical_path(path)
        _ensure_image(storage, path)
        return _build_sidecar(storage, path)

    @app.get("/metadata", response_model=ImageMetadataResponse)
    def get_metadata(path: str, request: Request = None):
        storage = _storage_from_request(request)
        path = _canonical_path(path)
        _ensure_image(storage, path)
        return _build_image_metadata(storage, path)

    @app.post("/export-comparison")
    async def export_comparison(request: Request):
        storage = _storage_from_request(request)
        try:
            payload = await request.json()
        except Exception:
            return _error_response(400, "invalid_json", "request body must be valid JSON")

        try:
            body = ExportComparisonRequest.model_validate(payload)
        except ValidationError as exc:
            return _error_response(400, "invalid_request", _first_validation_error_detail(exc))

        canonical_paths = [_canonical_path(path) for path in body.paths]
        for path in canonical_paths:
            try:
                _ensure_image(storage, path)
            except HTTPException as exc:
                return _path_validation_error_response(exc)

        try:
            normalized_labels = _normalize_export_labels(body.labels)
        except ValueError as exc:
            return _error_response(400, "invalid_labels", str(exc))

        ordered_paths, ordered_labels = _resolve_export_paths_and_labels(
            canonical_paths,
            normalized_labels,
            body.reverse_order,
        )

        images: list[Image.Image] = []
        source_formats: list[str] = []
        try:
            for path in ordered_paths:
                image, source_format = _load_export_image(storage, path)
                images.append(image)
                source_formats.append(source_format)
            exported_png = _build_export_png(
                images,
                ordered_labels,
                embed_metadata=body.embed_metadata,
                ordered_paths=ordered_paths,
                source_formats=source_formats,
                reversed_order=body.reverse_order,
            )
        except HTTPException as exc:
            return _comparison_export_error_response(exc)
        finally:
            for image in images:
                image.close()

        filename = _comparison_export_filename(body.reverse_order)
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return Response(content=exported_png, media_type="image/png", headers=headers)

    @app.put("/item")
    def put_item(path: str, body: Sidecar, request: Request = None):
        storage = _storage_from_request(request)
        path = _canonical_path(path)
        _ensure_image(storage, path)
        updated_by = _updated_by_from_request(request)
        with meta_lock:
            sidecar = _update_item(storage, path, body, updated_by)
            meta_snapshot = dict(storage.get_metadata(path))
        record_update(path, meta_snapshot)
        client_id = _client_id_from_request(request)
        if client_id:
            gallery_id = _gallery_id_from_path(path)
            _touch_presence_edit(presence, broker, gallery_id, client_id)
        return sidecar

    @app.patch("/item")
    def patch_item(path: str, body: SidecarPatch, request: Request = None):
        storage = _storage_from_request(request)
        path = _canonical_path(path)
        _ensure_image(storage, path)
        idem_key = request.headers.get("Idempotency-Key") if request else None
        if not idem_key:
            raise HTTPException(400, "Idempotency-Key header required")
        cached = idempotency_cache.get(idem_key)
        if cached:
            status, payload = cached
            return JSONResponse(status_code=status, content=payload)

        if_match = _parse_if_match(request.headers.get("If-Match") if request else None)
        if request and request.headers.get("If-Match") and if_match is None:
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
            meta = _ensure_meta_fields(meta)
            if expected is not None and expected != meta.get("version", 1):
                current = _sidecar_from_meta(meta).model_dump()
                payload = {"error": "version_conflict", "current": current}
                idempotency_cache.set(idem_key, 409, payload)
                return JSONResponse(status_code=409, content=payload)

            updated = _apply_patch_to_meta(meta, body)
            if updated:
                meta["version"] = meta.get("version", 1) + 1
                meta["updated_at"] = _now_iso()
                meta["updated_by"] = _updated_by_from_request(request)
                storage.set_metadata(path, meta)
            meta_snapshot = dict(meta)
        if updated:
            record_update(path, meta_snapshot)
            client_id = _client_id_from_request(request)
            if client_id:
                gallery_id = _gallery_id_from_path(path)
                _touch_presence_edit(presence, broker, gallery_id, client_id)
        sidecar = _sidecar_from_meta(meta_snapshot).model_dump()
        idempotency_cache.set(idem_key, 200, sidecar)
        return JSONResponse(status_code=200, content=sidecar)

    _register_presence_routes(
        app,
        presence,
        broker,
        lifecycle_v2_enabled=lifecycle_v2_enabled,
        metrics=presence_metrics,
    )

    @app.get("/events")
    async def events(request: Request):
        broker.ensure_loop()
        queue = broker.register()
        last_event_id = _last_event_id_from_request(request)

        async def event_stream():
            try:
                for record in broker.replay(last_event_id):
                    yield _format_sse(record)
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        record = await asyncio.wait_for(queue.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": ping\n\n"
                        continue
                    yield _format_sse(record)
            finally:
                broker.unregister(queue)

        response = StreamingResponse(event_stream(), media_type="text/event-stream")
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Connection"] = "keep-alive"
        return response

    @app.get("/thumb")
    async def get_thumb(path: str, request: Request = None):
        storage = _storage_from_request(request)
        path = _canonical_path(path)
        _ensure_image(storage, path)
        return await _thumb_response_async(
            storage,
            path,
            request,
            thumb_queue,
            thumb_cache,
            hotpath_metrics=hotpath_metrics,
        )

    @app.get("/file")
    def get_file(path: str, request: Request = None):
        storage = _storage_from_request(request)
        path = _canonical_path(path)
        _ensure_image(storage, path)
        return _file_response(storage, path, request=request, hotpath_metrics=hotpath_metrics)

    @app.get("/search", response_model=SearchResult)
    def search(request: Request = None, q: str = "", path: str = "/", limit: int = 100):
        storage = _storage_from_request(request)
        return _search_results(storage, to_item, q, _canonical_path(path), limit)

# --- App Factory ---

def create_app(
    root_path: str,
    thumb_size: int = 256,
    thumb_quality: int = 70,
    no_write: bool = False,
    source_column: str | None = None,
    skip_indexing: bool = False,
    thumb_cache: bool = True,
    og_preview: bool = False,
    embedding_config: EmbeddingConfig | None = None,
    embedding_cache: bool = True,
    embedding_cache_dir: str | None = None,
    embedding_preload: bool = False,
    presence_view_ttl: float = 75.0,
    presence_edit_ttl: float = 60.0,
    presence_prune_interval: float = 5.0,
    presence_lifecycle_v2: bool = True,
) -> FastAPI:
    """Create FastAPI app with in-memory storage."""

    app = FastAPI(
        title="Lenslet",
        description="Lightweight image gallery server",
    )

    # CORS for browser access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Create storage (prefer table dataset if present)
    items_path = Path(root_path) / "items.parquet"
    storage_mode = "memory"
    embedding_detection = EmbeddingDetection.empty()
    if items_path.is_file():
        columns = None
        try:
            schema = load_parquet_schema(str(items_path))
            embedding_detection = detect_embeddings(schema, embedding_config or EmbeddingConfig())
            columns = columns_without_embeddings(schema, embedding_detection)
        except Exception as exc:
            print(f"[lenslet] Warning: Failed to detect embeddings: {exc}")
        try:
            table = load_parquet_table(str(items_path), columns=columns)
            storage = TableStorage(
                table=table,
                root=root_path,
                thumb_size=thumb_size,
                thumb_quality=thumb_quality,
                source_column=source_column,
                skip_indexing=skip_indexing,
            )
            storage_mode = "table"
        except Exception as exc:
            print(f"[lenslet] Warning: Failed to load table dataset: {exc}")
            storage = MemoryStorage(
                root=root_path,
                thumb_size=thumb_size,
                thumb_quality=thumb_quality,
            )
            storage_mode = "memory"
    else:
        storage = MemoryStorage(
            root=root_path,
            thumb_size=thumb_size,
            thumb_quality=thumb_quality,
        )

    workspace = Workspace.for_dataset(root_path, can_write=not no_write)
    try:
        workspace.ensure()
    except Exception as exc:
        print(f"[lenslet] Warning: failed to initialize workspace: {exc}")
        workspace.can_write = False

    meta_lock = threading.Lock()
    log_lock = threading.Lock()
    broker, idempotency_cache, snapshotter, max_event_id = _init_sync_state(storage, workspace, meta_lock, log_lock)
    sync_state = {"last_event_id": max_event_id}
    presence = PresenceTracker(view_ttl=presence_view_ttl, edit_ttl=presence_edit_ttl)
    presence_metrics = _PresenceMetrics()
    app.state.sync_broker = broker
    app.state.presence_lifecycle_v2_enabled = presence_lifecycle_v2
    _install_presence_prune_loop(app, presence, broker, interval_seconds=presence_prune_interval)

    embedding_manager: EmbeddingManager | None = None
    if storage_mode == "table" and items_path.is_file() and isinstance(storage, TableStorage):
        embedding_cache_store = _embedding_cache_from_workspace(
            workspace,
            enabled=embedding_cache,
            cache_dir=embedding_cache_dir,
        )
        embedding_manager = _build_embedding_manager(
            str(items_path),
            storage,
            embedding_detection,
            cache=embedding_cache_store,
            preload=embedding_preload,
        )

    if hasattr(storage, "get_index"):
        def _warm_index() -> None:
            try:
                storage.get_index("/")  # type: ignore[call-arg]
            except Exception as exc:
                print(f"[lenslet] Warning: failed to build index: {exc}")
        threading.Thread(target=_warm_index, daemon=True).start()

    thumb_queue = ThumbnailScheduler(max_workers=_thumb_worker_count())
    thumb_cache_store = _thumb_cache_from_workspace(workspace, enabled=thumb_cache)
    hotpath_metrics = _create_hotpath_metrics(app)

    def _to_item(storage, cached) -> Item:
        meta = storage.get_metadata(cached.path)
        return _build_item(cached, meta)

    record_update = _build_record_update(
        storage,
        broker=broker,
        workspace=workspace,
        log_lock=log_lock,
        snapshotter=snapshotter,
        sync_state=sync_state,
    )

    # Inject storage via middleware
    _attach_storage(app, storage)

    # --- Routes ---

    @app.get("/health")
    def health():
        return {
            "ok": True,
            "mode": storage_mode,
            "root": root_path,
            "can_write": workspace.can_write,
            "labels": _labels_health_payload(workspace),
            "presence": _presence_runtime_payload(
                presence=presence,
                broker=broker,
                metrics=presence_metrics,
                lifecycle_v2_enabled=presence_lifecycle_v2,
                prune_interval_seconds=float(getattr(app.state, "presence_prune_interval", presence_prune_interval)),
            ),
            "hotpath": hotpath_metrics.snapshot(storage),
        }

    @app.post("/refresh")
    def refresh(path: str = "/", request: Request = None):
        if storage_mode != "memory":
            return {"ok": True, "note": f"{storage_mode} mode is static"}

        storage = _storage_from_request(request)
        path = _canonical_path(path)
        try:
            target = storage._abs_path(path)
        except ValueError:
            raise HTTPException(400, "invalid path")

        if not os.path.isdir(target):
            raise HTTPException(404, "folder not found")

        storage.invalidate_subtree(path)
        return {"ok": True}

    _register_common_api_routes(
        app,
        _to_item,
        meta_lock=meta_lock,
        presence=presence,
        broker=broker,
        lifecycle_v2_enabled=presence_lifecycle_v2,
        presence_metrics=presence_metrics,
        idempotency_cache=idempotency_cache,
        record_update=record_update,
        thumb_queue=thumb_queue,
        thumb_cache=thumb_cache_store,
        hotpath_metrics=hotpath_metrics,
    )

    _register_embedding_routes(app, storage, embedding_manager)
    _register_og_routes(app, storage, workspace, enabled=og_preview)
    _register_index_routes(app, storage, workspace, og_preview=og_preview)
    _register_views_routes(app, workspace)

    # Mount frontend if dist exists
    _mount_frontend(app)

    return app


def create_app_from_datasets(
    datasets: dict[str, list[str]],
    thumb_size: int = 256,
    thumb_quality: int = 70,
    show_source: bool = True,
    thumb_cache: bool = True,
    og_preview: bool = False,
    embedding_parquet_path: str | None = None,
    embedding_config: EmbeddingConfig | None = None,
    embedding_cache: bool = True,
    embedding_cache_dir: str | None = None,
    embedding_preload: bool = False,
    presence_view_ttl: float = 75.0,
    presence_edit_ttl: float = 60.0,
    presence_prune_interval: float = 5.0,
    presence_lifecycle_v2: bool = True,
) -> FastAPI:
    """Create FastAPI app with in-memory dataset storage."""

    app = FastAPI(
        title="Lenslet",
        description="Lightweight image gallery server (dataset mode)",
    )

    # CORS for browser access
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Create dataset storage
    storage = DatasetStorage(
        datasets=datasets,
        thumb_size=thumb_size,
        thumb_quality=thumb_quality,
        include_source_in_search=show_source,
    )
    workspace = Workspace.for_dataset(None, can_write=False)
    meta_lock = threading.Lock()
    log_lock = threading.Lock()
    broker, idempotency_cache, snapshotter, max_event_id = _init_sync_state(storage, workspace, meta_lock, log_lock)
    sync_state = {"last_event_id": max_event_id}
    presence = PresenceTracker(view_ttl=presence_view_ttl, edit_ttl=presence_edit_ttl)
    presence_metrics = _PresenceMetrics()
    app.state.sync_broker = broker
    app.state.presence_lifecycle_v2_enabled = presence_lifecycle_v2
    _install_presence_prune_loop(app, presence, broker, interval_seconds=presence_prune_interval)
    thumb_queue = ThumbnailScheduler(max_workers=_thumb_worker_count())
    thumb_cache_store = _thumb_cache_from_workspace(workspace, enabled=thumb_cache)
    hotpath_metrics = _create_hotpath_metrics(app)
    embedding_manager: EmbeddingManager | None = None
    if embedding_parquet_path and isinstance(storage, TableStorage):
        detection = _resolve_embedding_detection(embedding_parquet_path, embedding_config)
        embed_cache = _embedding_cache_from_workspace(
            workspace,
            enabled=embedding_cache,
            cache_dir=embedding_cache_dir,
        )
        embedding_manager = _build_embedding_manager(
            embedding_parquet_path,
            storage,
            detection,
            cache=embed_cache,
            preload=embedding_preload,
        )

    def _to_item(storage: DatasetStorage, cached) -> Item:
        meta = storage.get_metadata(cached.path)
        source = None
        if show_source:
            try:
                source = storage.get_source_path(cached.path)
            except Exception:
                source = None
        return _build_item(cached, meta, source=source)

    record_update = _build_record_update(
        storage,
        broker=broker,
        workspace=workspace,
        log_lock=log_lock,
        snapshotter=snapshotter,
        sync_state=sync_state,
    )

    # Inject storage via middleware
    _attach_storage(app, storage)

    # --- Routes ---

    @app.get("/health")
    def health():
        dataset_names = list(datasets.keys())
        total_images = sum(len(paths) for paths in datasets.values())
        return {
            "ok": True,
            "mode": "dataset",
            "datasets": dataset_names,
            "total_images": total_images,
            "can_write": workspace.can_write,
            "labels": _labels_health_payload(workspace),
            "presence": _presence_runtime_payload(
                presence=presence,
                broker=broker,
                metrics=presence_metrics,
                lifecycle_v2_enabled=presence_lifecycle_v2,
                prune_interval_seconds=float(getattr(app.state, "presence_prune_interval", presence_prune_interval)),
            ),
            "hotpath": hotpath_metrics.snapshot(storage),
        }

    @app.post("/refresh")
    def refresh(path: str = "/", request: Request = None):
        # Dataset mode is static for now, but keep API parity with memory mode
        _ = path
        return {"ok": True, "note": "dataset mode is static"}

    _register_common_api_routes(
        app,
        _to_item,
        meta_lock=meta_lock,
        presence=presence,
        broker=broker,
        lifecycle_v2_enabled=presence_lifecycle_v2,
        presence_metrics=presence_metrics,
        idempotency_cache=idempotency_cache,
        record_update=record_update,
        thumb_queue=thumb_queue,
        thumb_cache=thumb_cache_store,
        hotpath_metrics=hotpath_metrics,
    )

    _register_embedding_routes(app, storage, embedding_manager)
    _register_views_routes(app, workspace)

    # Mount frontend if dist exists
    _mount_frontend(app)

    return app


def create_app_from_table(
    table: object,
    base_dir: str | None = None,
    thumb_size: int = 256,
    thumb_quality: int = 70,
    source_column: str | None = None,
    skip_indexing: bool = False,
    show_source: bool = True,
    allow_local: bool = True,
    og_preview: bool = False,
    workspace: Workspace | None = None,
    thumb_cache: bool = True,
    embedding_parquet_path: str | None = None,
    embedding_config: EmbeddingConfig | None = None,
    embedding_cache: bool = True,
    embedding_cache_dir: str | None = None,
    embedding_preload: bool = False,
    presence_view_ttl: float = 75.0,
    presence_edit_ttl: float = 60.0,
    presence_prune_interval: float = 5.0,
    presence_lifecycle_v2: bool = True,
) -> FastAPI:
    """Create FastAPI app with in-memory table storage."""
    storage = TableStorage(
        table=table,
        root=base_dir,
        thumb_size=thumb_size,
        thumb_quality=thumb_quality,
        source_column=source_column,
        skip_indexing=skip_indexing,
        allow_local=allow_local,
    )
    return create_app_from_storage(
        storage,
        show_source=show_source,
        og_preview=og_preview,
        workspace=workspace,
        thumb_cache=thumb_cache,
        embedding_parquet_path=embedding_parquet_path,
        embedding_config=embedding_config,
        embedding_cache=embedding_cache,
        embedding_cache_dir=embedding_cache_dir,
        embedding_preload=embedding_preload,
        presence_view_ttl=presence_view_ttl,
        presence_edit_ttl=presence_edit_ttl,
        presence_prune_interval=presence_prune_interval,
        presence_lifecycle_v2=presence_lifecycle_v2,
    )


def create_app_from_storage(
    storage: TableStorage,
    show_source: bool = True,
    og_preview: bool = False,
    workspace: Workspace | None = None,
    thumb_cache: bool = True,
    embedding_parquet_path: str | None = None,
    embedding_config: EmbeddingConfig | None = None,
    embedding_cache: bool = True,
    embedding_cache_dir: str | None = None,
    embedding_preload: bool = False,
    presence_view_ttl: float = 75.0,
    presence_edit_ttl: float = 60.0,
    presence_prune_interval: float = 5.0,
    presence_lifecycle_v2: bool = True,
) -> FastAPI:
    """Create FastAPI app using a pre-built TableStorage."""

    app = FastAPI(
        title="Lenslet",
        description="Lightweight image gallery server (table mode)",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if workspace is None:
        workspace = Workspace.for_dataset(None, can_write=False)
    meta_lock = threading.Lock()
    log_lock = threading.Lock()
    broker, idempotency_cache, snapshotter, max_event_id = _init_sync_state(storage, workspace, meta_lock, log_lock)
    sync_state = {"last_event_id": max_event_id}
    presence = PresenceTracker(view_ttl=presence_view_ttl, edit_ttl=presence_edit_ttl)
    presence_metrics = _PresenceMetrics()
    app.state.sync_broker = broker
    app.state.presence_lifecycle_v2_enabled = presence_lifecycle_v2
    _install_presence_prune_loop(app, presence, broker, interval_seconds=presence_prune_interval)
    thumb_queue = ThumbnailScheduler(max_workers=_thumb_worker_count())
    thumb_cache_store = _thumb_cache_from_workspace(workspace, enabled=thumb_cache)
    hotpath_metrics = _create_hotpath_metrics(app)
    embedding_manager: EmbeddingManager | None = None
    if embedding_parquet_path:
        detection = _resolve_embedding_detection(embedding_parquet_path, embedding_config)
        embed_cache = _embedding_cache_from_workspace(
            workspace,
            enabled=embedding_cache,
            cache_dir=embedding_cache_dir,
        )
        embedding_manager = _build_embedding_manager(
            embedding_parquet_path,
            storage,
            detection,
            cache=embed_cache,
            preload=embedding_preload,
        )

    def _to_item(storage: TableStorage, cached) -> Item:
        meta = storage.get_metadata(cached.path)
        source = cached.source if show_source else None
        return _build_item(cached, meta, source=source)

    record_update = _build_record_update(
        storage,
        broker=broker,
        workspace=workspace,
        log_lock=log_lock,
        snapshotter=snapshotter,
        sync_state=sync_state,
    )

    _attach_storage(app, storage)

    @app.get("/health")
    def health():
        return {
            "ok": True,
            "mode": "table",
            "total_images": len(storage._items),
            "can_write": workspace.can_write,
            "labels": _labels_health_payload(workspace),
            "presence": _presence_runtime_payload(
                presence=presence,
                broker=broker,
                metrics=presence_metrics,
                lifecycle_v2_enabled=presence_lifecycle_v2,
                prune_interval_seconds=float(getattr(app.state, "presence_prune_interval", presence_prune_interval)),
            ),
            "hotpath": hotpath_metrics.snapshot(storage),
        }

    @app.post("/refresh")
    def refresh(path: str = "/", request: Request = None):
        _ = path
        return {"ok": True, "note": "table mode is static"}

    _register_common_api_routes(
        app,
        _to_item,
        meta_lock=meta_lock,
        presence=presence,
        broker=broker,
        lifecycle_v2_enabled=presence_lifecycle_v2,
        presence_metrics=presence_metrics,
        idempotency_cache=idempotency_cache,
        record_update=record_update,
        thumb_queue=thumb_queue,
        thumb_cache=thumb_cache_store,
        hotpath_metrics=hotpath_metrics,
    )

    _register_embedding_routes(app, storage, embedding_manager)
    _register_og_routes(app, storage, workspace, enabled=og_preview)
    _register_index_routes(app, storage, workspace, og_preview=og_preview)
    _register_views_routes(app, workspace)
    _mount_frontend(app)

    return app


def _thumb_cache_from_workspace(workspace: Workspace, enabled: bool) -> ThumbCache | None:
    if not enabled or not workspace.can_write:
        return None
    cache_dir = workspace.thumb_cache_dir()
    if cache_dir is None:
        return None
    return ThumbCache(cache_dir)


def _embedding_cache_from_workspace(
    workspace: Workspace,
    enabled: bool,
    cache_dir: str | None,
) -> EmbeddingCache | None:
    if not enabled or not workspace.can_write:
        return None
    if cache_dir:
        root = Path(cache_dir).expanduser()
        if root.name != "embeddings_cache":
            root = root / "embeddings_cache"
        return EmbeddingCache(root, allow_write=workspace.can_write)
    root = workspace.embedding_cache_dir()
    if root is None:
        return None
    return EmbeddingCache(root, allow_write=workspace.can_write)
