"""FastAPI server for Lenslet."""
from __future__ import annotations
import io
import os
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

from .metadata import read_png_info
from .storage.memory import MemoryStorage
from .storage.dataset import DatasetStorage
from .storage.parquet import ParquetStorage
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
    format: Literal["png"]
    meta: dict


class ViewsPayload(BaseModel):
    version: int = 1
    views: list[dict] = Field(default_factory=list)


# --- App Factory ---

def create_app(
    root_path: str,
    thumb_size: int = 256,
    thumb_quality: int = 70,
    no_write: bool = False,
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

    # Create storage (prefer Parquet dataset if present)
    items_path = Path(root_path) / "items.parquet"
    storage_mode = "memory"
    if items_path.is_file():
        try:
            storage = ParquetStorage(
                root=root_path,
                thumb_size=thumb_size,
                thumb_quality=thumb_quality,
            )
            storage_mode = "parquet"
        except Exception as exc:
            print(f"[lenslet] Warning: Failed to load Parquet dataset: {exc}")
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

    def _storage(request: Request):
        return request.state.storage  # type: ignore[attr-defined]

    def _ensure_image(storage, path: str) -> None:
        try:
            storage.validate_image_path(path)
        except FileNotFoundError:
            raise HTTPException(404, "file not found")
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    def _to_item(storage, cached) -> Item:
        meta = storage.get_metadata(cached.path)
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
            metrics=getattr(cached, "metrics", None),
        )

    # Inject storage via middleware
    @app.middleware("http")
    async def attach_storage(request: Request, call_next):
        request.state.storage = storage
        response = await call_next(request)
        return response

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
        storage = _storage(request)
        try:
            index = storage.get_index(path)
        except ValueError:
            raise HTTPException(400, "invalid path")
        except FileNotFoundError:
            raise HTTPException(404, "folder not found")

        items = [_to_item(storage, it) for it in index.items]
        dirs = [DirEntry(name=d, kind="branch") for d in index.dirs]

        return FolderIndex(
            path=path,
            generatedAt=index.generated_at,
            items=items,
            dirs=dirs,
        )

    @app.post("/refresh")
    def refresh(path: str = "/", request: Request = None):
        if storage_mode != "memory":
            return {"ok": True, "note": f"{storage_mode} mode is static"}

        storage = _storage(request)
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
        storage = _storage(request)
        _ensure_image(storage, path)

        meta = storage.get_metadata(path)
        return Sidecar(
            tags=meta.get("tags", []),
            notes=meta.get("notes", ""),
            exif={"width": meta.get("width", 0), "height": meta.get("height", 0)},
            star=meta.get("star"),
            updated_at=datetime.now(timezone.utc).isoformat(),
            updated_by="server",
        )

    @app.get("/metadata", response_model=ImageMetadataResponse)
    def get_metadata(path: str, request: Request = None):
        storage = _storage(request)
        _ensure_image(storage, path)

        mime = storage._guess_mime(path)  # type: ignore[attr-defined]
        if mime != "image/png":
            raise HTTPException(415, "metadata reading currently supports PNG images only")

        try:
            raw = storage.read_bytes(path)
            meta = read_png_info(io.BytesIO(raw))
        except HTTPException:
            raise
        except Exception as exc:  # pragma: no cover - unexpected parse errors
            raise HTTPException(500, f"failed to parse metadata: {exc}")

        return ImageMetadataResponse(path=path, format="png", meta=meta)

    @app.put("/item")
    def put_item(path: str, body: Sidecar, request: Request = None):
        storage = _storage(request)
        _ensure_image(storage, path)
        # Update in-memory metadata (session-only)
        meta = storage.get_metadata(path)
        meta["tags"] = body.tags
        meta["notes"] = body.notes
        meta["star"] = body.star
        storage.set_metadata(path, meta)
        return body

    @app.get("/thumb")
    def get_thumb(path: str, request: Request = None):
        storage = _storage(request)
        _ensure_image(storage, path)

        thumb = storage.get_thumbnail(path)
        if thumb is None:
            raise HTTPException(500, "failed to generate thumbnail")
        return Response(content=thumb, media_type="image/webp")

    @app.get("/file")
    def get_file(path: str, request: Request = None):
        storage = _storage(request)
        _ensure_image(storage, path)
        data = storage.read_bytes(path)
        return Response(content=data, media_type=storage._guess_mime(path))

    @app.get("/search", response_model=SearchResult)
    def search(request: Request = None, q: str = "", path: str = "/", limit: int = 100):
        storage = _storage(request)
        hits = storage.search(query=q, path=path, limit=limit)
        return SearchResult(items=[_to_item(storage, it) for it in hits])

    @app.get("/views", response_model=ViewsPayload)
    def get_views():
        return workspace.load_views()

    @app.put("/views", response_model=ViewsPayload)
    def put_views(body: ViewsPayload):
        if not workspace.can_write:
            raise HTTPException(403, "no-write mode")
        payload = body.model_dump()
        workspace.write_views(payload)
        return body

    # Mount frontend if dist exists
    frontend_dist = Path(__file__).parent / "frontend"
    if frontend_dist.is_dir():
        app.mount("/", NoCacheIndexStaticFiles(directory=str(frontend_dist), html=True), name="frontend")

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
    )
    workspace = Workspace.for_dataset(None, can_write=False)

    def _storage(request: Request) -> DatasetStorage:
        return request.state.storage  # type: ignore[attr-defined]

    def _ensure_image(storage: DatasetStorage, path: str) -> None:
        try:
            storage.validate_image_path(path)
        except FileNotFoundError:
            raise HTTPException(404, "file not found")
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    def _to_item(storage: DatasetStorage, cached) -> Item:
        meta = storage.get_metadata(cached.path)
        source = None
        if show_source:
            try:
                source = storage.get_source_path(cached.path)
            except Exception:
                source = None
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

    # Inject storage via middleware
    @app.middleware("http")
    async def attach_storage(request: Request, call_next):
        request.state.storage = storage
        response = await call_next(request)
        return response

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
        storage = _storage(request)
        try:
            index = storage.get_index(path)
        except ValueError:
            raise HTTPException(400, "invalid path")
        except FileNotFoundError:
            raise HTTPException(404, "folder not found")

        items = [_to_item(storage, it) for it in index.items]
        dirs = [DirEntry(name=d, kind="branch") for d in index.dirs]

        return FolderIndex(
            path=path,
            generatedAt=index.generated_at,
            items=items,
            dirs=dirs,
        )

    @app.post("/refresh")
    def refresh(path: str = "/", request: Request = None):
        # Dataset mode is static for now, but keep API parity with memory mode
        _ = path
        return {"ok": True, "note": "dataset mode is static"}

    @app.get("/item")
    def get_item(path: str, request: Request = None):
        storage = _storage(request)
        _ensure_image(storage, path)

        meta = storage.get_metadata(path)
        return Sidecar(
            tags=meta.get("tags", []),
            notes=meta.get("notes", ""),
            exif={"width": meta.get("width", 0), "height": meta.get("height", 0)},
            star=meta.get("star"),
            updated_at=datetime.now(timezone.utc).isoformat(),
            updated_by="server",
        )

    @app.get("/metadata", response_model=ImageMetadataResponse)
    def get_metadata(path: str, request: Request = None):
        storage = _storage(request)
        _ensure_image(storage, path)

        mime = storage._guess_mime(path)  # type: ignore[attr-defined]
        if mime != "image/png":
            raise HTTPException(415, "metadata reading currently supports PNG images only")

        try:
            raw = storage.read_bytes(path)
            meta = read_png_info(io.BytesIO(raw))
        except HTTPException:
            raise
        except Exception as exc:  # pragma: no cover - unexpected parse errors
            raise HTTPException(500, f"failed to parse metadata: {exc}")

        return ImageMetadataResponse(path=path, format="png", meta=meta)

    @app.put("/item")
    def put_item(path: str, body: Sidecar, request: Request = None):
        storage = _storage(request)
        _ensure_image(storage, path)
        # Update in-memory metadata (session-only)
        meta = storage.get_metadata(path)
        meta["tags"] = body.tags
        meta["notes"] = body.notes
        meta["star"] = body.star
        storage.set_metadata(path, meta)
        return body

    @app.get("/thumb")
    def get_thumb(path: str, request: Request = None):
        storage = _storage(request)
        _ensure_image(storage, path)

        thumb = storage.get_thumbnail(path)
        if thumb is None:
            raise HTTPException(500, "failed to generate thumbnail")
        return Response(content=thumb, media_type="image/webp")

    @app.get("/file")
    def get_file(path: str, request: Request = None):
        storage = _storage(request)
        _ensure_image(storage, path)
        data = storage.read_bytes(path)
        return Response(content=data, media_type=storage._guess_mime(path))

    @app.get("/search", response_model=SearchResult)
    def search(request: Request = None, q: str = "", path: str = "/", limit: int = 100):
        storage = _storage(request)
        hits = storage.search(query=q, path=path, limit=limit)
        return SearchResult(items=[_to_item(storage, it) for it in hits])

    @app.get("/views", response_model=ViewsPayload)
    def get_views():
        return workspace.load_views()

    @app.put("/views", response_model=ViewsPayload)
    def put_views(body: ViewsPayload):
        if not workspace.can_write:
            raise HTTPException(403, "no-write mode")
        payload = body.model_dump()
        workspace.write_views(payload)
        return body

    # Mount frontend if dist exists
    frontend_dist = Path(__file__).parent / "frontend"
    if frontend_dist.is_dir():
        app.mount("/", NoCacheIndexStaticFiles(directory=str(frontend_dist), html=True), name="frontend")

    return app
