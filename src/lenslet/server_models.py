from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

Mime = Literal["image/webp", "image/jpeg", "image/png"]


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
    page: int | None = None
    pageSize: int | None = None
    pageCount: int | None = None
    totalItems: int | None = None


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


class _ExportComparisonRequestBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paths: list[str]
    labels: list[str] | None = None
    embed_metadata: bool = True
    reverse_order: bool = False


class ExportComparisonRequestV1(_ExportComparisonRequestBase):
    v: Literal[1]

    @field_validator("paths")
    @classmethod
    def validate_pair_paths(cls, value: list[str]) -> list[str]:
        if len(value) != 2:
            raise ValueError("comparison export v1 requires exactly 2 paths")
        return value

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if len(value) > 2:
            raise ValueError("comparison export v1 accepts at most 2 labels")
        return value


class ExportComparisonRequestV2(_ExportComparisonRequestBase):
    v: Literal[2]
    paths: list[str]

    @field_validator("paths")
    @classmethod
    def validate_path_count(cls, value: list[str]) -> list[str]:
        if len(value) < 2 or len(value) > MAX_EXPORT_COMPARISON_PATHS_V2:
            raise ValueError(
                f"comparison export v2 requires between 2 and {MAX_EXPORT_COMPARISON_PATHS_V2} paths",
            )
        return value

    @model_validator(mode="after")
    def validate_labels(self) -> "ExportComparisonRequestV2":
        if self.labels is None:
            return self
        if len(self.labels) > len(self.paths):
            raise ValueError("comparison export v2 accepts at most one label per path")
        return self


ExportComparisonRequest = Annotated[
    ExportComparisonRequestV1 | ExportComparisonRequestV2,
    Field(discriminator="v"),
]
EXPORT_COMPARISON_REQUEST_ADAPTER = TypeAdapter(ExportComparisonRequest)


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
