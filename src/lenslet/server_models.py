from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Mime = Literal["image/webp", "image/jpeg", "image/png"]
ExportComparisonOutputFormat = Literal["png", "gif"]


class Item(BaseModel):
    path: str
    name: str
    type: Mime
    w: int
    h: int
    size: int
    hasThumb: bool = True  # Always true in memory mode
    hasMeta: bool = True   # Always true in memory mode
    hash: str | None = None
    addedAt: str | None = None
    star: int | None = None
    comments: str | None = None
    url: str | None = None
    source: str | None = None
    metrics: dict[str, float] | None = None


class DirEntry(BaseModel):
    name: str
    kind: Literal["branch", "leaf-real", "leaf-pointer"] = "branch"


class FolderIndex(BaseModel):
    v: int = 1
    path: str
    generatedAt: str
    items: list[Item] = Field(default_factory=list)
    dirs: list[DirEntry] = Field(default_factory=list)
    metricKeys: list[str] = Field(default_factory=list)
    page: int | None = None
    pageSize: int | None = None
    pageCount: int | None = None
    totalItems: int | None = None


class FolderPathsResponse(BaseModel):
    paths: list[str] = Field(default_factory=list)


class Sidecar(BaseModel):
    v: int = 1
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    exif: dict | None = None
    hash: str | None = None
    original_position: str | None = None
    star: int | None = None
    version: int = 1
    updated_at: str = ""
    updated_by: str = "server"
    table_fields: dict[str, Any] | None = None


class SidecarPatch(BaseModel):
    base_version: int | None = None
    set_star: int | None = None
    set_notes: str | None = None
    set_tags: list[str] | None = None
    add_tags: list[str] = Field(default_factory=list)
    remove_tags: list[str] = Field(default_factory=list)


class PresencePayload(BaseModel):
    gallery_id: str
    client_id: str
    lease_id: str | None = None


class PresenceMovePayload(BaseModel):
    from_gallery_id: str
    to_gallery_id: str
    client_id: str
    lease_id: str


class PresenceLeavePayload(BaseModel):
    gallery_id: str
    client_id: str
    lease_id: str


class SearchResult(BaseModel):
    items: list[Item]


class ImageMetadataResponse(BaseModel):
    path: str
    format: Literal["png", "jpeg", "webp"]
    meta: dict


MAX_EXPORT_COMPARISON_PATHS_V2 = 12
MAX_EXPORT_COMPARISON_PATHS_V2_GIF = 24


def export_comparison_max_paths_v2_for_format(output_format: ExportComparisonOutputFormat) -> int:
    if output_format == "gif":
        return MAX_EXPORT_COMPARISON_PATHS_V2_GIF
    return MAX_EXPORT_COMPARISON_PATHS_V2


class _ExportComparisonRequestBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paths: list[str]
    labels: list[str] | None = None
    embed_metadata: bool = True
    reverse_order: bool = False
    output_format: ExportComparisonOutputFormat = "png"
    high_quality_gif: bool = False


class ExportComparisonRequest(_ExportComparisonRequestBase):
    v: Literal[2]
    paths: list[str]

    @field_validator("paths")
    @classmethod
    def validate_path_count(cls, value: list[str]) -> list[str]:
        if len(value) < 2:
            raise ValueError(
                "comparison export v2 requires between 2 and the configured max paths",
            )
        return value

    @model_validator(mode="after")
    def validate_labels(self) -> "ExportComparisonRequest":
        max_paths = export_comparison_max_paths_v2_for_format(self.output_format)
        if len(self.paths) > max_paths:
            raise ValueError(
                f"comparison export v2 requires between 2 and {max_paths} paths for {self.output_format} output",
            )
        if self.labels is None:
            return self
        if len(self.labels) > len(self.paths):
            raise ValueError("comparison export v2 accepts at most one label per path")
        return self


class ViewsPayload(BaseModel):
    version: int = 1
    views: list[dict] = Field(default_factory=list)


class EmbeddingSpecPayload(BaseModel):
    name: str
    dimension: int
    dtype: str
    metric: str


class EmbeddingRejectedPayload(BaseModel):
    name: str
    reason: str


class EmbeddingsResponse(BaseModel):
    embeddings: list[EmbeddingSpecPayload] = Field(default_factory=list)
    rejected: list[EmbeddingRejectedPayload] = Field(default_factory=list)


class EmbeddingSearchRequest(BaseModel):
    embedding: str
    query_path: str | None = None
    query_vector_b64: str | None = None
    top_k: int = 50
    min_score: float | None = None


class EmbeddingSearchItem(BaseModel):
    row_index: int
    path: str
    score: float


class EmbeddingSearchResponse(BaseModel):
    embedding: str
    items: list[EmbeddingSearchItem] = Field(default_factory=list)
