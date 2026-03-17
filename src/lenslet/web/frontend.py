"""Shared static frontend serving helpers for Lenslet web apps."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope


class NoCacheIndexStaticFiles(StaticFiles):
    """Serve static assets with no-cache for the HTML shell."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.media_type == "text/html":
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


def frontend_dist_path() -> Path:
    return Path(__file__).resolve().parents[1] / "frontend"


@lru_cache(maxsize=8)
def load_frontend_shell(index_path: str, mtime_ns: int) -> str:
    _ = mtime_ns
    return Path(index_path).read_text(encoding="utf-8")


def mount_frontend(app: FastAPI) -> None:
    frontend_dist = frontend_dist_path()
    if frontend_dist.is_dir():
        app.mount("/", NoCacheIndexStaticFiles(directory=str(frontend_dist), html=True), name="frontend")
