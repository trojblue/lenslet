from __future__ import annotations

from fastapi import FastAPI, Request

from ..browse import ToItemFn, search_results, storage_from_request
from ..models import BrowseSearchResultsPayload
from ..paths import canonical_path


def register_search_routes(app: FastAPI, to_item: ToItemFn) -> None:
    @app.get("/search", response_model=BrowseSearchResultsPayload)
    def search(request: Request, q: str = "", path: str = "/", limit: int = 100) -> BrowseSearchResultsPayload:
        storage = storage_from_request(request)
        return search_results(storage, to_item, q, canonical_path(path), limit)
