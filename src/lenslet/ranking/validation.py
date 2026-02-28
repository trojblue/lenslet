from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .dataset import RankingDataset


class RankingValidationError(ValueError):
    """Raised when ranking save payload validation fails."""


class RankingSavePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instance_id: str
    final_ranks: list[list[str]] = Field(default_factory=list)
    started_at: str | None = None
    submitted_at: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    completed: bool | None = None
    save_seq: int | None = Field(default=None, ge=0)

    @field_validator("instance_id", mode="before")
    @classmethod
    def _coerce_instance_id(cls, value: Any) -> str:
        if value is None:
            raise ValueError("instance_id is required")
        text = str(value).strip()
        if not text:
            raise ValueError("instance_id cannot be empty")
        return text

    @field_validator("final_ranks")
    @classmethod
    def _validate_rank_groups(cls, groups: list[list[str]]) -> list[list[str]]:
        for idx, group in enumerate(groups):
            if not isinstance(group, list):
                raise ValueError(f"final_ranks[{idx}] must be an array")
            if not group:
                raise ValueError(f"final_ranks[{idx}] cannot be empty")
            for value in group:
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"final_ranks[{idx}] contains an invalid image_id")
        return groups


def validate_save_payload(payload: Any, dataset: RankingDataset) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RankingValidationError("request body must be a JSON object")
    try:
        body = RankingSavePayload.model_validate(payload)
    except ValidationError as exc:
        raise RankingValidationError(_first_validation_error(exc)) from exc

    instance = dataset.get_instance(body.instance_id)
    if instance is None:
        raise RankingValidationError(f"unknown instance_id: {body.instance_id}")

    expected_ids = set(instance.image_ids)
    seen_ids: set[str] = set()
    for group_idx, group in enumerate(body.final_ranks):
        for image_id in group:
            if image_id not in expected_ids:
                raise RankingValidationError(
                    f"final_ranks[{group_idx}] includes unknown image_id: {image_id}",
                )
            if image_id in seen_ids:
                raise RankingValidationError(f"duplicate image_id in ranking payload: {image_id}")
            seen_ids.add(image_id)

    missing_ids = [image_id for image_id in instance.image_ids if image_id not in seen_ids]
    completed = body.completed if body.completed is not None else (not missing_ids)
    if completed and missing_ids:
        raise RankingValidationError(
            "completed ranking must include every image exactly once",
        )

    entry: dict[str, Any] = {
        "instance_id": instance.instance_id,
        "instance_index": instance.instance_index,
        "final_ranks": body.final_ranks,
        "completed": bool(completed),
        "submitted_at": body.submitted_at or _utc_now_iso(),
    }
    if missing_ids:
        entry["missing_image_ids"] = missing_ids
    if body.started_at is not None:
        entry["started_at"] = body.started_at
    if body.duration_ms is not None:
        entry["duration_ms"] = body.duration_ms
    if body.save_seq is not None:
        entry["save_seq"] = body.save_seq
    return entry


def derive_progress(
    dataset: RankingDataset,
    latest_entries_by_instance: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    completed_instance_ids: list[str] = []
    last_completed_index: int | None = None
    for instance in dataset.instances:
        entry = latest_entries_by_instance.get(instance.instance_id)
        if isinstance(entry, dict) and bool(entry.get("completed")):
            completed_instance_ids.append(instance.instance_id)
            last_completed_index = instance.instance_index

    resume_index = 0
    if last_completed_index is not None:
        next_index = last_completed_index + 1
        resume_index = next_index if next_index < dataset.instance_count else 0

    return {
        "completed_instance_ids": completed_instance_ids,
        "last_completed_instance_index": last_completed_index,
        "resume_instance_index": resume_index,
        "total_instances": dataset.instance_count,
    }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _first_validation_error(exc: ValidationError) -> str:
    first = exc.errors()[0] if exc.errors() else {"msg": "invalid request payload", "loc": ()}
    loc = ".".join(str(part) for part in first.get("loc", ()))
    msg = str(first.get("msg", "invalid request payload"))
    return f"{loc}: {msg}" if loc else msg
