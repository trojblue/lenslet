from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from .dataset import RankingDataset
from .persistence import RankingResultsStore
from .validation import RankingValidationError, derive_progress, validate_save_payload


def build_ranking_router(
    dataset: RankingDataset,
    results_store: RankingResultsStore,
) -> APIRouter:
    router = APIRouter(prefix="/rank", tags=["ranking"])

    @router.get("/dataset")
    def get_dataset() -> dict[str, Any]:
        return dataset.to_response_payload(_rank_image_url)

    @router.get("/image")
    def get_image(instance_id: str, image_id: str):
        instance = dataset.get_instance(instance_id)
        if instance is None:
            raise HTTPException(404, f"unknown instance_id: {instance_id}")
        for image in instance.images:
            if image.image_id == image_id:
                return FileResponse(str(image.abs_path))
        raise HTTPException(404, f"unknown image_id for instance '{instance_id}': {image_id}")

    @router.post("/save")
    def save(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            entry = validate_save_payload(payload, dataset)
        except RankingValidationError as exc:
            raise HTTPException(400, str(exc)) from exc
        results_store.append(entry)
        return {
            "ok": True,
            "instance_id": entry["instance_id"],
            "instance_index": entry["instance_index"],
            "completed": entry["completed"],
        }

    @router.get("/progress")
    def get_progress() -> dict[str, Any]:
        latest = results_store.latest_entries_by_instance()
        return derive_progress(dataset, latest)

    @router.get("/export")
    def export_results(completed_only: bool = False) -> dict[str, Any]:
        ordered_ids = [instance.instance_id for instance in dataset.instances]
        entries = results_store.collapsed_entries(ordered_ids)
        if completed_only:
            entries = [entry for entry in entries if bool(entry.get("completed"))]
        return {
            "dataset_path": str(dataset.dataset_path),
            "results_path": str(results_store.results_path),
            "count": len(entries),
            "results": entries,
        }

    return router


def _rank_image_url(instance_id: str, image_id: str) -> str:
    return (
        "/rank/image"
        f"?instance_id={quote(instance_id, safe='')}"
        f"&image_id={quote(image_id, safe='')}"
    )
