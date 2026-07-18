from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
import hashlib
import json
import math
import re
from typing import Generic, Iterable, Literal, Mapping, TypeVar

from ..diagnostics import request_phase


CompareOp = Literal["<", "<=", ">", ">="]
SortDirection = Literal["asc", "desc"]
BuiltinSortKey = Literal["added", "name", "random"]

DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_VALID_STAR_VALUES = frozenset({0, 1, 2, 3, 4, 5})
DERIVED_METRIC_PREFIX = "@derived/"
DERIVED_METRIC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
DerivedMetricNumericMissingPolicy = Literal["zero", "invalid"]
DerivedMetricStatusKind = Literal["none", "applied", "unavailable", "invalid"]
DerivedMetricScoreScope = Literal["none", "query_filtered"]
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class DescendingTextSortKey:
    """Preserve descending text order without constructing complemented strings."""

    value: str

    def __lt__(self, other: DescendingTextSortKey) -> bool:
        for left, right in zip(self.value, other.value):
            if left != right:
                return left > right
        return len(self.value) < len(other.value)


@dataclass(frozen=True, slots=True)
class StarsInFilter:
    values: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class StarsNotInFilter:
    values: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class NameContainsFilter:
    value: str


@dataclass(frozen=True, slots=True)
class NameNotContainsFilter:
    value: str


@dataclass(frozen=True, slots=True)
class NotesContainsFilter:
    value: str


@dataclass(frozen=True, slots=True)
class NotesNotContainsFilter:
    value: str


@dataclass(frozen=True, slots=True)
class UrlContainsFilter:
    value: str


@dataclass(frozen=True, slots=True)
class UrlNotContainsFilter:
    value: str


@dataclass(frozen=True, slots=True)
class DateRangeFilter:
    from_value: str | None = None
    to_value: str | None = None


@dataclass(frozen=True, slots=True)
class WidthCompareFilter:
    op: CompareOp
    value: float


@dataclass(frozen=True, slots=True)
class HeightCompareFilter:
    op: CompareOp
    value: float


@dataclass(frozen=True, slots=True)
class MetricRangeFilter:
    key: str
    min_value: float
    max_value: float


@dataclass(frozen=True, slots=True)
class CategoricalInFilter:
    key: str
    values: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DerivedMetricNumericTerm:
    key: str
    weight: float
    missing: DerivedMetricNumericMissingPolicy
    z_normalize: bool = False


@dataclass(frozen=True, slots=True)
class DerivedMetricCategoricalTerm:
    key: str
    value: str
    weight: float


@dataclass(frozen=True, slots=True)
class DerivedMetricSpec:
    id: str
    name: str
    intercept: float
    numeric_terms: tuple[DerivedMetricNumericTerm, ...] = ()
    categorical_terms: tuple[DerivedMetricCategoricalTerm, ...] = ()


@dataclass(frozen=True, slots=True)
class DerivedMetricZStat:
    mean: float
    std: float
    count: int


@dataclass(frozen=True, slots=True)
class DerivedMetricStatus:
    key: str | None = None
    display_name: str | None = None
    status: DerivedMetricStatusKind = "none"
    score_scope: DerivedMetricScoreScope = "none"
    score_population_count: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    missing_numeric_inputs: tuple[str, ...] = ()
    unavailable_categorical_inputs: tuple[str, ...] = ()
    z_stats: Mapping[str, DerivedMetricZStat] = field(default_factory=dict)


BrowseFilterClause = (
    StarsInFilter
    | StarsNotInFilter
    | NameContainsFilter
    | NameNotContainsFilter
    | NotesContainsFilter
    | NotesNotContainsFilter
    | UrlContainsFilter
    | UrlNotContainsFilter
    | DateRangeFilter
    | WidthCompareFilter
    | HeightCompareFilter
    | MetricRangeFilter
    | CategoricalInFilter
)


@dataclass(frozen=True, slots=True)
class BrowseFilterAst:
    and_clauses: tuple[BrowseFilterClause, ...] = ()


@dataclass(frozen=True, slots=True)
class BuiltinSortSpec:
    key: BuiltinSortKey = "added"
    direction: SortDirection = "desc"


@dataclass(frozen=True, slots=True)
class MetricSortSpec:
    key: str
    direction: SortDirection = "asc"


BrowseSortSpec = BuiltinSortSpec | MetricSortSpec


@dataclass(frozen=True, slots=True)
class BrowseWindowProjection:
    metric_keys: tuple[str, ...] = ()
    categorical_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BrowseFacetFields:
    metric_keys: tuple[str, ...] = ()
    categorical_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BrowseQuerySpec:
    path: str
    recursive: bool
    offset: int
    limit: int
    filters: BrowseFilterAst = field(default_factory=BrowseFilterAst)
    sort: BrowseSortSpec = field(default_factory=BuiltinSortSpec)
    text_query: str | None = None
    random_seed: str | None = None
    derived_metric: DerivedMetricSpec | None = None
    unsupported_metric_intent: str | None = None
    projection: BrowseWindowProjection = field(default_factory=BrowseWindowProjection)
    facet_fields: BrowseFacetFields | None = None


