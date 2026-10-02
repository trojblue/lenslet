from __future__ import annotations

import asyncio
import time
from pathlib import Path

import httpx

from lenslet.web.frontend import FrontendStaticFiles, load_frontend_shell


def test_load_frontend_shell_reloads_when_mtime_changes(tmp_path: Path) -> None:
    index_path = tmp_path / "index.html"
    index_path.write_text("<html>first</html>", encoding="utf-8")
    first_mtime = index_path.stat().st_mtime_ns

    first = load_frontend_shell(str(index_path), first_mtime)

    time.sleep(0.01)
    index_path.write_text("<html>second</html>", encoding="utf-8")
    second_mtime = index_path.stat().st_mtime_ns

    second = load_frontend_shell(str(index_path), second_mtime)

    assert first == "<html>first</html>"
    assert second == "<html>second</html>"


def test_frontend_cache_policy_tracks_content_addressed_assets(tmp_path: Path) -> None:
    asyncio.run(_assert_frontend_cache_policy(tmp_path))


async def _assert_frontend_cache_policy(tmp_path: Path) -> None:
    (tmp_path / "assets").mkdir()
    files = {
        "index.html": "<html>shell</html>",
        "assets/index-AbCd1234.js": "export const version = 1;",
        "assets/index-_bCd-234.css": "body { color: red; }",
        "assets/index.js": "mutable",
        "assets/index-123.js": "not a Vite fingerprint",
        "assets/index-AbCd1234.html": "<html>other shell</html>",
        "favicon.ico": "icon",
    }
    for path, content in files.items():
        (tmp_path / path).write_text(content, encoding="utf-8")
    app = FrontendStaticFiles(directory=tmp_path, html=True)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for path in files:
            response = await client.get(f"/{path}")
            assert response.status_code == 200
            policy = response.headers.get("cache-control", "")
            if path.endswith(".html"):
                assert "no-store" in policy
            elif path in ("assets/index-AbCd1234.js", "assets/index-_bCd-234.css"):
                assert policy == "public, max-age=31536000, immutable"
                cached = await client.get(f"/{path}", headers={"If-None-Match": response.headers["etag"]})
                assert cached.status_code == 304
                assert cached.headers["cache-control"] == policy
            else:
                assert "immutable" not in policy
        shell = await client.get("/")
        assert "no-store" in shell.headers["cache-control"]
