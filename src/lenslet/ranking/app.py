from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from fastapi import FastAPI, Request

from ..web.app.base import create_api_app
from ..web.frontend import mount_frontend
from ..web.auth import (
    READ_ONLY_MUTATION_POLICY,
    request_can_mutate,
    set_mutation_policy,
    trusted_local_mutation_policy,
)
from .dataset import RankingDatasetError, load_ranking_dataset
from .models import RankingHealthResponse
from .persistence import RankingPersistenceError, RankingResultsStore, resolve_results_path
from .routes import build_ranking_router


def create_ranking_app(
    dataset_path: str | Path,
    *,
    results_path: str | Path | None = None,
    trusted_write_origins: Iterable[str] | None = None,
) -> FastAPI:
    dataset = load_ranking_dataset(dataset_path)
    resolved_results_path = resolve_results_path(
        dataset.dataset_path,
        dataset.all_image_paths(),
        override_path=results_path,
    )
    results_store = RankingResultsStore(resolved_results_path)

    app = create_api_app(description="Lightweight image ranking server")
    origins = tuple(trusted_write_origins or ())
    policy = trusted_local_mutation_policy(origins) if origins else READ_ONLY_MUTATION_POLICY
    set_mutation_policy(app, policy)

    app.state.ranking_dataset = dataset
    app.state.ranking_results_path = results_store.results_path

    @app.get("/health", response_model=RankingHealthResponse)
    def health(request: Request) -> RankingHealthResponse:
        return RankingHealthResponse(
            ok=True,
            mode="ranking",
            can_write=request_can_mutate(request, writes_enabled=True),
            dataset_path=str(dataset.dataset_path),
            results_path=str(results_store.results_path),
            instance_count=dataset.instance_count,
        )

    app.include_router(build_ranking_router(dataset, results_store))
    mount_frontend(app)
    return app


__all__ = [
    "create_ranking_app",
    "RankingDatasetError",
    "RankingPersistenceError",
]
