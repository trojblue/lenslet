from __future__ import annotations

import time
from typing import Any
from urllib.parse import parse_qs, urlparse

def is_media_request(url: str) -> bool:
    path = urlparse(url).path
    return path.endswith("/thumb") or path.endswith("/file")

def delay_nth_file_request(page: Any, request_index: int, delay_ms: int) -> tuple[dict[str, int], Any]:
    state = {"count": 0, "delayed": 0}

    def route_handler(route: Any) -> None:
        state["count"] += 1
        if state["count"] == request_index:
            state["delayed"] += 1
            time.sleep(delay_ms / 1000.0)
        route.continue_()

    page.route("**/file?*", route_handler)
    return state, route_handler

def delay_file_path_requests(page: Any, target_path: str, delay_ms: int) -> tuple[dict[str, int], Any]:
    state = {"count": 0, "delayed": 0}

    def route_handler(route: Any) -> None:
        state["count"] += 1
        request_path = parse_qs(urlparse(route.request.url).query).get("path", [""])[0]
        if request_path == target_path:
            state["delayed"] += 1
            time.sleep(delay_ms / 1000.0)
        route.continue_()

    page.route("**/file?*", route_handler)
    return state, route_handler
