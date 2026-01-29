"""FastAPI server for Lenslet."""
from __future__ import annotations
import asyncio
import io
import os
import threading
import html
import math
from urllib.parse import urlparse
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
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
    EmbeddingRejectedPayload,
    EmbeddingSearchItem,
    EmbeddingSearchRequest,
    EmbeddingSearchResponse,
    EmbeddingSpecPayload,
    EmbeddingsResponse,
    FolderIndex,
    ImageMetadataResponse,
    Item,
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


def _build_folder_index(storage, path: str, to_item) -> FolderIndex:
    try:
        index = storage.get_index(path)
    except ValueError:
        raise HTTPException(400, "invalid path")
    except FileNotFoundError:
        raise HTTPException(404, "folder not found")

    items = [to_item(storage, it) for it in index.items]
    dirs = [DirEntry(name=d, kind="branch") for d in index.dirs]

    return FolderIndex(
        path=_canonical_path(path),
        generatedAt=index.generated_at,
        items=items,
        dirs=dirs,
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
        return Response(status_code=204)

    if thumb is None:
        raise HTTPException(500, "failed to generate thumbnail")
    if thumb_cache is not None and cache_key:
        thumb_cache.set(cache_key, thumb)
    return Response(content=thumb, media_type="image/webp")


def _file_response(storage, path: str) -> Response:
    data = storage.read_bytes(path)
    return Response(content=data, media_type=storage._guess_mime(path))


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


def _register_index_routes(app: FastAPI, storage, workspace: Workspace, og_preview: bool) -> None:
    frontend_dist = Path(__file__).parent / "frontend"
    index_path = frontend_dist / "index.html"
    if not index_path.is_file():
        return

    def render_index(request: Request):
        html_text = index_path.read_text(encoding="utf-8")
        if og_preview:
            label = _dataset_label(workspace)
            title = f"Lenslet: {label}"
            scope_path = og.normalize_path(request.query_params.get("path"))
            scope_count = og.subtree_image_count(storage, scope_path)
            root_count = og.subtree_image_count(storage, "/")
            if scope_count is None:
                scope_count = _dataset_count(storage)
            if root_count is None:
                root_count = scope_count
            if scope_count is not None:
                if scope_path != "/" and root_count is not None:
                    title = f"{title} ({scope_count:,}/{root_count:,} images)"
                else:
                    title = f"{title} ({scope_count:,} images)"
            description = f"Browse {label} gallery"
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
    presence = PresenceTracker()
    app.state.sync_broker = broker

    embedding_manager: EmbeddingManager | None = None
    if storage_mode == "table" and items_path.is_file() and isinstance(storage, TableStorage):
        cache = _embedding_cache_from_workspace(
            workspace,
            enabled=embedding_cache,
            cache_dir=embedding_cache_dir,
        )
        embedding_manager = _build_embedding_manager(
            str(items_path),
            storage,
            embedding_detection,
            cache=cache,
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
    cache = _thumb_cache_from_workspace(workspace, enabled=thumb_cache)

    def _to_item(storage, cached) -> Item:
        meta = storage.get_metadata(cached.path)
        return _build_item(cached, meta)

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
            "labels": {
                "enabled": workspace.can_write,
                "log": str(workspace.labels_log_path()) if workspace.can_write else None,
                "snapshot": str(workspace.labels_snapshot_path()) if workspace.can_write else None,
            },
        }

    @app.get("/folders", response_model=FolderIndex)
    def get_folder(path: str = "/", request: Request = None):
        storage = _storage_from_request(request)
        return _build_folder_index(storage, _canonical_path(path), _to_item)

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

    @app.put("/item")
    def put_item(path: str, body: Sidecar, request: Request = None):
        storage = _storage_from_request(request)
        path = _canonical_path(path)
        _ensure_image(storage, path)
        updated_by = _updated_by_from_request(request)
        with meta_lock:
            sidecar = _update_item(storage, path, body, updated_by)
            meta_snapshot = dict(storage.get_metadata(path))
        _record_update(path, meta_snapshot)
        client_id = _client_id_from_request(request)
        if client_id:
            gallery_id = _gallery_id_from_path(path)
            viewing, editing = presence.touch_edit(gallery_id, client_id)
            broker.publish("presence", {"gallery_id": gallery_id, "viewing": viewing, "editing": editing})
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
            _record_update(path, meta_snapshot)
            client_id = _client_id_from_request(request)
            if client_id:
                gallery_id = _gallery_id_from_path(path)
                viewing, editing = presence.touch_edit(gallery_id, client_id)
                broker.publish("presence", {"gallery_id": gallery_id, "viewing": viewing, "editing": editing})
        sidecar = _sidecar_from_meta(meta_snapshot).model_dump()
        idempotency_cache.set(idem_key, 200, sidecar)
        return JSONResponse(status_code=200, content=sidecar)

    @app.post("/presence")
    def presence_heartbeat(body: PresencePayload):
        gallery_id = _canonical_path(body.gallery_id)
        if not body.client_id:
            raise HTTPException(400, "client_id required")
        viewing, editing = presence.touch_view(gallery_id, body.client_id)
        payload = {"gallery_id": gallery_id, "viewing": viewing, "editing": editing}
        broker.publish("presence", payload)
        return payload

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
        return await _thumb_response_async(storage, path, request, thumb_queue, cache)

    @app.get("/file")
    def get_file(path: str, request: Request = None):
        storage = _storage_from_request(request)
        path = _canonical_path(path)
        _ensure_image(storage, path)
        return _file_response(storage, path)

    @app.get("/search", response_model=SearchResult)
    def search(request: Request = None, q: str = "", path: str = "/", limit: int = 100):
        storage = _storage_from_request(request)
        return _search_results(storage, _to_item, q, _canonical_path(path), limit)

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
    presence = PresenceTracker()
    app.state.sync_broker = broker
    thumb_queue = ThumbnailScheduler(max_workers=_thumb_worker_count())
    cache = _thumb_cache_from_workspace(workspace, enabled=thumb_cache)
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
            "labels": {
                "enabled": workspace.can_write,
                "log": str(workspace.labels_log_path()) if workspace.can_write else None,
                "snapshot": str(workspace.labels_snapshot_path()) if workspace.can_write else None,
            },
        }

    @app.get("/folders", response_model=FolderIndex)
    def get_folder(path: str = "/", request: Request = None):
        storage = _storage_from_request(request)
        return _build_folder_index(storage, _canonical_path(path), _to_item)

    @app.post("/refresh")
    def refresh(path: str = "/", request: Request = None):
        # Dataset mode is static for now, but keep API parity with memory mode
        _ = path
        return {"ok": True, "note": "dataset mode is static"}

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

    @app.put("/item")
    def put_item(path: str, body: Sidecar, request: Request = None):
        storage = _storage_from_request(request)
        path = _canonical_path(path)
        _ensure_image(storage, path)
        updated_by = _updated_by_from_request(request)
        with meta_lock:
            sidecar = _update_item(storage, path, body, updated_by)
            meta_snapshot = dict(storage.get_metadata(path))
        _record_update(path, meta_snapshot)
        client_id = _client_id_from_request(request)
        if client_id:
            gallery_id = _gallery_id_from_path(path)
            viewing, editing = presence.touch_edit(gallery_id, client_id)
            broker.publish("presence", {"gallery_id": gallery_id, "viewing": viewing, "editing": editing})
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
            _record_update(path, meta_snapshot)
            client_id = _client_id_from_request(request)
            if client_id:
                gallery_id = _gallery_id_from_path(path)
                viewing, editing = presence.touch_edit(gallery_id, client_id)
                broker.publish("presence", {"gallery_id": gallery_id, "viewing": viewing, "editing": editing})
        sidecar = _sidecar_from_meta(meta_snapshot).model_dump()
        idempotency_cache.set(idem_key, 200, sidecar)
        return JSONResponse(status_code=200, content=sidecar)

    @app.post("/presence")
    def presence_heartbeat(body: PresencePayload):
        gallery_id = _canonical_path(body.gallery_id)
        if not body.client_id:
            raise HTTPException(400, "client_id required")
        viewing, editing = presence.touch_view(gallery_id, body.client_id)
        payload = {"gallery_id": gallery_id, "viewing": viewing, "editing": editing}
        broker.publish("presence", payload)
        return payload

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
        return await _thumb_response_async(storage, path, request, thumb_queue, cache)

    @app.get("/file")
    def get_file(path: str, request: Request = None):
        storage = _storage_from_request(request)
        path = _canonical_path(path)
        _ensure_image(storage, path)
        return _file_response(storage, path)

    @app.get("/search", response_model=SearchResult)
    def search(request: Request = None, q: str = "", path: str = "/", limit: int = 100):
        storage = _storage_from_request(request)
        return _search_results(storage, _to_item, q, _canonical_path(path), limit)

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
    og_preview: bool = False,
    workspace: Workspace | None = None,
    thumb_cache: bool = True,
    embedding_parquet_path: str | None = None,
    embedding_config: EmbeddingConfig | None = None,
    embedding_cache: bool = True,
    embedding_cache_dir: str | None = None,
    embedding_preload: bool = False,
) -> FastAPI:
    """Create FastAPI app with in-memory table storage."""
    storage = TableStorage(
        table=table,
        root=base_dir,
        thumb_size=thumb_size,
        thumb_quality=thumb_quality,
        source_column=source_column,
        skip_indexing=skip_indexing,
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
    presence = PresenceTracker()
    app.state.sync_broker = broker
    thumb_queue = ThumbnailScheduler(max_workers=_thumb_worker_count())
    cache = _thumb_cache_from_workspace(workspace, enabled=thumb_cache)
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

    _attach_storage(app, storage)

    @app.get("/health")
    def health():
        return {
            "ok": True,
            "mode": "table",
            "total_images": len(storage._items),
            "can_write": workspace.can_write,
            "labels": {
                "enabled": workspace.can_write,
                "log": str(workspace.labels_log_path()) if workspace.can_write else None,
                "snapshot": str(workspace.labels_snapshot_path()) if workspace.can_write else None,
            },
        }

    @app.get("/folders", response_model=FolderIndex)
    def get_folder(path: str = "/", request: Request = None):
        storage = _storage_from_request(request)
        return _build_folder_index(storage, _canonical_path(path), _to_item)

    @app.post("/refresh")
    def refresh(path: str = "/", request: Request = None):
        _ = path
        return {"ok": True, "note": "table mode is static"}

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

    @app.put("/item")
    def put_item(path: str, body: Sidecar, request: Request = None):
        storage = _storage_from_request(request)
        path = _canonical_path(path)
        _ensure_image(storage, path)
        updated_by = _updated_by_from_request(request)
        with meta_lock:
            sidecar = _update_item(storage, path, body, updated_by)
            meta_snapshot = dict(storage.get_metadata(path))
        _record_update(path, meta_snapshot)
        client_id = _client_id_from_request(request)
        if client_id:
            gallery_id = _gallery_id_from_path(path)
            viewing, editing = presence.touch_edit(gallery_id, client_id)
            broker.publish("presence", {"gallery_id": gallery_id, "viewing": viewing, "editing": editing})
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
            _record_update(path, meta_snapshot)
            client_id = _client_id_from_request(request)
            if client_id:
                gallery_id = _gallery_id_from_path(path)
                viewing, editing = presence.touch_edit(gallery_id, client_id)
                broker.publish("presence", {"gallery_id": gallery_id, "viewing": viewing, "editing": editing})
        sidecar = _sidecar_from_meta(meta_snapshot).model_dump()
        idempotency_cache.set(idem_key, 200, sidecar)
        return JSONResponse(status_code=200, content=sidecar)

    @app.post("/presence")
    def presence_heartbeat(body: PresencePayload):
        gallery_id = _canonical_path(body.gallery_id)
        if not body.client_id:
            raise HTTPException(400, "client_id required")
        viewing, editing = presence.touch_view(gallery_id, body.client_id)
        payload = {"gallery_id": gallery_id, "viewing": viewing, "editing": editing}
        broker.publish("presence", payload)
        return payload

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
        return await _thumb_response_async(storage, path, request, thumb_queue, cache)

    @app.get("/file")
    def get_file(path: str, request: Request = None):
        storage = _storage_from_request(request)
        path = _canonical_path(path)
        _ensure_image(storage, path)
        return _file_response(storage, path)

    @app.get("/search", response_model=SearchResult)
    def search(request: Request = None, q: str = "", path: str = "/", limit: int = 100):
        storage = _storage_from_request(request)
        return _search_results(storage, _to_item, q, _canonical_path(path), limit)

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
