from __future__ import annotations

import math
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..browse.query import parse_query_date_bound
from ..storage.image_media import ImageMime

JsonObject = dict[str, Any]
ExportComparisonOutputFormat = Literal["png", "gif"]
StarRating = Annotated[int, Field(ge=0, le=5, strict=True)]
BrowseQuerySortDirection = Literal["asc", "desc"]
BrowseQueryCompareOp = Literal["<", "<=", ">", ">="]
DerivedMetricNumericMissingPolicy = Literal["zero", "invalid"]
BROWSE_QUERY_DEFAULT_LIMIT = 1000
BROWSE_QUERY_MAX_LIMIT = 10_000
DERIVED_METRIC_KEY_PREFIX = "@derived/"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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
    categoricals: dict[str, str] | None = None


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
    categorical_keys: list[str] = Field(default_factory=list)
    total_items: int | None = None
    offset: int | None = None
    limit: int | None = None


class BrowseQueryStarsValuesPayload(StrictModel):
    values: list[StarRating] = Field(default_factory=list)


class BrowseQueryTextPayload(StrictModel):
    value: str


class BrowseQueryDateRangePayload(StrictModel):
    from_: str | None = Field(default=None, alias="from")
    to: str | None = None

    @field_validator("from_", "to")
    @classmethod
    def validate_parseable_date_bound(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return value
        try:
            parse_query_date_bound(value, as_end=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("date range bounds must be parseable dates") from exc
        return value


class BrowseQueryNumberComparePayload(StrictModel):
    op: BrowseQueryCompareOp
    value: float

    @field_validator("value")
    @classmethod
    def validate_finite_value(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("value must be finite")
        return value


class BrowseQueryMetricRangePayload(StrictModel):
    key: str
    min: float
    max: float

    @field_validator("min", "max")
    @classmethod
    def validate_finite_bound(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("metric range bounds must be finite")
        return value

    @model_validator(mode="after")
    def validate_bounds(self) -> "BrowseQueryMetricRangePayload":
        if self.min > self.max:
            raise ValueError("metric range min must be less than or equal to max")
        if not self.key.strip():
            raise ValueError("metric range key must be non-empty")
        return self


class BrowseQueryCategoricalInPayload(StrictModel):
    key: str
    values: list[str] = Field(default_factory=list)

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("categorical filter key must be non-empty")
        return value


class BrowseQueryStarsInClausePayload(StrictModel):
    starsIn: BrowseQueryStarsValuesPayload


class BrowseQueryStarsNotInClausePayload(StrictModel):
    starsNotIn: BrowseQueryStarsValuesPayload


class BrowseQueryNameContainsClausePayload(StrictModel):
    nameContains: BrowseQueryTextPayload


class BrowseQueryNameNotContainsClausePayload(StrictModel):
    nameNotContains: BrowseQueryTextPayload


class BrowseQueryNotesContainsClausePayload(StrictModel):
    notesContains: BrowseQueryTextPayload


class BrowseQueryNotesNotContainsClausePayload(StrictModel):
    notesNotContains: BrowseQueryTextPayload


class BrowseQueryUrlContainsClausePayload(StrictModel):
    urlContains: BrowseQueryTextPayload


class BrowseQueryUrlNotContainsClausePayload(StrictModel):
    urlNotContains: BrowseQueryTextPayload


class BrowseQueryDateRangeClausePayload(StrictModel):
    dateRange: BrowseQueryDateRangePayload


class BrowseQueryWidthCompareClausePayload(StrictModel):
    widthCompare: BrowseQueryNumberComparePayload


class BrowseQueryHeightCompareClausePayload(StrictModel):
    heightCompare: BrowseQueryNumberComparePayload


class BrowseQueryMetricRangeClausePayload(StrictModel):
    metricRange: BrowseQueryMetricRangePayload


class BrowseQueryCategoricalInClausePayload(StrictModel):
    categoricalIn: BrowseQueryCategoricalInPayload


BrowseQueryFilterClausePayload = (
    BrowseQueryStarsInClausePayload
    | BrowseQueryStarsNotInClausePayload
    | BrowseQueryNameContainsClausePayload
    | BrowseQueryNameNotContainsClausePayload
    | BrowseQueryNotesContainsClausePayload
    | BrowseQueryNotesNotContainsClausePayload
    | BrowseQueryUrlContainsClausePayload
    | BrowseQueryUrlNotContainsClausePayload
    | BrowseQueryDateRangeClausePayload
    | BrowseQueryWidthCompareClausePayload
    | BrowseQueryHeightCompareClausePayload
    | BrowseQueryMetricRangeClausePayload
    | BrowseQueryCategoricalInClausePayload
)


class BrowseQueryFilterAstPayload(StrictModel):
    and_: list[BrowseQueryFilterClausePayload] = Field(default_factory=list, alias="and")


class BrowseQueryBuiltinSortPayload(StrictModel):
    kind: Literal["builtin"]
    key: Literal["added", "name", "random"]
    dir: BrowseQuerySortDirection = "desc"


class BrowseQueryMetricSortPayload(StrictModel):
    kind: Literal["metric"]
    key: str
    dir: BrowseQuerySortDirection = "asc"

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("metric sort key must be non-empty")
        return value


BrowseQuerySortPayload = BrowseQueryBuiltinSortPayload | BrowseQueryMetricSortPayload


class BrowseQueryDerivedMetricNumericTermPayload(StrictModel):
    key: str
    weight: float
    missing: DerivedMetricNumericMissingPolicy

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        key = value.strip()
        if not key:
            raise ValueError("derived metric numeric term key must be non-empty")
        if key.startswith(DERIVED_METRIC_KEY_PREFIX):
            raise ValueError("derived metric numeric term key cannot be another derived metric")
        return value

    @field_validator("weight")
    @classmethod
    def validate_weight(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("derived metric numeric term weight must be finite")
        return value


class BrowseQueryDerivedMetricCategoricalTermPayload(StrictModel):
    key: str
    value: str
    weight: float

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        key = value.strip()
        if not key:
            raise ValueError("derived metric categorical term key must be non-empty")
        if key.startswith(DERIVED_METRIC_KEY_PREFIX):
            raise ValueError("derived metric categorical term key cannot be another derived metric")
        return value

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("derived metric categorical term value must be non-empty")
        return value

    @field_validator("weight")
    @classmethod
    def validate_weight(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("derived metric categorical term weight must be finite")
        return value


class BrowseQueryDerivedMetricPayload(StrictModel):
    version: Literal[1]
    id: str
    name: str
    intercept: float
    numeric_terms: list[BrowseQueryDerivedMetricNumericTermPayload] = Field(default_factory=list, alias="numericTerms")
    categorical_terms: list[BrowseQueryDerivedMetricCategoricalTermPayload] = Field(
        default_factory=list,
        alias="categoricalTerms",
    )

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("derived metric id must be non-empty")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("derived metric name must be non-empty")
        return value

    @field_validator("intercept")
    @classmethod
    def validate_intercept(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("derived metric intercept must be finite")
        return value


class BrowseQueryRequest(StrictModel):
    path: str = "/"
    recursive: bool = False
    offset: int = Field(0, ge=0)
    limit: int = Field(BROWSE_QUERY_DEFAULT_LIMIT, gt=0, le=BROWSE_QUERY_MAX_LIMIT)
    filters: BrowseQueryFilterAstPayload = Field(default_factory=BrowseQueryFilterAstPayload)
    sort: BrowseQuerySortPayload = Field(
        default_factory=lambda: BrowseQueryBuiltinSortPayload(kind="builtin", key="added", dir="desc")
    )
    text_query: str | None = None
    random_seed: str | int | None = None
    derived_metric: BrowseQueryDerivedMetricPayload | None = None


class BrowseQueryResponse(BaseModel):
    version: int = 1
    path: str
    generated_at: str
    generation_token: str
    request_token: str
    scope_total: int
    filtered_total: int
    offset: int
    limit: int
    items: list[BrowseItemPayload] = Field(default_factory=list)
    folders: list[BrowseFolderEntryPayload] = Field(default_factory=list)
    metric_keys: list[str] = Field(default_factory=list)
    categorical_keys: list[str] = Field(default_factory=list)


class MetricHistogramFacetPayload(BaseModel):
    bins: list[int] = Field(default_factory=list)
    min: float
    max: float
    count: int


class MetricCategoryFacetPayload(BaseModel):
    code: float
    label: str
    population_count: int


class MetricFacetPayload(BaseModel):
    histogram: MetricHistogramFacetPayload | None = None
    categories: list[MetricCategoryFacetPayload] = Field(default_factory=list)


class CategoricalValueFacetPayload(BaseModel):
    value: str
    population_count: int


class CategoricalFacetPayload(BaseModel):
    values: list[CategoricalValueFacetPayload] = Field(default_factory=list)


class BrowseFacetsPayload(BaseModel):
    version: int = 1
    path: str
    generated_at: str
    total_items: int
    metric_keys: list[str] = Field(default_factory=list)
    categorical_keys: list[str] = Field(default_factory=list)
    metrics: dict[str, MetricFacetPayload] = Field(default_factory=dict)
    categoricals: dict[str, CategoricalFacetPayload] = Field(default_factory=dict)


class BrowseFolderPathsPayload(BaseModel):
    paths: list[str] = Field(default_factory=list)


class TableSourceColumnOptionPayload(BaseModel):
    name: str
    selected: bool = False
    sample_total: int = 0
    sample_loadable: int = 0
    sample_usable: int = 0
    warning: str | None = None


class TableSourceColumnsPayload(BaseModel):
    enabled: bool
    current: str | None = None
    columns: list[TableSourceColumnOptionPayload] = Field(default_factory=list)
    warning: str | None = None


class TableSourceColumnSwitchRequest(BaseModel):
    source_column: str


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
