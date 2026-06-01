from __future__ import annotations

from collections import deque

from fastapi import FastAPI, Request

from ..browse import ToItemFn, build_folder_index, storage_from_request
from ..context import get_request_context
from ..models import BrowseFolderPathsPayload, BrowseFolderPayload
from ..paths import canonical_path
from ...storage.base import BrowseStorage


def _collect_folder_paths(storage: BrowseStorage) -> list[str]:
    queue: deque[str] = deque(["/"])
    seen: set[str] = set()

    while queue:
        path = canonical_path(queue.popleft())
        if path in seen:
            continue
        seen.add(path)
        try:
            index = storage.load_recursive_index(path)
        except FileNotFoundError:
            continue
        if index is None:
            continue
        for child_name in getattr(index, "dirs", []) or []:
            queue.append(canonical_path(storage.join(path, child_name)))

    return sorted(seen, key=lambda value: (value != "/", value))


def register_folder_routes(
    app: FastAPI,
    to_item: ToItemFn,
) -> None:
    @app.get("/folders", response_model=BrowseFolderPayload)
    def get_folder(
        request: Request,
        path: str = "/",
        recursive: bool = False,
        count_only: bool = False,
    ) -> BrowseFolderPayload:
        storage = storage_from_request(request)
        context = get_request_context(request)
        return build_folder_index(
            storage,
            canonical_path(path),
            to_item,
            recursive=recursive,
            count_only=count_only,
            browse_cache=context.recursive_browse_cache,
            hotpath_metrics=context.runtime.hotpath_metrics,
        )

    @app.get("/folders/paths", response_model=BrowseFolderPathsPayload)
    def get_folder_paths(request: Request) -> BrowseFolderPathsPayload:
        storage = storage_from_request(request)
        return BrowseFolderPathsPayload(paths=_collect_folder_paths(storage))
