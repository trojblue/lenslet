from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import TypeVar

from fastapi import FastAPI, HTTPException, Query, Request

from ...browse.query import (
    BrowseFacetFields,
    BrowseFilterAst,
    BrowseFilterClause,
    BrowseQuerySpec,
    BrowseWindowProjection,
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
    browse_analysis_query_key,
    browse_facet_request_token,
    browse_query_request_token,
)
from ...diagnostics import mark_request_handler_started, request_phase
from ...storage.base import BrowseStorage
from ...storage.table.query_coordinator import (
    AnalysisBusy,
    AnalysisLease,
    AnalysisSuperseded,
)
from ...storage.table.query_engine import (
    TableFilterAnalysis,
    TableOrderAnalysis,
    TableQueryStale,
)
from ...storage.table.storage import TableStorage
from ..browse import (
    RECURSIVE_WINDOW_MAX_LIMIT,
    ToItemFn,
    build_folder_facets,
    build_folder_facets_from_summary,
    build_folder_field_capabilities,
    build_folder_index,
    build_folder_query,
    build_folder_query_from_result,
    storage_from_request,
)
from ..context import get_request_context
from ..models import (
    BrowseFacetsPayload,
    BrowseFieldCapabilitiesPayload,
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


_CLIENT_SESSION_HEADER = "X-Lenslet-Client-Session"
_QUERY_REVISION_HEADER = "X-Lenslet-Query-Revision"
_MAX_CLIENT_SESSION_LENGTH = 128
_MAX_QUERY_REVISION = (1 << 63) - 1
_STALE_RETRIES = 3
T = TypeVar("T")


def _analysis_owner(request: Request) -> tuple[str, int]:
    session = request.headers.get(_CLIENT_SESSION_HEADER)
    raw_revision = request.headers.get(_QUERY_REVISION_HEADER)
    if session is None or raw_revision is None:
        raise HTTPException(400, "analysis ownership headers must be sent together")
    if (
        not session
        or len(session) > _MAX_CLIENT_SESSION_LENGTH
        or session != session.strip()
        or any(ord(character) < 33 or ord(character) > 126 for character in session)
    ):
        raise HTTPException(400, "invalid analysis client session")
    try:
        revision = int(raw_revision)
    except ValueError as exc:
        raise HTTPException(400, "invalid query revision") from exc
    if str(revision) != raw_revision or not 0 <= revision <= _MAX_QUERY_REVISION:
        raise HTTPException(400, "invalid query revision")
    return session, revision


def _analysis_busy() -> HTTPException:
    return HTTPException(
        503,
        "analysis_busy",
        headers={"Retry-After": "1"},
    )


def _analysis_superseded() -> HTTPException:
    return HTTPException(409, "analysis_superseded")


def _raise_storage_query_error(exc: ValueError | FileNotFoundError) -> None:
    if isinstance(exc, FileNotFoundError):
        raise HTTPException(404, "folder not found") from exc
    raise HTTPException(400, "invalid path") from exc


async def _acquire_table_filter(
    storage: TableStorage,
    spec: BrowseQuerySpec,
    request: Request,
    session: str,
    revision: int,
) -> TableFilterAnalysis:
    coordinator = get_request_context(request).runtime.query_coordinator
    for _attempt in range(_STALE_RETRIES):
        try:
            key = storage.table_filter_key(spec)
            with request_phase("analysis"):
                lease = await coordinator.acquire(
                    "filter",
                    key,
                    lambda cancel: storage.analyze_table_filter(spec, key, cancel),
                    client_session=session,
                    query_revision=revision,
                    disconnected=request.is_disconnected,
                )
            return storage.refresh_table_filter(spec, lease.value)
        except AnalysisBusy as exc:
            raise _analysis_busy() from exc
        except AnalysisSuperseded as exc:
            raise _analysis_superseded() from exc
        except TableQueryStale:
            continue
        except (ValueError, FileNotFoundError) as exc:
            _raise_storage_query_error(exc)
    raise _analysis_busy()


async def _acquire_table_order(
    storage: TableStorage,
    spec: BrowseQuerySpec,
    analysis: TableFilterAnalysis,
    request: Request,
    session: str,
    revision: int,
) -> TableOrderAnalysis:
    coordinator = get_request_context(request).runtime.query_coordinator
    key = storage.table_order_key(spec, analysis)
    try:
        with request_phase("ordering"):
            lease = await coordinator.acquire(
                "order",
                key,
                lambda cancel: storage.order_table_analysis(
                    spec, analysis, key, cancel,
                ),
                client_session=session,
                query_revision=revision,
                disconnected=request.is_disconnected,
            )
    except AnalysisBusy as exc:
        raise _analysis_busy() from exc
    except AnalysisSuperseded as exc:
        raise _analysis_superseded() from exc
    return lease.value


async def _coordinated_table_query(
    storage: TableStorage,
    spec: BrowseQuerySpec,
    request: Request,
    to_item: ToItemFn,
    session: str,
    revision: int,
) -> BrowseQueryResponse:
    coordinator = get_request_context(request).runtime.query_coordinator
    analysis = await _acquire_table_filter(
        storage, spec, request, session, revision,
    )
    ordered = await _acquire_table_order(
        storage, spec, analysis, request, session, revision,
    )
    projection_key = (
        "window",
        ordered.key,
        spec.offset,
        spec.limit,
        spec.projection,
        id(analysis),
    )
    try:
        with request_phase("projection"):
            lease = await coordinator.acquire(
                "request",
                projection_key,
                lambda _cancel: build_folder_query_from_result(
                    storage,
                    storage.query_browse_scope_from_analysis(spec, analysis, ordered),
                    spec,
                    to_item,
                ),
                client_session=session,
                query_revision=revision,
                disconnected=request.is_disconnected,
            )
    except AnalysisBusy as exc:
        raise _analysis_busy() from exc
    except AnalysisSuperseded as exc:
        raise _analysis_superseded() from exc
    return lease.value


async def _coordinated_table_facets(
    storage: TableStorage,
    spec: BrowseQuerySpec,
    request: Request,
    session: str,
    revision: int,
) -> BrowseFacetsPayload:
    coordinator = get_request_context(request).runtime.query_coordinator
    analysis = await _acquire_table_filter(
        storage, spec, request, session, revision,
    )
    facet_key = (browse_facet_request_token(spec), id(analysis))
    try:
        with request_phase("facet"):
            lease = await coordinator.acquire(
                "request",
                facet_key,
                lambda _cancel: build_folder_facets_from_summary(
                    storage.facet_summary_for_query_from_analysis(spec, analysis),
                    spec,
                ),
                client_session=session,
                query_revision=revision,
                disconnected=request.is_disconnected,
            )
    except AnalysisBusy as exc:
        raise _analysis_busy() from exc
    except AnalysisSuperseded as exc:
        raise _analysis_superseded() from exc
    return lease.value


async def _coordinated_generic_request(
    *,
    kind: str,
    key: str,
    operation: Callable[[], T],
    request: Request,
    session: str,
    revision: int,
) -> T:
    coordinator = get_request_context(request).runtime.query_coordinator
    try:
        lease: AnalysisLease[T] = await coordinator.acquire(
            "generic",
            (kind, key),
            lambda _cancel: operation(),
            client_session=session,
            query_revision=revision,
            disconnected=request.is_disconnected,
        )
    except AnalysisBusy as exc:
        raise _analysis_busy() from exc
    except AnalysisSuperseded as exc:
        raise _analysis_superseded() from exc
    return lease.value


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
        projection=BrowseWindowProjection(
            metric_keys=tuple(body.projection.metric_keys),
            categorical_keys=tuple(body.projection.categorical_keys),
        ),
        facet_fields=(
            BrowseFacetFields(
                metric_keys=tuple(body.facet_fields.metric_keys),
                categorical_keys=tuple(body.facet_fields.categorical_keys),
            )
            if body.facet_fields is not None
            else None
        ),
    )


