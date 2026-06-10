from __future__ import annotations

from collections import deque

from fastapi import FastAPI, Query, Request

from ...browse.query import (
    BrowseFilterAst,
    BrowseFilterClause,
    BrowseQuerySpec,
    BuiltinSortSpec,
    CategoricalInFilter,
    DateRangeFilter,
    DerivedMetricCategoricalTerm,
    DerivedMetricNumericTerm,
    DerivedMetricSpec,
    HeightCompareFilter,
    MetricRangeFilter,
    MetricSortSpec,
    NameContainsFilter,
    NameNotContainsFilter,
    NotesContainsFilter,
    NotesNotContainsFilter,
    StarsInFilter,
    StarsNotInFilter,
    UrlContainsFilter,
    UrlNotContainsFilter,
    WidthCompareFilter,
)
from ..browse import (
    RECURSIVE_WINDOW_MAX_LIMIT,
    ToItemFn,
    build_folder_facets,
    build_folder_index,
    build_folder_query,
    storage_from_request,
)
from ..context import get_request_context
from ..models import (
    BrowseFacetsPayload,
    BrowseFolderPathsPayload,
    BrowseFolderPayload,
    BrowseQueryCategoricalInClausePayload,
    BrowseQueryDateRangeClausePayload,
    BrowseQueryDerivedMetricPayload,
    BrowseQueryFilterClausePayload,
    BrowseQueryHeightCompareClausePayload,
    BrowseQueryMetricRangeClausePayload,
    BrowseQueryMetricSortPayload,
    BrowseQueryNameContainsClausePayload,
    BrowseQueryNameNotContainsClausePayload,
    BrowseQueryNotesContainsClausePayload,
    BrowseQueryNotesNotContainsClausePayload,
    BrowseQueryRequest,
    BrowseQueryResponse,
    BrowseQueryStarsInClausePayload,
    BrowseQueryStarsNotInClausePayload,
    BrowseQueryUrlContainsClausePayload,
    BrowseQueryUrlNotContainsClausePayload,
    BrowseQueryWidthCompareClausePayload,
)
from ..paths import canonical_path
from ...storage.base import BrowseStorage


def _collect_folder_paths(storage: BrowseStorage) -> list[str]:
    queue: deque[str] = deque(["/"])
    seen: set[str] = set()

    while queue:
        path = canonical_path(queue.popleft())
        if path in seen:
            continue
        seen.add(path)
        try:
            index = storage.load_recursive_index(path)
        except FileNotFoundError:
            continue
        if index is None:
            continue
        for child_name in getattr(index, "dirs", []) or []:
            queue.append(canonical_path(storage.join(path, child_name)))

    return sorted(seen, key=lambda value: (value != "/", value))


def _query_filter_clause(clause: BrowseQueryFilterClausePayload) -> BrowseFilterClause:
    if isinstance(clause, BrowseQueryStarsInClausePayload):
        return StarsInFilter(values=tuple(clause.starsIn.values))
    if isinstance(clause, BrowseQueryStarsNotInClausePayload):
        return StarsNotInFilter(values=tuple(clause.starsNotIn.values))
    if isinstance(clause, BrowseQueryNameContainsClausePayload):
        return NameContainsFilter(value=clause.nameContains.value)
    if isinstance(clause, BrowseQueryNameNotContainsClausePayload):
        return NameNotContainsFilter(value=clause.nameNotContains.value)
    if isinstance(clause, BrowseQueryNotesContainsClausePayload):
        return NotesContainsFilter(value=clause.notesContains.value)
    if isinstance(clause, BrowseQueryNotesNotContainsClausePayload):
        return NotesNotContainsFilter(value=clause.notesNotContains.value)
    if isinstance(clause, BrowseQueryUrlContainsClausePayload):
        return UrlContainsFilter(value=clause.urlContains.value)
    if isinstance(clause, BrowseQueryUrlNotContainsClausePayload):
        return UrlNotContainsFilter(value=clause.urlNotContains.value)
    if isinstance(clause, BrowseQueryDateRangeClausePayload):
        return DateRangeFilter(from_value=clause.dateRange.from_, to_value=clause.dateRange.to)
    if isinstance(clause, BrowseQueryWidthCompareClausePayload):
        return WidthCompareFilter(op=clause.widthCompare.op, value=clause.widthCompare.value)
    if isinstance(clause, BrowseQueryHeightCompareClausePayload):
        return HeightCompareFilter(op=clause.heightCompare.op, value=clause.heightCompare.value)
    if isinstance(clause, BrowseQueryMetricRangeClausePayload):
        return MetricRangeFilter(
            key=clause.metricRange.key,
            min_value=clause.metricRange.min,
            max_value=clause.metricRange.max,
        )
    if isinstance(clause, BrowseQueryCategoricalInClausePayload):
        return CategoricalInFilter(
            key=clause.categoricalIn.key,
            values=tuple(clause.categoricalIn.values),
        )
    raise TypeError(f"unsupported browse query filter clause: {clause!r}")


