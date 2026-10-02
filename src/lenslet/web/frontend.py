"""Static frontend serving helpers for Lenslet web apps."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope


_FINGERPRINTED_ASSET = re.compile(r"assets/[^/]+-[A-Za-z0-9_-]{8}\.(?:js|css)")


class FrontendStaticFiles(StaticFiles):
    """Revalidate the shell while retaining content-addressed Vite bundles."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.media_type == "text/html":
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        elif response.status_code in (200, 206, 304) and _FINGERPRINTED_ASSET.fullmatch(path):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
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
        app.mount("/", FrontendStaticFiles(directory=str(frontend_dist), html=True), name="frontend")