def register_folder_routes(
    app: FastAPI,
    to_item: ToItemFn,
) -> None:
    @app.get("/folders/fields", response_model=BrowseFieldCapabilitiesPayload)
    def get_folder_fields(
        request: Request,
        path: str = "/",
        recursive: bool = True,
    ) -> BrowseFieldCapabilitiesPayload:
        storage = storage_from_request(request)
        return build_folder_field_capabilities(storage, path, recursive=recursive)

    @app.post("/folders/query", response_model=BrowseQueryResponse)
    async def post_folder_query(
        body: BrowseQueryRequest,
        request: Request,
    ) -> BrowseQueryResponse:
        mark_request_handler_started()
        storage = storage_from_request(request)
        spec = _query_spec_from_payload(body)
        session, revision = _analysis_owner(request)
        if isinstance(storage, TableStorage):
            return await _coordinated_table_query(
                storage, spec, request, to_item, session, revision,
            )
        return await _coordinated_generic_request(
            kind="query",
            key=browse_query_request_token(spec),
            operation=lambda: build_folder_query(storage, spec, to_item),
            request=request,
            session=session,
            revision=revision,
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
    async def post_folder_facets(
        body: BrowseQueryRequest,
        request: Request,
    ) -> BrowseFacetsPayload:
        mark_request_handler_started()
        storage = storage_from_request(request)
        spec = _query_spec_from_payload(body)
        session, revision = _analysis_owner(request)
        if isinstance(storage, TableStorage):
            return await _coordinated_table_facets(
                storage, spec, request, session, revision,
            )
        return await _coordinated_generic_request(
            kind="facets",
            key=browse_facet_request_token(spec),
            operation=lambda: build_folder_facets(storage, spec, to_item),
            request=request,
            session=session,
            revision=revision,
        )

    @app.get("/folders/facets", response_model=BrowseFacetsPayload)
    async def get_folder_facets(
        request: Request,
        path: str = "/",
        recursive: bool = True,
    ) -> BrowseFacetsPayload:
        mark_request_handler_started()
        storage = storage_from_request(request)
        spec = BrowseQuerySpec(
            path=canonical_path(path),
            recursive=recursive,
            offset=0,
            limit=1,
        )
        session, revision = _analysis_owner(request)
        if isinstance(storage, TableStorage):
            return await _coordinated_table_facets(
                storage, spec, request, session, revision,
            )
        return await _coordinated_generic_request(
            kind="facets",
            key=browse_analysis_query_key(spec),
            operation=lambda: build_folder_facets(storage, spec, to_item),
            request=request,
            session=session,
            revision=revision,
        )
