"""FastAPI server for Lenslet."""
from __future__ import annotations
import asyncio
import io
import os
import threading
import html
from urllib.parse import urlparse
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal
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
from .storage.memory import MemoryStorage
from .storage.dataset import DatasetStorage
from .storage.table import TableStorage, load_parquet_table
from .thumbs import ThumbnailScheduler
from .thumb_cache import ThumbCache
from .og_cache import OgImageCache
from .workspace import Workspace


# --- Models ---

Mime = Literal["image/webp", "image/jpeg", "image/png"]



class Item(BaseModel):
    path: str
    name: str
    type: Mime
    w: int
    h: int
    size: int
    hasThumb: bool = True  # Always true in memory mode
    hasMeta: bool = True   # Always true in memory mode
    hash: str | None = None
    addedAt: str | None = None
    star: int | None = None
    comments: str | None = None
    url: str | None = None
    source: str | None = None
    metrics: dict[str, float] | None = None


class DirEntry(BaseModel):
    name: str
    kind: Literal["branch", "leaf-real", "leaf-pointer"] = "branch"


class FolderIndex(BaseModel):
    v: int = 1
    path: str
    generatedAt: str
    items: list[Item] = Field(default_factory=list)
    dirs: list[DirEntry] = Field(default_factory=list)
    page: int | None = None
    pageCount: int | None = None


class Sidecar(BaseModel):
    v: int = 1
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    exif: dict | None = None
    hash: str | None = None
    original_position: str | None = None
    star: int | None = None
    updated_at: str = ""
    updated_by: str = "server"


class SearchResult(BaseModel):
    items: list[Item]


class ImageMetadataResponse(BaseModel):
    path: str
    format: Literal["png", "jpeg", "webp"]
    meta: dict


class ViewsPayload(BaseModel):
    version: int = 1
    views: list[dict] = Field(default_factory=list)


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
    return Sidecar(
        tags=meta.get("tags", []),
        notes=meta.get("notes", ""),
        exif={"width": meta.get("width", 0), "height": meta.get("height", 0)},
        star=meta.get("star"),
        updated_at=datetime.now(timezone.utc).isoformat(),
        updated_by="server",
    )


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
    return Item(
        path=cached.path,
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
        metrics=getattr(cached, "metrics", None),
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
        path=path,
        generatedAt=index.generated_at,
        items=items,
        dirs=dirs,
    )


def _update_item(storage, path: str, body: Sidecar) -> Sidecar:
    meta = storage.get_metadata(path)
    meta["tags"] = body.tags
    meta["notes"] = body.notes
    meta["star"] = body.star
    storage.set_metadata(path, meta)
    return body


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
    if items_path.is_file():
        try:
            table = load_parquet_table(str(items_path))
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
        }

    @app.get("/folders", response_model=FolderIndex)
    def get_folder(path: str = "/", request: Request = None):
        storage = _storage_from_request(request)
        return _build_folder_index(storage, path, _to_item)

    @app.post("/refresh")
    def refresh(path: str = "/", request: Request = None):
        if storage_mode != "memory":
            return {"ok": True, "note": f"{storage_mode} mode is static"}

        storage = _storage_from_request(request)
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
        _ensure_image(storage, path)
        return _build_sidecar(storage, path)

    @app.get("/metadata", response_model=ImageMetadataResponse)
    def get_metadata(path: str, request: Request = None):
        storage = _storage_from_request(request)
        _ensure_image(storage, path)
        return _build_image_metadata(storage, path)

    @app.put("/item")
    def put_item(path: str, body: Sidecar, request: Request = None):
        storage = _storage_from_request(request)
        _ensure_image(storage, path)
        return _update_item(storage, path, body)

    @app.get("/thumb")
    async def get_thumb(path: str, request: Request = None):
        storage = _storage_from_request(request)
        _ensure_image(storage, path)
        return await _thumb_response_async(storage, path, request, thumb_queue, cache)

    @app.get("/file")
    def get_file(path: str, request: Request = None):
        storage = _storage_from_request(request)
        _ensure_image(storage, path)
        return _file_response(storage, path)

    @app.get("/search", response_model=SearchResult)
    def search(request: Request = None, q: str = "", path: str = "/", limit: int = 100):
        storage = _storage_from_request(request)
        return _search_results(storage, _to_item, q, path, limit)

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
    thumb_queue = ThumbnailScheduler(max_workers=_thumb_worker_count())
    cache = _thumb_cache_from_workspace(workspace, enabled=thumb_cache)

    def _to_item(storage: DatasetStorage, cached) -> Item:
        meta = storage.get_metadata(cached.path)
        source = None
        if show_source:
            try:
                source = storage.get_source_path(cached.path)
            except Exception:
                source = None
        return _build_item(cached, meta, source=source)

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
        }

    @app.get("/folders", response_model=FolderIndex)
    def get_folder(path: str = "/", request: Request = None):
        storage = _storage_from_request(request)
        return _build_folder_index(storage, path, _to_item)

    @app.post("/refresh")
    def refresh(path: str = "/", request: Request = None):
        # Dataset mode is static for now, but keep API parity with memory mode
        _ = path
        return {"ok": True, "note": "dataset mode is static"}

    @app.get("/item")
    def get_item(path: str, request: Request = None):
        storage = _storage_from_request(request)
        _ensure_image(storage, path)
        return _build_sidecar(storage, path)

    @app.get("/metadata", response_model=ImageMetadataResponse)
    def get_metadata(path: str, request: Request = None):
        storage = _storage_from_request(request)
        _ensure_image(storage, path)
        return _build_image_metadata(storage, path)

    @app.put("/item")
    def put_item(path: str, body: Sidecar, request: Request = None):
        storage = _storage_from_request(request)
        _ensure_image(storage, path)
        return _update_item(storage, path, body)

    @app.get("/thumb")
    async def get_thumb(path: str, request: Request = None):
        storage = _storage_from_request(request)
        _ensure_image(storage, path)
        return await _thumb_response_async(storage, path, request, thumb_queue, cache)

    @app.get("/file")
    def get_file(path: str, request: Request = None):
        storage = _storage_from_request(request)
        _ensure_image(storage, path)
        return _file_response(storage, path)

    @app.get("/search", response_model=SearchResult)
    def search(request: Request = None, q: str = "", path: str = "/", limit: int = 100):
        storage = _storage_from_request(request)
        return _search_results(storage, _to_item, q, path, limit)

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
    )


