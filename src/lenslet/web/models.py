from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..storage.image_media import ImageMime

JsonObject = dict[str, Any]
ExportComparisonOutputFormat = Literal["png", "gif"]
StarRating = Annotated[int, Field(ge=0, le=5, strict=True)]


class BrowseItemPayload(BaseModel):
    path: str
    name: str
    mime: ImageMime
    width: int
    height: int
    size: int
    has_thumbnail: bool = True  # Always true in memory mode
    has_metadata: bool = True   # Always true in memory mode
    hash: str | None = None
    added_at: str | None = None
    star: StarRating | None = None
    notes: str | None = None
    url: str | None = None
    source: str | None = None
    metrics: dict[str, float] | None = None
    metric_labels: dict[str, str] | None = None


class BrowseFolderEntryPayload(BaseModel):
    name: str
    kind: Literal["branch", "leaf-real", "leaf-pointer"] = "branch"


class BrowseFolderPayload(BaseModel):
    version: int = 1
    path: str
    generated_at: str
    items: list[BrowseItemPayload] = Field(default_factory=list)
    folders: list[BrowseFolderEntryPayload] = Field(default_factory=list)
    metric_keys: list[str] = Field(default_factory=list)
    total_items: int | None = None
    offset: int | None = None
    limit: int | None = None


class BrowseFolderPathsPayload(BaseModel):
    paths: list[str] = Field(default_factory=list)


class Sidecar(BaseModel):
    v: int = 1
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    exif: JsonObject | None = None
    hash: str | None = None
    original_position: str | None = None
    star: StarRating | None = None
    version: int = 1
    updated_at: str = ""
    updated_by: str = "server"
    table_fields: JsonObject | None = None


class SidecarPatch(BaseModel):
    base_version: int | None = None
    set_star: StarRating | None = None
    set_notes: str | None = None
    set_tags: list[str] | None = None
    add_tags: list[str] = Field(default_factory=list)
    remove_tags: list[str] = Field(default_factory=list)


class PresencePayload(BaseModel):
    gallery_id: str
    lease_id: str | None = None


class PresenceMovePayload(BaseModel):
    from_gallery_id: str
    to_gallery_id: str
    lease_id: str


class PresenceLeavePayload(BaseModel):
    gallery_id: str
    lease_id: str


class PresenceCountPayload(BaseModel):
    gallery_id: str
    viewing: int
    editing: int


class PresenceSessionResponse(PresenceCountPayload):
    client_id: str
    lease_id: str


class PresenceMoveResponse(BaseModel):
    client_id: str
    lease_id: str
    from_scope: PresenceCountPayload
    to_scope: PresenceCountPayload


class PresenceLeaveResponse(PresenceSessionResponse):
    removed: bool


class PresenceInvalidLeaseResponse(BaseModel):
    error: Literal["invalid_lease"]
    gallery_id: str
    client_id: str


class PresenceScopeMismatchResponse(BaseModel):
    error: Literal["scope_mismatch"]
    requested_gallery_id: str
    actual_gallery_id: str
    client_id: str


class BrowseSearchResultsPayload(BaseModel):
    items: list[BrowseItemPayload]


class ImageMetadataResponse(BaseModel):
    path: str
    format: Literal["png", "jpeg", "webp"]
    meta: JsonObject


class ErrorResponse(BaseModel):
    error: str
    message: str


class SidecarConflictResponse(BaseModel):
    error: Literal["version_conflict"]
    current: Sidecar


class RefreshStatusPayload(BaseModel):
    enabled: bool | None = None
    note: str | None = None


class LabelsHealthPayload(BaseModel):
    enabled: bool
    log: str | None = None
    snapshot: str | None = None


class BrowseCacheHealthPayload(BaseModel):
    enabled: bool
    persisted: bool
    path: str | None = None
    max_bytes: int
    pending_warms: int


class CompareExportHealthPayload(BaseModel):
    supported_versions: list[int]
    max_paths_v2: int
    max_paths_v2_gif: int


class IndexingHealthPayload(BaseModel):
    state: Literal["idle", "running", "ready", "error"]
    scope: str | None = None
    done: int | None = None
    total: int | None = None
    generation: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None


class PresenceHealthPayload(BaseModel):
    view_ttl_seconds: float | None = None
    edit_ttl_seconds: float | None = None
    prune_interval_seconds: float | None = None
    active_clients: int | None = None
    active_scopes: int | None = None
    stale_pruned_total: int | None = None
    invalid_lease_total: int | None = None
    replay_miss_total: int | None = None
    replay_buffer_size: int | None = None
    replay_buffer_capacity: int | None = None
    replay_oldest_event_id: int | None = None
    replay_newest_event_id: int | None = None
    connected_sse_clients: int | None = None


class HotpathTimerPayload(BaseModel):
    count: int
    total_ms: float
    avg_ms: float


class HotpathHealthPayload(BaseModel):
    counters: dict[str, int] = Field(default_factory=dict)
    timers_ms: dict[str, HotpathTimerPayload] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    ok: bool
    mode: str | None = None
    can_write: bool | None = None
    workspace_id: str | None = None
    storage_origin: str | None = None
    root: str | None = None
    datasets: list[str] | None = None
    total_images: int | None = None
    refresh: RefreshStatusPayload | None = None
    browse_cache: BrowseCacheHealthPayload | None = None
    compare_export: CompareExportHealthPayload | None = None
    labels: LabelsHealthPayload | None = None
    indexing: IndexingHealthPayload | None = None
    presence: PresenceHealthPayload | None = None
    hotpath: HotpathHealthPayload | None = None


class RefreshResponse(BaseModel):
    ok: bool
    note: str | None = None


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
    views: list[JsonObject] = Field(default_factory=list)


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


class EmbeddingPathQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["path"]
    path: str


class EmbeddingVectorQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["vector"]
    vector_b64: str


EmbeddingSearchQuery = Annotated[
    EmbeddingPathQuery | EmbeddingVectorQuery,
    Field(discriminator="kind"),
]


class EmbeddingSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embedding: str
    query: EmbeddingSearchQuery
    top_k: int = 50
    min_score: float | None = None


class EmbeddingSearchItem(BaseModel):
    row_index: int
    path: str
    score: float


class EmbeddingSearchResponse(BaseModel):
    embedding: str
    items: list[EmbeddingSearchItem] = Field(default_factory=list)
