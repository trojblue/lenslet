"""Embeddings route registration for Lenslet."""

from __future__ import annotations

import math

from fastapi import FastAPI, HTTPException, Request

from .embeddings.index import EmbeddingIndexError, EmbeddingManager
from .server_models import (
    EmbeddingRejectedPayload,
    EmbeddingSearchItem,
    EmbeddingSearchRequest,
    EmbeddingSearchResponse,
    EmbeddingSpecPayload,
    EmbeddingsResponse,
)


def _build_embeddings_payload(manager: EmbeddingManager) -> EmbeddingsResponse:
    return EmbeddingsResponse(
        embeddings=[
            EmbeddingSpecPayload(
                name=spec.name,
                dimension=spec.dimension,
                dtype=spec.dtype,
                metric=spec.metric,
            )
            for spec in manager.available
        ],
        rejected=[EmbeddingRejectedPayload(name=rej.name, reason=rej.reason) for rej in manager.rejected],
    )


def register_embedding_routes(
    app: FastAPI,
    storage,
    manager: EmbeddingManager | None,
) -> None:
    from . import server as _server

    @app.get("/embeddings", response_model=EmbeddingsResponse)
    def get_embeddings():
        if manager is None:
            return EmbeddingsResponse()
        return _build_embeddings_payload(manager)

    @app.post("/embeddings/search", response_model=EmbeddingSearchResponse)
    def search_embeddings(body: EmbeddingSearchRequest, request: Request = None):
        _ = request
        if manager is None:
            raise HTTPException(404, "embedding search unavailable")
        if not body.embedding:
            raise HTTPException(400, "embedding is required")
        if manager.get_spec(body.embedding) is None:
            raise HTTPException(404, "embedding not found")
        has_path = body.query_path is not None
        has_vector = body.query_vector_b64 is not None
        if has_path == has_vector:
            raise HTTPException(400, "provide exactly one of query_path or query_vector_b64")
        top_k = body.top_k
        if top_k <= 0 or top_k > 1000:
            raise HTTPException(400, "top_k must be between 1 and 1000")
        if body.min_score is not None and not math.isfinite(body.min_score):
            raise HTTPException(400, "min_score must be a finite number")

        try:
            if body.query_path is not None:
                path = _server._canonical_path(body.query_path)
                _server._ensure_image(storage, path)
                row_index = storage.row_index_for_path(path)
                if row_index is None:
                    raise HTTPException(404, "query_path not found")
                matches = manager.search_by_path(
                    body.embedding,
                    row_index=row_index,
                    top_k=top_k,
                    min_score=body.min_score,
                )
            else:
                matches = manager.search_by_vector(
                    body.embedding,
                    vector_b64=body.query_vector_b64 or "",
                    top_k=top_k,
                    min_score=body.min_score,
                )
        except EmbeddingIndexError as exc:
            raise HTTPException(400, str(exc))

        return EmbeddingSearchResponse(
            embedding=body.embedding,
            items=[
                EmbeddingSearchItem(
                    row_index=match.row_index,
                    path=_server._canonical_path(match.path),
                    score=match.score,
                )
                for match in matches
            ],
        )
