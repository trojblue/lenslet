from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field


class RankingImagePayload(BaseModel):
    image_id: str
    source_path: str
    url: str


class RankingInstancePayload(BaseModel):
    instance_id: str
    instance_index: int
    max_ranks: int
    images: list[RankingImagePayload]


class RankingDatasetResponse(BaseModel):
    dataset_path: str
    instance_count: int
    instances: list[RankingInstancePayload]


class RankingHealthResponse(BaseModel):
    ok: bool
    mode: Literal["ranking"]
    can_write: bool
    dataset_path: str
    results_path: str
    instance_count: int


class RankingSaveResponse(BaseModel):
    ok: bool
    instance_id: str
    instance_index: int
    completed: bool


class _RankingResultEntryRequired(TypedDict):
    instance_id: str
    instance_index: int
    completed: bool


class RankingResultEntry(_RankingResultEntryRequired, total=False):
    final_ranks: list[list[str]]
    missing_image_ids: list[str]
    started_at: str
    submitted_at: str
    duration_ms: int
    save_seq: int


class RankingProgressResponse(BaseModel):
    completed_instance_ids: list[str] = Field(default_factory=list)
    last_completed_instance_index: int | None = None
    resume_instance_index: int
    total_instances: int


class RankingExportEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    instance_id: str
    instance_index: int | None = None
    final_ranks: list[list[str]] | None = None
    completed: bool | None = None
    missing_image_ids: list[str] | None = None
    started_at: str | None = None
    submitted_at: str | None = None
    duration_ms: int | None = None
    save_seq: int | None = None


class RankingExportResponse(BaseModel):
    dataset_path: str
    results_path: str
    count: int
    results: list[RankingExportEntry] = Field(default_factory=list)