def create_app_from_storage(
    storage: TableStorage,
    show_source: bool = True,
    og_preview: bool = False,
    workspace: Workspace | None = None,
    thumb_cache: bool = True,
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
    thumb_queue = ThumbnailScheduler(max_workers=_thumb_worker_count())
    cache = _thumb_cache_from_workspace(workspace, enabled=thumb_cache)

    def _to_item(storage: TableStorage, cached) -> Item:
        meta = storage.get_metadata(cached.path)
        source = cached.source if show_source else None
        return _build_item(cached, meta, source=source)

    _attach_storage(app, storage)

    @app.get("/health")
    def health():
        return {
            "ok": True,
            "mode": "table",
            "total_images": len(storage._items),
            "can_write": workspace.can_write,
        }

    @app.get("/folders", response_model=FolderIndex)
    def get_folder(path: str = "/", request: Request = None):
        storage = _storage_from_request(request)
        return _build_folder_index(storage, path, _to_item)

    @app.post("/refresh")
    def refresh(path: str = "/", request: Request = None):
        _ = path
        return {"ok": True, "note": "table mode is static"}

    @app.get("/item")
    def get_item(path: str, request: Request = None):
        storage = _storage_from_request(request)
        _ensure_image(storage, path)
        return _build_sidecar(storage, path)

    @app.get("/metadata", response_model=ImageMetadataResponse)
    def get_metadata(path: str, request: Request = None):
        storage = _storage_from_request(request)
        _ensure_image(storage, path)
        return _build_image_metadata(storage, path)

    @app.put("/item")
    def put_item(path: str, body: Sidecar, request: Request = None):
        storage = _storage_from_request(request)
        _ensure_image(storage, path)
        return _update_item(storage, path, body)

    @app.get("/thumb")
    async def get_thumb(path: str, request: Request = None):
        storage = _storage_from_request(request)
        _ensure_image(storage, path)
        return await _thumb_response_async(storage, path, request, thumb_queue, cache)

    @app.get("/file")
    def get_file(path: str, request: Request = None):
        storage = _storage_from_request(request)
        _ensure_image(storage, path)
        return _file_response(storage, path)

    @app.get("/search", response_model=SearchResult)
    def search(request: Request = None, q: str = "", path: str = "/", limit: int = 100):
        storage = _storage_from_request(request)
        return _search_results(storage, _to_item, q, path, limit)

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