@dataclass(frozen=True, slots=True)
class QueryDependencyManifest:
    fields: frozenset[str] = frozenset()
    metric_keys: frozenset[str] = frozenset()
    categorical_keys: frozenset[str] = frozenset()
    unknown: bool = False


@dataclass(frozen=True, slots=True)
class BrowseQueryFolderEntry:
    name: str
    kind: Literal["branch", "leaf-real", "leaf-pointer"] = "branch"


@dataclass(frozen=True, slots=True)
class BrowseQueryRecord(Generic[T]):
    payload: T
    stable_identity: str
    path: str
    name: str
    added_at: str | None = None
    width: int | float | None = None
    height: int | float | None = None
    source: str | None = None
    url: str | None = None
    metrics: Mapping[str, object] | None = None
    categoricals: Mapping[str, str] | None = None
    star: int | None = None
    notes: str | None = None
    search_text: str = ""


@dataclass(frozen=True, slots=True)
class DerivedMetricApplyResult(Generic[T]):
    records: list[BrowseQueryRecord[T]]
    status: DerivedMetricStatus


@dataclass(frozen=True, slots=True)
class BrowseQueryEvaluation(Generic[T]):
    filtered_total: int
    window: tuple[BrowseQueryRecord[T], ...]
    derived_metric_status: DerivedMetricStatus = field(default_factory=DerivedMetricStatus)


@dataclass(frozen=True, slots=True)
class BrowseQueryResult(Generic[T]):
    path: str
    generated_at: str
    generation_token: str
    request_token: str
    scope_total: int
    filtered_total: int
    offset: int
    limit: int
    items: tuple[T, ...]
    folders: tuple[BrowseQueryFolderEntry, ...] = ()
    metric_keys: tuple[str, ...] = ()
    categorical_keys: tuple[str, ...] = ()
    derived_metric_status: DerivedMetricStatus = field(default_factory=DerivedMetricStatus)


def normalize_filter_ast(ast: BrowseFilterAst) -> BrowseFilterAst:
    clauses = tuple(
        clause
        for clause in (_normalize_clause(clause) for clause in ast.and_clauses)
        if clause is not None
    )
    return BrowseFilterAst(and_clauses=clauses)


def evaluate_browse_records(
    records: tuple[BrowseQueryRecord[T], ...] | list[BrowseQueryRecord[T]],
    spec: BrowseQuerySpec,
    *,
    metric_keys: Iterable[str] | None = None,
    categorical_keys: Iterable[str] | None = None,
) -> BrowseQueryEvaluation[T]:
    with request_phase("analysis"):
        normalized = BrowseQuerySpec(
            path=spec.path,
            recursive=spec.recursive,
            offset=spec.offset,
            limit=spec.limit,
            filters=normalize_filter_ast(spec.filters),
            sort=spec.sort,
            text_query=_normalize_text(spec.text_query),
            random_seed=spec.random_seed,
            derived_metric=normalize_derived_metric_spec(spec.derived_metric),
            unsupported_metric_intent=_normalize_text(spec.unsupported_metric_intent),
        )
        date_bounds = _prepare_date_bounds(normalized.filters)
        searched = [
            record for record in records if _matches_text_query(record, normalized.text_query)
        ]
        base_filters, derived_filters = _split_derived_metric_filters(normalized.filters)
        base_filtered = [
            record for record in searched if _matches_filter_ast(record, base_filters, date_bounds)
        ]
        derived_metric_status = DerivedMetricStatus()
        if normalized.derived_metric is not None or _query_references_derived_metric(normalized):
            derived_result = evaluate_derived_metric_for_records(
                base_filtered,
                normalized.derived_metric,
                metric_keys=metric_keys,
                categorical_keys=categorical_keys,
            )
            query_records = derived_result.records
            derived_metric_status = derived_result.status
        else:
            query_records = base_filtered
        filtered = [
            record
            for record in query_records
            if _matches_filter_ast(record, derived_filters, date_bounds)
        ]
    with request_phase("ordering"):
        ordered = sort_browse_records(filtered, normalized.sort, random_seed=normalized.random_seed)
    with request_phase("projection"):
        start = max(0, normalized.offset)
        end = start + max(0, normalized.limit)
        window = tuple(ordered[start:end])
    return BrowseQueryEvaluation(
        filtered_total=len(ordered),
        window=window,
        derived_metric_status=derived_metric_status,
    )


