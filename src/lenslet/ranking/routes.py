from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from ..web.responses import error_response, error_response_models
from ..web.permissions import deny_if_mutation_forbidden
from .dataset import RankingDataset
from .models import (
    RankingDatasetResponse,
    RankingExportResponse,
    RankingProgressResponse,
    RankingSaveResponse,
)
from .persistence import RankingResultsStore
from .validation import RankingSavePayload, RankingValidationError, derive_progress, validate_save_payload


def build_ranking_router(
    dataset: RankingDataset,
    results_store: RankingResultsStore,
) -> APIRouter:
    router = APIRouter(prefix="/rank", tags=["ranking"])

    @router.get("/dataset", response_model=RankingDatasetResponse)
    def get_dataset() -> RankingDatasetResponse:
        return RankingDatasetResponse.model_validate(dataset.to_response_payload(_rank_image_url))

    @router.get("/image", response_model=None, responses=error_response_models(404))
    def get_image(instance_id: str, image_id: str) -> Response:
        image = dataset.get_image(instance_id, image_id)
        if image is None:
            return error_response(
                404,
                "rank_image_not_found",
                f"unknown image_id for instance '{instance_id}': {image_id}",
            )
        return FileResponse(str(image.abs_path))

    @router.post("/save", response_model=RankingSaveResponse, responses=error_response_models(400, 403))
    def save(request: Request, payload: RankingSavePayload) -> RankingSaveResponse | JSONResponse:
        if denied := deny_if_mutation_forbidden(request, writes_enabled=True):
            return denied
        try:
            entry = validate_save_payload(payload, dataset)
        except RankingValidationError as exc:
            return error_response(400, "invalid_ranking_payload", str(exc))
        results_store.append(entry)
        return RankingSaveResponse(
            ok=True,
            instance_id=entry["instance_id"],
            instance_index=entry["instance_index"],
            completed=entry["completed"],
        )

    @router.get("/progress", response_model=RankingProgressResponse)
    def get_progress() -> RankingProgressResponse:
        latest = results_store.latest_entries_by_instance()
        return RankingProgressResponse.model_validate(derive_progress(dataset, latest))

    @router.get("/export", response_model=RankingExportResponse)
    def export_results(completed_only: bool = False) -> RankingExportResponse:
        ordered_ids = [instance.instance_id for instance in dataset.instances]
        entries = results_store.collapsed_entries(ordered_ids)
        if completed_only:
            entries = [entry for entry in entries if entry["completed"]]
        return RankingExportResponse(
            dataset_path=str(dataset.dataset_path),
            results_path=str(results_store.results_path),
            count=len(entries),
            results=entries,
        )

    return router


def _rank_image_url(instance_id: str, image_id: str) -> str:
    return (
        "/rank/image"
        f"?instance_id={quote(instance_id, safe='')}"
        f"&image_id={quote(image_id, safe='')}"
    )
