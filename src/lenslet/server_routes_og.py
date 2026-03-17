"""OG route registration and dataset metadata helpers for Lenslet."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, Response

from . import og
from .media_errors import MediaError
from .og_cache import OgImageCache
from .server_context import get_request_context
from .storage.base import BrowseStorage
from .workspace import Workspace

logger = logging.getLogger(__name__)


def _og_cache_key(workspace: Workspace, style: str, signature: str, path: str) -> str:
    safe_path = og.normalize_path(path)
    return f"og:{style}:{signature}:{safe_path}"


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


def _dataset_signature(current_storage: BrowseStorage, current_workspace: Workspace) -> str:
    mtime = _dataset_mtime(current_workspace)
    if mtime is not None:
        return f"parquet:{int(mtime)}"
    try:
        index = current_storage.get_index("/")
    except Exception:
        return "unknown"
    if index is None:
        return "empty"
    items = index.items
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


def _dataset_label(current_workspace: Workspace) -> str:
    if current_workspace.views_override is not None:
        name = current_workspace.views_override.name
        if name.endswith(".lenslet.json"):
            name = name[: -len(".lenslet.json")]
        label = Path(name).stem
        return label or "dataset"
    if current_workspace.root is not None:
        label = current_workspace.root.parent.name
        return label or "dataset"
    return "dataset"


def _dataset_count(current_storage: BrowseStorage) -> int | None:
    try:
        return current_storage.total_items()
    except Exception:
        return None


def _og_cache_from_workspace(workspace: Workspace, enabled: bool) -> OgImageCache | None:
    if not enabled or not workspace.can_write:
        return None
    cache_dir = workspace.og_cache_dir()
    if cache_dir is None:
        return None
    return OgImageCache(cache_dir)


def register_og_routes(app: FastAPI, enabled: bool) -> None:
    @app.get("/og-image", include_in_schema=False, name="og_image")
    def og_image(request: Request, style: str = og.OG_STYLE, path: str | None = None) -> Response:
        context = get_request_context(request)
        current_storage = context.storage
        current_workspace = context.workspace
        og_cache = context.og_cache
        label = _dataset_label(current_workspace)
        if not enabled:
            return Response(content=og.fallback_og_image(label), media_type="image/png")
        try:
            style_key = og.resolve_style(style)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        sample_path = _og_path_from_request(path, request)
        signature = _dataset_signature(current_storage, current_workspace)
        cache_key = _og_cache_key(current_workspace, style_key, signature, sample_path)
        if og_cache is not None:
            cached = og_cache.get(cache_key)
            if cached is not None:
                return Response(content=cached, media_type="image/png")

        sample_count = og.OG_IMAGES_X * og.OG_IMAGES_Y
        tiles: list[list[list[tuple[int, int, int]]]] = []
        for sample_path_entry in og.sample_paths(current_storage, sample_path, sample_count):
            try:
                thumb = current_storage.get_thumbnail(sample_path_entry)
            except FileNotFoundError:
                logger.warning("og thumbnail source missing for %s", sample_path_entry)
                continue
            except MediaError as exc:
                logger.warning("og thumbnail generation failed for %s: %s", sample_path_entry, exc.reason)
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