def evaluate_derived_metric_for_records(
    records: tuple[BrowseQueryRecord[T], ...] | list[BrowseQueryRecord[T]],
    spec: DerivedMetricSpec | None,
    *,
    metric_keys: Iterable[str] | None = None,
    categorical_keys: Iterable[str] | None = None,
) -> DerivedMetricApplyResult[T]:
    stripped = [_record_without_derived_metrics(record) for record in records]
    score_population_count = len(stripped)
    raw_spec = spec
    spec = normalize_derived_metric_spec(raw_spec)
    if raw_spec is None:
        return DerivedMetricApplyResult(records=stripped, status=DerivedMetricStatus())
    if spec is None:
        raw_id = _normalize_text(raw_spec.id)
        raw_name = _normalize_text(raw_spec.name)
        return DerivedMetricApplyResult(
            records=stripped,
            status=DerivedMetricStatus(
                key=(
                    derived_metric_key(raw_id)
                    if raw_id and DERIVED_METRIC_ID_RE.fullmatch(raw_id)
                    else None
                ),
                display_name=raw_name,
                status="invalid",
                score_population_count=score_population_count,
                invalid_count=score_population_count,
            ),
        )

    key = derived_metric_key(spec)
    missing_numeric, missing_categorical = _missing_derived_metric_inputs(
        stripped,
        spec,
        metric_keys=metric_keys,
        categorical_keys=categorical_keys,
    )
    if missing_numeric or missing_categorical:
        return DerivedMetricApplyResult(
            records=stripped,
            status=DerivedMetricStatus(
                key=key,
                display_name=spec.name,
                status="unavailable",
                score_scope="query_filtered",
                score_population_count=score_population_count,
                valid_count=0,
                invalid_count=score_population_count,
                missing_numeric_inputs=missing_numeric,
                unavailable_categorical_inputs=missing_categorical,
            ),
        )

    z_stats = _derived_metric_z_stats(stripped, spec)
    out: list[BrowseQueryRecord[T]] = []
    valid_count = 0
    invalid_count = 0
    for record in stripped:
        score = _derived_metric_score(record, spec, z_stats)
        if score is None:
            invalid_count += 1
            out.append(record)
            continue
        valid_count += 1
        metrics = dict(record.metrics or {})
        metrics[key] = score
        out.append(_record_with_metrics(record, metrics))
    return DerivedMetricApplyResult(
        records=out,
        status=DerivedMetricStatus(
            key=key,
            display_name=spec.name,
            status="applied",
            score_scope="query_filtered",
            score_population_count=score_population_count,
            valid_count=valid_count,
            invalid_count=invalid_count,
            z_stats=z_stats,
        ),
    )


def apply_derived_metric_to_records(
    records: tuple[BrowseQueryRecord[T], ...] | list[BrowseQueryRecord[T]],
    spec: DerivedMetricSpec | None,
    *,
    metric_keys: Iterable[str] | None = None,
    categorical_keys: Iterable[str] | None = None,
) -> list[BrowseQueryRecord[T]]:
    return evaluate_derived_metric_for_records(
        records,
        spec,
        metric_keys=metric_keys,
        categorical_keys=categorical_keys,
    ).records


def derived_metric_key(spec: DerivedMetricSpec | str) -> str:
    metric_id = spec if isinstance(spec, str) else spec.id
    return f"{DERIVED_METRIC_PREFIX}{metric_id}"


def is_derived_metric_key(key: str | None) -> bool:
    return (
        isinstance(key, str)
        and key.startswith(DERIVED_METRIC_PREFIX)
        and len(key) > len(DERIVED_METRIC_PREFIX)
    )


def normalize_derived_metric_spec(spec: DerivedMetricSpec | None) -> DerivedMetricSpec | None:
    if spec is None:
        return None
    metric_id = spec.id.strip()
    if not DERIVED_METRIC_ID_RE.fullmatch(metric_id):
        return None
    if not math.isfinite(spec.intercept):
        return None
    numeric_terms: list[DerivedMetricNumericTerm] = []
    for term in spec.numeric_terms:
        key = _normalize_text(term.key)
        if key is None or is_derived_metric_key(key):
            return None
        if not math.isfinite(term.weight) or term.missing not in {"zero", "invalid"}:
            return None
        numeric_terms.append(
            DerivedMetricNumericTerm(
                key=key,
                weight=term.weight,
                missing=term.missing,
                z_normalize=term.z_normalize,
            )
        )
    categorical_terms: list[DerivedMetricCategoricalTerm] = []
    for term in spec.categorical_terms:
        key = _normalize_text(term.key)
        value = _normalize_text(term.value)
        if key is None or value is None or is_derived_metric_key(key):
            return None
        if not math.isfinite(term.weight):
            return None
        categorical_terms.append(
            DerivedMetricCategoricalTerm(key=key, value=value, weight=term.weight)
        )
    name = spec.name.strip() or "Derived score"
    return DerivedMetricSpec(
        id=metric_id,
        name=name,
        intercept=spec.intercept,
        numeric_terms=tuple(numeric_terms),
        categorical_terms=tuple(categorical_terms),
    )


