from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request

from ..app_base import create_api_app
from ..frontend_serving import mount_frontend
from ..server_auth import TRUSTED_LOCAL_MUTATION_POLICY, request_can_mutate, set_mutation_policy
from .dataset import RankingDatasetError, load_ranking_dataset
from .persistence import RankingPersistenceError, RankingResultsStore, resolve_results_path
from .routes import build_ranking_router


def create_ranking_app(
    dataset_path: str | Path,
    *,
    results_path: str | Path | None = None,
) -> FastAPI:
    dataset = load_ranking_dataset(dataset_path)
    resolved_results_path = resolve_results_path(
        dataset.dataset_path,
        dataset.all_image_paths(),
        override_path=results_path,
    )
    results_store = RankingResultsStore(resolved_results_path)

    app = create_api_app(description="Lightweight image ranking server")
    set_mutation_policy(app, TRUSTED_LOCAL_MUTATION_POLICY)

    app.state.ranking_dataset = dataset
    app.state.ranking_results_path = results_store.results_path

    @app.get("/health")
    def health(request: Request) -> dict[str, object]:
        return {
            "ok": True,
            "mode": "ranking",
            "can_write": request_can_mutate(request, writes_enabled=True),
            "dataset_path": str(dataset.dataset_path),
            "results_path": str(results_store.results_path),
            "instance_count": dataset.instance_count,
        }

    app.include_router(build_ranking_router(dataset, results_store))
    mount_frontend(app)
    return app


__all__ = [
    "create_ranking_app",
    "RankingDatasetError",
    "RankingPersistenceError",
]
