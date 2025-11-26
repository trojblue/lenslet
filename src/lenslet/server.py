"""FastAPI server for Lenslet."""
from __future__ import annotations
import os
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal

from .storage.memory import MemoryStorage


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


# --- App Factory ---

def create_app(
    root_path: str,
    thumb_size: int = 256,
    thumb_quality: int = 70,
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

    # Create in-memory storage
    storage = MemoryStorage(
        root=root_path,
        thumb_size=thumb_size,
        thumb_quality=thumb_quality,
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
        return {"ok": True, "mode": "memory", "root": root_path}

    @app.get("/folders", response_model=FolderIndex)
    def get_folder(path: str = "/", request: Request = None):
        storage: MemoryStorage = request.state.storage
        try:
            index = storage.get_index(path)
        except ValueError:
            raise HTTPException(400, "invalid path")
        except FileNotFoundError:
            raise HTTPException(404, "folder not found")

        items = []
        for it in index.items:
            meta = storage.get_metadata(it.path)
            items.append(Item(
                path=it.path,
                name=it.name,
                type=it.mime,
                w=it.width,
                h=it.height,
                size=it.size,
                hasThumb=True,
                hasMeta=True,
                addedAt=datetime.fromtimestamp(it.mtime, tz=timezone.utc).isoformat(),
                star=meta.get("star"),
            ))

        dirs = [DirEntry(name=d, kind="branch") for d in index.dirs]

        return FolderIndex(
            path=path,
            generatedAt=index.generated_at,
            items=items,
            dirs=dirs,
        )

    @app.get("/item")
    def get_item(path: str, request: Request = None):
        storage: MemoryStorage = request.state.storage
        try:
            if not storage.exists(path):
                raise HTTPException(404, "file not found")
        except ValueError:
            raise HTTPException(400, "invalid path")

        meta = storage.get_metadata(path)
        return Sidecar(
            tags=meta.get("tags", []),
            notes=meta.get("notes", ""),
            exif={"width": meta.get("width", 0), "height": meta.get("height", 0)},
            star=meta.get("star"),
            updated_at=datetime.now(timezone.utc).isoformat(),
            updated_by="server",
        )

    @app.put("/item")
    def put_item(path: str, body: Sidecar, request: Request = None):
        storage: MemoryStorage = request.state.storage
        # Update in-memory metadata (session-only)
        meta = storage.get_metadata(path)
        meta["tags"] = body.tags
        meta["notes"] = body.notes
        meta["star"] = body.star
        storage.set_metadata(path, meta)
        return body

    @app.get("/thumb")
    def get_thumb(path: str, request: Request = None):
        storage: MemoryStorage = request.state.storage
        try:
            if not storage.exists(path):
                raise HTTPException(404, "file not found")
        except ValueError:
            raise HTTPException(400, "invalid path")

        thumb = storage.get_thumbnail(path)
        if thumb is None:
            raise HTTPException(500, "failed to generate thumbnail")
        return Response(content=thumb, media_type="image/webp")

    @app.get("/file")
    def get_file(path: str, request: Request = None):
        storage: MemoryStorage = request.state.storage
        lower = (path or "").lower()
        if not any(lower.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")):
            raise HTTPException(400, "unsupported file type")
        try:
            if not storage.exists(path):
                raise HTTPException(404, "file not found")
            data = storage.read_bytes(path)
        except ValueError:
            raise HTTPException(400, "invalid path")
        return Response(content=data, media_type=storage._guess_mime(path))

    @app.get("/search", response_model=SearchResult)
    def search(request: Request = None, q: str = "", path: str = "/", limit: int = 100):
        storage: MemoryStorage = request.state.storage
        # Simple search across all indexed items
        results = []
        ql = q.lower()
        path_norm = path.lstrip("/")
        scope_prefix = path_norm + "/" if path_norm else ""

        # Collect all items from all cached indexes
        all_items = []
        for idx in storage._indexes.values():
            for it in idx.items:
                all_items.append(it)

        # If no indexes cached yet, try to index root
        if not all_items:
            try:
                idx = storage.get_index("/")
                all_items = idx.items
            except Exception:
                pass

        for it in all_items:
            p = it.path.lstrip("/")
            if path_norm and not (p == path_norm or p.startswith(scope_prefix)):
                continue
            meta = storage.get_metadata(it.path)
            hay = " ".join([
                it.name,
                " ".join(meta.get("tags", [])),
                meta.get("notes", ""),
            ]).lower()
            if ql in hay:
                results.append(Item(
                    path=it.path,
                    name=it.name,
                    type=it.mime,
                    w=it.width,
                    h=it.height,
                    size=it.size,
                    hasThumb=True,
                    hasMeta=True,
                ))
                if len(results) >= limit:
                    break

        return SearchResult(items=results)

    # Mount frontend if dist exists
    frontend_dist = Path(__file__).parent / "frontend"
    if frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

    return app