def _query_derived_metric_spec(payload: BrowseQueryDerivedMetricPayload | None) -> DerivedMetricSpec | None:
    if payload is None:
        return None
    return DerivedMetricSpec(
        id=payload.id,
        name=payload.name,
        intercept=payload.intercept,
        numeric_terms=tuple(
            DerivedMetricNumericTerm(
                key=term.key,
                weight=term.weight,
                missing=term.missing,
                z_normalize=term.z_normalize,
            )
            for term in payload.numeric_terms
        ),
        categorical_terms=tuple(
            DerivedMetricCategoricalTerm(
                key=term.key,
                value=term.value,
                weight=term.weight,
            )
            for term in payload.categorical_terms
        ),
    )


def _query_spec_from_payload(body: BrowseQueryRequest) -> BrowseQuerySpec:
    sort = (
        MetricSortSpec(key=body.sort.key, direction=body.sort.dir)
        if isinstance(body.sort, BrowseQueryMetricSortPayload)
        else BuiltinSortSpec(key=body.sort.key, direction=body.sort.dir)
    )
    return BrowseQuerySpec(
        path=canonical_path(body.path),
        recursive=body.recursive,
        offset=body.offset,
        limit=body.limit,
        filters=BrowseFilterAst(
            and_clauses=tuple(_query_filter_clause(clause) for clause in body.filters.and_)
        ),
        sort=sort,
        text_query=body.text_query,
        random_seed=None if body.random_seed is None else str(body.random_seed),
        derived_metric=_query_derived_metric_spec(body.derived_metric),
        unsupported_metric_intent=body.unsupported_metric_intent,
    )


def register_folder_routes(
    app: FastAPI,
    to_item: ToItemFn,
) -> None:
    @app.post("/folders/query", response_model=BrowseQueryResponse)
    def post_folder_query(
        body: BrowseQueryRequest,
        request: Request,
    ) -> BrowseQueryResponse:
        storage = storage_from_request(request)
        return build_folder_query(
            storage,
            _query_spec_from_payload(body),
            to_item,
        )

    @app.get("/folders", response_model=BrowseFolderPayload)
    def get_folder(
        request: Request,
        path: str = "/",
        recursive: bool = False,
        count_only: bool = False,
        offset: int = Query(0, ge=0),
        limit: int | None = Query(None, gt=0, le=RECURSIVE_WINDOW_MAX_LIMIT),
    ) -> BrowseFolderPayload:
        storage = storage_from_request(request)
        context = get_request_context(request)
        return build_folder_index(
            storage,
            canonical_path(path),
            to_item,
            recursive=recursive,
            count_only=count_only,
            offset=offset,
            limit=limit,
            browse_cache=context.recursive_browse_cache,
            hotpath_metrics=context.runtime.hotpath_metrics,
        )

    @app.get("/folders/paths", response_model=BrowseFolderPathsPayload)
    def get_folder_paths(request: Request) -> BrowseFolderPathsPayload:
        storage = storage_from_request(request)
        return BrowseFolderPathsPayload(paths=_collect_folder_paths(storage))

    @app.post("/folders/facets", response_model=BrowseFacetsPayload)
    def post_folder_facets(
        body: BrowseQueryRequest,
        request: Request,
    ) -> BrowseFacetsPayload:
        storage = storage_from_request(request)
        return build_folder_facets(
            storage,
            _query_spec_from_payload(body),
            to_item,
        )

    @app.get("/folders/facets", response_model=BrowseFacetsPayload)
    def get_folder_facets(
        request: Request,
        path: str = "/",
        recursive: bool = True,
    ) -> BrowseFacetsPayload:
        storage = storage_from_request(request)
        return build_folder_facets(
            storage,
            BrowseQuerySpec(
                path=canonical_path(path),
                recursive=recursive,
                offset=0,
                limit=1,
            ),
            to_item,
        )