def query_dependency_manifest(
    spec: BrowseQuerySpec,
    *,
    facet_metric_keys: Iterable[str] = (),
    facet_categorical_keys: Iterable[str] = (),
) -> QueryDependencyManifest:
    """Return mutation dependencies for one normalized browse analysis."""
    fields: set[str] = set()
    metric_keys = {key for key in facet_metric_keys if key}
    categorical_keys = {key for key in facet_categorical_keys if key}
    unknown = bool(_normalize_text(spec.unsupported_metric_intent))

    for clause in normalize_filter_ast(spec.filters).and_clauses:
        if isinstance(clause, (StarsInFilter, StarsNotInFilter)):
            fields.add("star")
        elif isinstance(clause, (NameContainsFilter, NameNotContainsFilter)):
            fields.add("name")
        elif isinstance(clause, (NotesContainsFilter, NotesNotContainsFilter)):
            fields.add("notes")
        elif isinstance(clause, (UrlContainsFilter, UrlNotContainsFilter)):
            fields.update(("source", "url"))
        elif isinstance(clause, DateRangeFilter):
            fields.add("added_at")
        elif isinstance(clause, WidthCompareFilter):
            fields.add("width")
        elif isinstance(clause, HeightCompareFilter):
            fields.add("height")
        elif isinstance(clause, MetricRangeFilter):
            metric_keys.add(clause.key)
        elif isinstance(clause, CategoricalInFilter):
            categorical_keys.add(clause.key)
        else:
            unknown = True

    if _normalize_text(spec.text_query):
        fields.update(("name", "path", "tags", "notes", "source", "url"))

    if isinstance(spec.sort, BuiltinSortSpec):
        if spec.sort.key == "added":
            fields.add("added_at")
        elif spec.sort.key == "name":
            fields.add("name")
        elif spec.sort.key != "random":
            unknown = True
    elif isinstance(spec.sort, MetricSortSpec):
        metric_keys.add(spec.sort.key)
    else:
        unknown = True

    derived = normalize_derived_metric_spec(spec.derived_metric)
    if spec.derived_metric is not None and derived is None:
        unknown = True
    if derived is not None:
        metric_keys.update(term.key for term in derived.numeric_terms)
        categorical_keys.update(term.key for term in derived.categorical_terms)

    return QueryDependencyManifest(
        fields=frozenset(fields),
        metric_keys=frozenset(metric_keys),
        categorical_keys=frozenset(categorical_keys),
        unknown=unknown,
    )


def _record_with_metrics(
    record: BrowseQueryRecord[T],
    metrics: Mapping[str, object] | None,
) -> BrowseQueryRecord[T]:
    return BrowseQueryRecord(
        payload=record.payload,
        stable_identity=record.stable_identity,
        path=record.path,
        name=record.name,
        added_at=record.added_at,
        width=record.width,
        height=record.height,
        source=record.source,
        url=record.url,
        metrics=metrics,
        categoricals=record.categoricals,
        star=record.star,
        notes=record.notes,
        search_text=record.search_text,
    )


def _record_without_derived_metrics(record: BrowseQueryRecord[T]) -> BrowseQueryRecord[T]:
    metrics = record.metrics
    if not metrics:
        return record
    if not any(is_derived_metric_key(key) for key in metrics):
        return record
    filtered = {key: value for key, value in metrics.items() if not is_derived_metric_key(key)}
    return _record_with_metrics(record, filtered or None)


