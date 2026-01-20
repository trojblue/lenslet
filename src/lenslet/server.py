"""FastAPI server for Lenslet."""
from __future__ import annotations
import asyncio
import io
import os
import threading
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal


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


async def _thumb_response_async(
    storage,
    path: str,
    request: Request,
    queue: ThumbnailScheduler,
) -> Response:
    cached = _get_cached_thumbnail(storage, path)
    if cached is not None:
        return Response(content=cached, media_type="image/webp")

    future = queue.submit(path, lambda: storage.get_thumbnail(path))
    try:
        thumb = await _await_thumbnail(request, future)
    except _ClientDisconnected:
        return Response(status_code=204)

    if thumb is None:
        raise HTTPException(500, "failed to generate thumbnail")
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
        return await _thumb_response_async(storage, path, request, thumb_queue)

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


def create_app_from_datasets(
    datasets: dict[str, list[str]],
    thumb_size: int = 256,
    thumb_quality: int = 70,
    show_source: bool = True,
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
        return await _thumb_response_async(storage, path, request, thumb_queue)

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
    workspace: Workspace | None = None,
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
    return create_app_from_storage(storage, show_source=show_source, workspace=workspace)


def create_app_from_storage(
    storage: TableStorage,
    show_source: bool = True,
    workspace: Workspace | None = None,
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
        return await _thumb_response_async(storage, path, request, thumb_queue)

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
    _mount_frontend(app)

    return app
