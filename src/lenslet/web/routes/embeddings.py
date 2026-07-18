"""Embeddings route registration for Lenslet."""

from __future__ import annotations

import math

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from ...embeddings.index import EmbeddingIndexError, EmbeddingManager
from ..browse import ensure_image
from ..context import get_request_context
from ..models import (
    EmbeddingRejectedPayload,
    EmbeddingSearchItem,
    EmbeddingSearchRequest,
    EmbeddingSearchResponse,
    EmbeddingSpecPayload,
    EmbeddingsResponse,
)
from ..responses import error_response, error_response_models
from ..paths import canonical_path


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
    manager: EmbeddingManager | None,
) -> None:
    @app.get("/embeddings", response_model=EmbeddingsResponse)
    def get_embeddings() -> EmbeddingsResponse:
        if manager is None:
            return EmbeddingsResponse()
        return _build_embeddings_payload(manager)

    @app.post(
        "/embeddings/search",
        response_model=EmbeddingSearchResponse,
        responses=error_response_models(400, 404, 409),
    )
    def search_embeddings(body: EmbeddingSearchRequest, request: Request) -> EmbeddingSearchResponse | JSONResponse:
        if manager is None:
            return error_response(404, "embedding_search_unavailable", "embedding search unavailable")
        if not body.embedding:
            return error_response(400, "missing_embedding", "embedding is required")
        if manager.get_spec(body.embedding) is None:
            return error_response(404, "embedding_not_found", "embedding not found")
        top_k = body.top_k
        if top_k <= 0 or top_k > 1000:
            return error_response(400, "invalid_top_k", "top_k must be between 1 and 1000")
        if body.min_score is not None and not math.isfinite(body.min_score):
            return error_response(400, "invalid_min_score", "min_score must be a finite number")

        try:
            if body.query.kind == "path":
                storage = get_request_context(request).storage
                path = canonical_path(body.query.path)
                ensure_image(storage, path)
                row_index = storage.row_index_for_path(path)
                if row_index is None:
                    return error_response(404, "query_path_not_found", "query path not found")
                matches = manager.search_by_row_index(
                    body.embedding,
                    row_index=row_index,
                    top_k=top_k,
                    min_score=body.min_score,
                )
            else:
                matches = manager.search_by_vector(
                    body.embedding,
                    vector_b64=body.query.vector_b64,
                    top_k=top_k,
                    min_score=body.min_score,
                )
        except HTTPException as exc:
            message = str(exc.detail)
            if exc.status_code == 404:
                return error_response(404, "query_path_not_found", message)
            return error_response(exc.status_code, "invalid_query_path", message)
        except EmbeddingIndexError as exc:
            return error_response(400, "invalid_embedding_query", str(exc))

        return EmbeddingSearchResponse(
            embedding=body.embedding,
            items=[
                EmbeddingSearchItem(
                    row_index=match.row_index,
                    path=canonical_path(match.path),
                    score=match.score,
                )
                for match in matches
            ],
        )