def _missing_derived_metric_inputs(
    records: list[BrowseQueryRecord[T]],
    spec: DerivedMetricSpec,
    *,
    metric_keys: Iterable[str] | None,
    categorical_keys: Iterable[str] | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    available_metrics = (
        _available_metric_keys(records) if metric_keys is None else _normalized_key_set(metric_keys)
    )
    available_categoricals = (
        _available_categorical_keys(records)
        if categorical_keys is None
        else _normalized_key_set(categorical_keys)
    )
    missing_metrics: set[str] = set()
    missing_categoricals: set[str] = set()
    for term in spec.numeric_terms:
        if term.key not in available_metrics:
            missing_metrics.add(term.key)
    for term in spec.categorical_terms:
        if term.key not in available_categoricals:
            missing_categoricals.add(term.key)
    return tuple(sorted(missing_metrics)), tuple(sorted(missing_categoricals))


def _normalized_key_set(values: Iterable[str]) -> set[str]:
    keys: set[str] = set()
    for value in values:
        key = _normalize_text(value)
        if key is not None and not is_derived_metric_key(key):
            keys.add(key)
    return keys


def _available_metric_keys(records: list[BrowseQueryRecord[T]]) -> set[str]:
    keys: set[str] = set()
    for record in records:
        for key in record.metrics or {}:
            normalized = _normalize_text(key)
            if normalized is not None and not is_derived_metric_key(normalized):
                keys.add(normalized)
    return keys


def _available_categorical_keys(records: list[BrowseQueryRecord[T]]) -> set[str]:
    keys: set[str] = set()
    for record in records:
        for key in record.categoricals or {}:
            normalized = _normalize_text(key)
            if normalized is not None:
                keys.add(normalized)
    return keys


def _derived_metric_z_stats(
    records: list[BrowseQueryRecord[T]],
    spec: DerivedMetricSpec,
) -> dict[str, DerivedMetricZStat]:
    z_keys = {term.key for term in spec.numeric_terms if term.z_normalize}
    if not z_keys:
        return {}
    sums = {key: 0.0 for key in z_keys}
    sums_sq = {key: 0.0 for key in z_keys}
    counts = {key: 0 for key in z_keys}
    for record in records:
        metrics = record.metrics or {}
        for key in z_keys:
            value = _finite_number(metrics.get(key))
            if value is None:
                continue
            sums[key] += value
            sums_sq[key] += value * value
            counts[key] += 1

    stats: dict[str, DerivedMetricZStat] = {}
    for key in z_keys:
        count = counts[key]
        if count <= 0:
            continue
        mean = sums[key] / count
        variance = max(0.0, (sums_sq[key] / count) - (mean * mean))
        stats[key] = DerivedMetricZStat(mean=mean, std=math.sqrt(variance), count=count)
    return stats


def _derived_metric_score(
    record: BrowseQueryRecord[object],
    spec: DerivedMetricSpec,
    z_stats: Mapping[str, DerivedMetricZStat],
) -> float | None:
    score = spec.intercept
    metrics = record.metrics or {}
    for term in spec.numeric_terms:
        value = _finite_number(metrics.get(term.key))
        if value is None:
            if term.missing == "invalid":
                return None
            continue
        if term.z_normalize:
            stats = z_stats.get(term.key)
            value = 0.0 if stats is None or stats.std <= 0 else (value - stats.mean) / stats.std
        score += value * term.weight
    categoricals = record.categoricals or {}
    for term in spec.categorical_terms:
        if categoricals.get(term.key) == term.value:
            score += term.weight
    return _finite_number(score)


def _query_references_derived_metric(spec: BrowseQuerySpec) -> bool:
    if isinstance(spec.sort, MetricSortSpec) and is_derived_metric_key(spec.sort.key):
        return True
    for clause in spec.filters.and_clauses:
        if isinstance(clause, MetricRangeFilter) and is_derived_metric_key(clause.key):
            return True
    return False


def _split_derived_metric_filters(
    filters: BrowseFilterAst,
) -> tuple[BrowseFilterAst, BrowseFilterAst]:
    base: list[BrowseFilterClause] = []
    derived: list[BrowseFilterClause] = []
    for clause in filters.and_clauses:
        if isinstance(clause, MetricRangeFilter) and is_derived_metric_key(clause.key):
            derived.append(clause)
        else:
            base.append(clause)
    return BrowseFilterAst(tuple(base)), BrowseFilterAst(tuple(derived))


def sort_browse_records(
    records: list[BrowseQueryRecord[T]] | tuple[BrowseQueryRecord[T], ...],
    sort: BrowseSortSpec,
    *,
    random_seed: str | None = None,
) -> list[BrowseQueryRecord[T]]:
    if isinstance(sort, MetricSortSpec):
        return sorted(records, key=lambda record: _metric_sort_key(record, sort))
    if sort.key == "random":
        seed = str(random_seed if random_seed is not None else "")
        return sorted(
            records,
            key=lambda record: (_random_key(seed, record.stable_identity), record.stable_identity),
        )
    if sort.key == "name":
        key = _descending_name_sort_key if sort.direction == "desc" else _name_sort_key
        return sorted(records, key=key)
    key = _descending_added_sort_key if sort.direction == "desc" else _added_sort_key
    return sorted(records, key=key)


def browse_analysis_query_key(
    spec: BrowseQuerySpec,
    *,
    unsupported_metric_intent: str | None = None,
) -> str:
    return _query_payload_token(
        "aq",
        _analysis_query_payload(spec, unsupported_metric_intent=unsupported_metric_intent),
    )


def browse_filter_query_key(spec: BrowseQuerySpec) -> str:
    """Return the semantic identity of filtering and derived-score work."""

    return _query_payload_token("fq", _filter_query_payload(spec))


def browse_order_query_key(spec: BrowseQuerySpec) -> str:
    """Return the semantic identity of filtering plus ordering work."""

    return _query_payload_token(
        "oq",
        {
            "filter_query_key": browse_filter_query_key(spec),
            "sort": _sort_token(spec.sort),
            "random_seed": _active_random_seed_token(spec),
        },
    )


def browse_window_request_token(
    spec: BrowseQuerySpec,
    *,
    generation_token: str | None = None,
    unsupported_metric_intent: str | None = None,
) -> str:
    payload: dict[str, object] = {
        "analysis_query_key": browse_analysis_query_key(
            spec,
            unsupported_metric_intent=unsupported_metric_intent,
        ),
        "offset": spec.offset,
        "limit": spec.limit,
        "projection": {
            "metric_keys": sorted(dict.fromkeys(spec.projection.metric_keys)),
            "categorical_keys": sorted(dict.fromkeys(spec.projection.categorical_keys)),
        },
    }
    if generation_token is not None:
        payload["generation_token"] = generation_token
    return _query_payload_token("bq", payload)


def browse_query_request_token(spec: BrowseQuerySpec) -> str:
    return browse_window_request_token(spec)


def browse_facet_request_token(spec: BrowseQuerySpec) -> str:
    fields = spec.facet_fields
    return _query_payload_token(
        "bf",
        {
            "analysis_query_key": browse_analysis_query_key(spec),
            "facet_fields": None if fields is None else {
                "metric_keys": sorted(dict.fromkeys(fields.metric_keys)),
                "categorical_keys": sorted(dict.fromkeys(fields.categorical_keys)),
            },
        },
    )


def _query_payload_token(prefix: str, payload: Mapping[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _analysis_query_payload(
    spec: BrowseQuerySpec,
    *,
    unsupported_metric_intent: str | None = None,
) -> dict[str, object]:
    unsupported_intent = _normalize_text(
        unsupported_metric_intent
        if unsupported_metric_intent is not None
        else spec.unsupported_metric_intent
    )
    payload = {
        "path": spec.path,
        "recursive": spec.recursive,
        **_filter_query_payload(spec),
        "sort": _sort_token(spec.sort),
        "random_seed": _active_random_seed_token(spec),
        "unsupported_metric_intent": unsupported_intent,
    }
    return payload


def _filter_query_payload(spec: BrowseQuerySpec) -> dict[str, object]:
    return {
        "path": spec.path,
        "recursive": spec.recursive,
        "filters": [
            _clause_token(clause) for clause in normalize_filter_ast(spec.filters).and_clauses
        ],
        "text_query": _normalize_text(spec.text_query),
        "derived_metric": _derived_metric_token(spec.derived_metric),
        "unsupported_metric_intent": _normalize_text(spec.unsupported_metric_intent),
    }


def _active_random_seed_token(spec: BrowseQuerySpec) -> str | None:
    if not isinstance(spec.sort, BuiltinSortSpec) or spec.sort.key != "random":
        return None
    if spec.random_seed is None:
        return None
    return str(spec.random_seed)


def parse_query_date_bound(value: str | None, *, as_end: bool) -> float | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    if DATE_ONLY_RE.match(normalized):
        parsed_date = date.fromisoformat(normalized)
        parsed_dt = datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)
        timestamp_ms = parsed_dt.timestamp() * 1000.0
        if as_end:
            return timestamp_ms + 24 * 60 * 60 * 1000 - 1
        return timestamp_ms
    normalized = normalized.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp() * 1000.0


def _normalize_clause(clause: BrowseFilterClause) -> BrowseFilterClause | None:
    if isinstance(clause, (StarsInFilter, StarsNotInFilter)):
        values = _normalize_star_values(clause.values)
        if not values:
            return None
        return type(clause)(values=values)
    if isinstance(
        clause,
        (
            NameContainsFilter,
            NameNotContainsFilter,
            NotesContainsFilter,
            NotesNotContainsFilter,
            UrlContainsFilter,
            UrlNotContainsFilter,
        ),
    ):
        value = _normalize_text(clause.value)
        if value is None:
            return None
        return type(clause)(value=value)
    if isinstance(clause, DateRangeFilter):
        from_value = _normalize_text(clause.from_value)
        to_value = _normalize_text(clause.to_value)
        if from_value is None and to_value is None:
            return None
        return DateRangeFilter(from_value=from_value, to_value=to_value)
    if isinstance(clause, (WidthCompareFilter, HeightCompareFilter)):
        if not math.isfinite(clause.value):
            return None
        return clause
    if isinstance(clause, MetricRangeFilter):
        key = _normalize_text(clause.key)
        if (
            key is None
            or not math.isfinite(clause.min_value)
            or not math.isfinite(clause.max_value)
        ):
            return None
        if clause.min_value > clause.max_value:
            return None
        return MetricRangeFilter(key=key, min_value=clause.min_value, max_value=clause.max_value)
    if isinstance(clause, CategoricalInFilter):
        key = _normalize_text(clause.key)
        values = _normalize_categorical_values(clause.values)
        if key is None or not values:
            return None
        return CategoricalInFilter(key=key, values=values)
    return clause


def _matches_filter_ast(
    record: BrowseQueryRecord[object],
    filters: BrowseFilterAst,
    date_bounds: Mapping[
        DateRangeFilter,
        tuple[float | None, float | None] | None,
    ],
) -> bool:
    for clause in filters.and_clauses:
        if not _matches_clause(record, clause, date_bounds):
            return False
    return True


def _matches_clause(
    record: BrowseQueryRecord[object],
    clause: BrowseFilterClause,
    date_bounds: Mapping[
        DateRangeFilter,
        tuple[float | None, float | None] | None,
    ],
) -> bool:
    if isinstance(clause, StarsInFilter):
        value = record.star if record.star is not None else 0
        return value in clause.values
    if isinstance(clause, StarsNotInFilter):
        value = record.star if record.star is not None else 0
        return value not in clause.values
    if isinstance(clause, NameContainsFilter):
        return _matches_text_value(record.name, clause.value)
    if isinstance(clause, NameNotContainsFilter):
        return not _matches_text_value(record.name, clause.value)
    if isinstance(clause, NotesContainsFilter):
        return _matches_notes_contains(record, clause.value)
    if isinstance(clause, NotesNotContainsFilter):
        return _matches_notes_not_contains(record, clause.value)
    if isinstance(clause, UrlContainsFilter):
        return _matches_url_contains(record, clause.value)
    if isinstance(clause, UrlNotContainsFilter):
        return _matches_url_not_contains(record, clause.value)
    if isinstance(clause, DateRangeFilter):
        return _matches_date_range(record.added_at, date_bounds[clause])
    if isinstance(clause, WidthCompareFilter):
        return _matches_dimension_compare(record.width, clause)
    if isinstance(clause, HeightCompareFilter):
        return _matches_dimension_compare(record.height, clause)
    if isinstance(clause, MetricRangeFilter):
        value = _finite_number((record.metrics or {}).get(clause.key))
        return value is not None and clause.min_value <= value <= clause.max_value
    if isinstance(clause, CategoricalInFilter):
        raw = (record.categoricals or {}).get(clause.key)
        if not raw:
            return False
        return raw in clause.values
    return True


def _matches_notes_contains(record: BrowseQueryRecord[object], needle: str) -> bool:
    notes = record.notes or ""
    if not notes:
        return False
    return needle.lower() in notes.lower()


def _matches_notes_not_contains(record: BrowseQueryRecord[object], needle: str) -> bool:
    notes = record.notes or ""
    if not notes:
        return False
    return needle.lower() not in notes.lower()


def _matches_url_contains(record: BrowseQueryRecord[object], needle: str) -> bool:
    url = record.source if record.source is not None else record.url
    if not url:
        return False
    return needle.lower() in url.lower()


def _matches_url_not_contains(record: BrowseQueryRecord[object], needle: str) -> bool:
    url = record.source if record.source is not None else record.url
    if not url:
        return False
    return needle.lower() not in url.lower()


def _matches_text_query(record: BrowseQueryRecord[object], text_query: str | None) -> bool:
    if text_query is None:
        return True
    return text_query.lower() in record.search_text.lower()


def _matches_text_value(value: str | None, needle: str) -> bool:
    return needle.lower() in (value or "").lower()


def _prepare_date_bounds(
    filters: BrowseFilterAst,
) -> dict[DateRangeFilter, tuple[float | None, float | None] | None]:
    bounds: dict[DateRangeFilter, tuple[float | None, float | None] | None] = {}
    for clause in filters.and_clauses:
        if not isinstance(clause, DateRangeFilter) or clause in bounds:
            continue
        try:
            bounds[clause] = (
                parse_query_date_bound(clause.from_value, as_end=False),
                parse_query_date_bound(clause.to_value, as_end=True),
            )
        except (TypeError, ValueError):
            bounds[clause] = None
    return bounds


def _matches_date_range(
    value: str | None,
    bounds: tuple[float | None, float | None] | None,
) -> bool:
    if bounds is None:
        return False
    from_ms, to_ms = bounds
    if from_ms is None and to_ms is None:
        return True
    if not value:
        return False
    try:
        item_ms = parse_query_date_bound(value, as_end=False)
    except (TypeError, ValueError):
        return False
    if item_ms is None:
        return False
    if from_ms is not None and item_ms < from_ms:
        return False
    if to_ms is not None and item_ms > to_ms:
        return False
    return True


def _matches_dimension_compare(
    value: int | float | None, clause: WidthCompareFilter | HeightCompareFilter
) -> bool:
    number = _finite_number(value)
    if number is None or number <= 0:
        return False
    if clause.op == "<":
        return number < clause.value
    if clause.op == "<=":
        return number <= clause.value
    if clause.op == ">":
        return number > clause.value
    if clause.op == ">=":
        return number >= clause.value
    return True


def _added_sort_key(record: BrowseQueryRecord[object]) -> tuple[float, str, str]:
    added_ms = _added_ms(record.added_at)
    return (added_ms, record.name, record.stable_identity)


def _descending_added_sort_key(
    record: BrowseQueryRecord[object],
) -> tuple[float, DescendingTextSortKey, DescendingTextSortKey]:
    return (
        -_added_ms(record.added_at),
        DescendingTextSortKey(record.name),
        DescendingTextSortKey(record.stable_identity),
    )


def _name_sort_key(record: BrowseQueryRecord[object]) -> tuple[str, str]:
    return (record.name, record.stable_identity)


def _descending_name_sort_key(
    record: BrowseQueryRecord[object],
) -> tuple[DescendingTextSortKey, DescendingTextSortKey]:
    return (
        DescendingTextSortKey(record.name),
        DescendingTextSortKey(record.stable_identity),
    )


def _metric_sort_key(
    record: BrowseQueryRecord[object], sort: MetricSortSpec
) -> tuple[int, float, str, str]:
    value = _finite_number((record.metrics or {}).get(sort.key))
    if value is None:
        return (1, 0.0, record.name, record.stable_identity)
    ordered_value = -value if sort.direction == "desc" else value
    return (0, ordered_value, record.name, record.stable_identity)


def _random_key(seed: str, stable_identity: str) -> int:
    digest = hashlib.sha256(f"{seed}\0{stable_identity}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def _added_ms(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return parse_query_date_bound(value, as_end=False) or 0.0
    except (TypeError, ValueError):
        return 0.0


def _finite_number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _normalize_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _normalize_star_values(values: tuple[int, ...]) -> tuple[int, ...]:
    out: list[int] = []
    seen: set[int] = set()
    for value in values:
        if value in _VALID_STAR_VALUES and value not in seen:
            seen.add(value)
            out.append(value)
    return tuple(out)


def _normalize_categorical_values(values: tuple[str, ...]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = raw.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return tuple(out)


def _clause_token(clause: BrowseFilterClause) -> dict[str, object]:
    if isinstance(clause, StarsInFilter):
        return {"starsIn": {"values": list(clause.values)}}
    if isinstance(clause, StarsNotInFilter):
        return {"starsNotIn": {"values": list(clause.values)}}
    if isinstance(clause, NameContainsFilter):
        return {"nameContains": {"value": clause.value}}
    if isinstance(clause, NameNotContainsFilter):
        return {"nameNotContains": {"value": clause.value}}
    if isinstance(clause, NotesContainsFilter):
        return {"notesContains": {"value": clause.value}}
    if isinstance(clause, NotesNotContainsFilter):
        return {"notesNotContains": {"value": clause.value}}
    if isinstance(clause, UrlContainsFilter):
        return {"urlContains": {"value": clause.value}}
    if isinstance(clause, UrlNotContainsFilter):
        return {"urlNotContains": {"value": clause.value}}
    if isinstance(clause, DateRangeFilter):
        return {"dateRange": {"from": clause.from_value, "to": clause.to_value}}
    if isinstance(clause, WidthCompareFilter):
        return {"widthCompare": {"op": clause.op, "value": clause.value}}
    if isinstance(clause, HeightCompareFilter):
        return {"heightCompare": {"op": clause.op, "value": clause.value}}
    if isinstance(clause, MetricRangeFilter):
        return {
            "metricRange": {"key": clause.key, "min": clause.min_value, "max": clause.max_value}
        }
    if isinstance(clause, CategoricalInFilter):
        return {"categoricalIn": {"key": clause.key, "values": list(clause.values)}}
    raise TypeError(f"unsupported filter clause: {clause!r}")


def _sort_token(sort: BrowseSortSpec) -> dict[str, object]:
    if isinstance(sort, MetricSortSpec):
        return {"kind": "metric", "key": sort.key, "dir": sort.direction}
    return {"kind": "builtin", "key": sort.key, "dir": sort.direction}


def _derived_metric_token(spec: DerivedMetricSpec | None) -> dict[str, object] | None:
    normalized = normalize_derived_metric_spec(spec)
    if normalized is None:
        return None
    return {
        "version": 1,
        "id": normalized.id,
        "name": normalized.name,
        "intercept": normalized.intercept,
        "numericTerms": [
            {
                "key": term.key,
                "weight": term.weight,
                "missing": term.missing,
                "zNormalize": term.z_normalize,
            }
            for term in normalized.numeric_terms
        ],
        "categoricalTerms": [
            {"key": term.key, "value": term.value, "weight": term.weight}
            for term in normalized.categorical_terms
        ],
    }
