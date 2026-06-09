from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
import hashlib
import json
import math
import re
from typing import Generic, Literal, Mapping, TypeVar


CompareOp = Literal["<", "<=", ">", ">="]
SortDirection = Literal["asc", "desc"]
BuiltinSortKey = Literal["added", "name", "random"]

DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_VALID_STAR_VALUES = frozenset({0, 1, 2, 3, 4, 5})


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
class BrowseQuerySpec:
    path: str
    recursive: bool
    offset: int
    limit: int
    filters: BrowseFilterAst = field(default_factory=BrowseFilterAst)
    sort: BrowseSortSpec = field(default_factory=BuiltinSortSpec)
    text_query: str | None = None
    random_seed: str | None = None


@dataclass(frozen=True, slots=True)
class BrowseQueryFolderEntry:
    name: str
    kind: Literal["branch", "leaf-real", "leaf-pointer"] = "branch"


T = TypeVar("T")


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
class BrowseQueryEvaluation(Generic[T]):
    filtered_total: int
    window: tuple[BrowseQueryRecord[T], ...]


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
) -> BrowseQueryEvaluation[T]:
    normalized = BrowseQuerySpec(
        path=spec.path,
        recursive=spec.recursive,
        offset=spec.offset,
        limit=spec.limit,
        filters=normalize_filter_ast(spec.filters),
        sort=spec.sort,
        text_query=_normalize_text(spec.text_query),
        random_seed=spec.random_seed,
    )
    searched = [
        record for record in records
        if _matches_text_query(record, normalized.text_query)
    ]
    filtered = [
        record for record in searched
        if _matches_filter_ast(record, normalized.filters)
    ]
    ordered = sort_browse_records(filtered, normalized.sort, random_seed=normalized.random_seed)
    start = max(0, normalized.offset)
    end = start + max(0, normalized.limit)
    return BrowseQueryEvaluation(
        filtered_total=len(ordered),
        window=tuple(ordered[start:end]),
    )


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
        return sorted(records, key=lambda record: (_random_key(seed, record.stable_identity), record.stable_identity))
    if sort.key == "name":
        return sorted(records, key=lambda record: _name_sort_key(record, sort.direction))
    return sorted(records, key=lambda record: _added_sort_key(record, sort.direction))


def browse_query_request_token(spec: BrowseQuerySpec) -> str:
    payload = {
        "path": spec.path,
        "recursive": spec.recursive,
        "offset": spec.offset,
        "limit": spec.limit,
        "filters": [_clause_token(clause) for clause in normalize_filter_ast(spec.filters).and_clauses],
        "sort": _sort_token(spec.sort),
        "text_query": _normalize_text(spec.text_query),
        "random_seed": spec.random_seed,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"bq_{digest}"


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
        if key is None or not math.isfinite(clause.min_value) or not math.isfinite(clause.max_value):
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


def _matches_filter_ast(record: BrowseQueryRecord[object], filters: BrowseFilterAst) -> bool:
    for clause in filters.and_clauses:
        if not _matches_clause(record, clause):
            return False
    return True


def _matches_clause(record: BrowseQueryRecord[object], clause: BrowseFilterClause) -> bool:
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
        return _matches_date_range(record.added_at, clause)
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


def _matches_date_range(value: str | None, clause: DateRangeFilter) -> bool:
    if clause.from_value is None and clause.to_value is None:
        return True
    if not value:
        return False
    try:
        item_ms = parse_query_date_bound(value, as_end=False)
        from_ms = parse_query_date_bound(clause.from_value, as_end=False)
        to_ms = parse_query_date_bound(clause.to_value, as_end=True)
    except (TypeError, ValueError):
        return False
    if item_ms is None:
        return False
    if from_ms is not None and item_ms < from_ms:
        return False
    if to_ms is not None and item_ms > to_ms:
        return False
    return True


def _matches_dimension_compare(value: int | float | None, clause: WidthCompareFilter | HeightCompareFilter) -> bool:
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


def _added_sort_key(record: BrowseQueryRecord[object], direction: SortDirection) -> tuple[float, str, str]:
    added_ms = _added_ms(record.added_at)
    if direction == "desc":
        return (-added_ms, _reverse_text_key(record.name), _reverse_text_key(record.stable_identity))
    return (added_ms, record.name, record.stable_identity)


def _name_sort_key(record: BrowseQueryRecord[object], direction: SortDirection) -> tuple[str, str]:
    if direction == "desc":
        return (_reverse_text_key(record.name), _reverse_text_key(record.stable_identity))
    return (record.name, record.stable_identity)


def _metric_sort_key(record: BrowseQueryRecord[object], sort: MetricSortSpec) -> tuple[int, float, str, str]:
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


def _reverse_text_key(value: str) -> str:
    return "".join(chr(0x10FFFF - ord(char)) for char in value)


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
        return {"metricRange": {"key": clause.key, "min": clause.min_value, "max": clause.max_value}}
    if isinstance(clause, CategoricalInFilter):
        return {"categoricalIn": {"key": clause.key, "values": list(clause.values)}}
    raise TypeError(f"unsupported filter clause: {clause!r}")


def _sort_token(sort: BrowseSortSpec) -> dict[str, object]:
    if isinstance(sort, MetricSortSpec):
        return {"kind": "metric", "key": sort.key, "dir": sort.direction}
    return {"kind": "builtin", "key": sort.key, "dir": sort.direction}
