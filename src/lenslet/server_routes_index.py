"""Index/frontend route registration for Lenslet."""

from __future__ import annotations

import html
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from . import og
from .server_routes_og import _dataset_count, _dataset_label
from .workspace import Workspace


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


def _build_index_title(label: str, total_count: int | None) -> str:
    title = f"Lenslet: {label}"
    if total_count is None:
        return title
    return f"{title} ({total_count:,} images)"


def _build_index_description(label: str, scope_path: str) -> str:
    if scope_path == "/":
        return f"Browse {label} gallery"
    return f"Browse {label} gallery in {scope_path}"


def register_index_routes(app: FastAPI, storage, workspace: Workspace, og_preview: bool) -> None:
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


def mount_frontend(app: FastAPI) -> None:
    frontend_dist = Path(__file__).parent / "frontend"
    if frontend_dist.is_dir():
        app.mount("/", NoCacheIndexStaticFiles(directory=str(frontend_dist), html=True), name="frontend")
