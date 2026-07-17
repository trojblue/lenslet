from __future__ import annotations

from typing import TYPE_CHECKING

from ...browse.query import (
    BrowseQueryFolderEntry,
    BrowseQueryResult,
    BrowseQuerySpec,
    browse_query_request_token,
)
from ...diagnostics import request_phase
from ..source.paths import normalize_item_path
from .facets import build_table_query_facet_summary, metric_keys_for_query_spec
from .query_engine import (
    CancellationProbe,
    TableFilterAnalysis,
    TableFilterKey,
    TableOrderAnalysis,
    TableOrderKey,
)
from .row_store import TableRowViewItem

if TYPE_CHECKING:
    from .storage import TableStorage


def query_context(
    storage: TableStorage,
    spec: BrowseQuerySpec,
) -> tuple[str, tuple[int, ...], tuple[BrowseQueryFolderEntry, ...]]:
    norm = normalize_item_path(spec.path)
    row_store = storage._require_row_store()
    rows = storage._query_rows_for_scope(row_store, norm, recursive=spec.recursive)
    folders = storage._query_folder_entries(row_store, norm)
    if not rows and not folders and norm:
        raise FileNotFoundError(spec.path)
    return norm, rows, folders


def filter_key(storage: TableStorage, spec: BrowseQuerySpec) -> TableFilterKey:
    query_context(storage, spec)
    return storage.query_engine.filter_key(spec)


def analyze_filter(
    storage: TableStorage,
    spec: BrowseQuerySpec,
    expected_key: TableFilterKey | None,
    cancel: CancellationProbe,
) -> TableFilterAnalysis:
    _norm, rows, _folders = query_context(storage, spec)
    return storage.query_engine.analyze_filter(
        rows,
        spec,
        cancel,
        expected_key=expected_key,
    )


def order_key(
    storage: TableStorage,
    spec: BrowseQuerySpec,
    analysis: TableFilterAnalysis,
) -> TableOrderKey:
    return storage.query_engine.order_key(analysis, spec)


def order_analysis(
    storage: TableStorage,
    spec: BrowseQuerySpec,
    analysis: TableFilterAnalysis,
    key: TableOrderKey,
    cancel: CancellationProbe,
) -> TableOrderAnalysis:
    return storage.query_engine.order(
        analysis,
        spec.sort,
        random_seed=spec.random_seed,
        cancel=cancel,
        key=key,
    )


def query_scope(
    storage: TableStorage,
    spec: BrowseQuerySpec,
) -> BrowseQueryResult[TableRowViewItem]:
    with request_phase("analysis"):
        analysis = analyze_filter(storage, spec, None, lambda: False)
    key = order_key(storage, spec, analysis)
    with request_phase("ordering"):
        ordered = order_analysis(storage, spec, analysis, key, lambda: False)
    return query_scope_from_analysis(storage, spec, analysis, ordered)


def query_scope_from_analysis(
    storage: TableStorage,
    spec: BrowseQuerySpec,
    analysis: TableFilterAnalysis,
    ordered: TableOrderAnalysis,
) -> BrowseQueryResult[TableRowViewItem]:
    norm, rows, folders = query_context(storage, spec)
    if ordered.key.filter_key != analysis.key:
        raise ValueError("order analysis does not match filter analysis")
    available_categorical_keys = frozenset(storage.categorical_keys())
    available_metric_keys = frozenset(metric_keys_for_query_spec(spec, analysis.metric_keys))
    projected_metric_keys = tuple(spec.projection.metric_keys)
    projected_categorical_keys = tuple(spec.projection.categorical_keys)
    result_metric_keys = tuple(key for key in projected_metric_keys if key in available_metric_keys)
    categorical_keys = tuple(
        key for key in projected_categorical_keys if key in available_categorical_keys
    )
    storage.query_engine.window_key(
        ordered,
        spec,
        metric_keys=projected_metric_keys,
        categorical_keys=projected_categorical_keys,
    )
    with request_phase("projection"):
        start = max(0, spec.offset)
        end = start + max(0, spec.limit)
        items = tuple(
            storage._materialize_query_item(
                row_id,
                analysis,
                projected_metric_keys,
                projected_categorical_keys,
            )
            for row_id in ordered.ordered_row_ids[start:end]
        )
    return BrowseQueryResult(
        path=_canonical_path(norm),
        generated_at=storage._generated_at,
        generation_token=_generation_token(
            storage.browse_cache_signature(),
            storage.browse_generation(),
        ),
        request_token=browse_query_request_token(spec),
        scope_total=len(rows),
        filtered_total=len(analysis.row_ids),
        offset=spec.offset,
        limit=spec.limit,
        items=items,
        folders=folders,
        metric_keys=result_metric_keys,
        categorical_keys=categorical_keys,
        derived_metric_status=analysis.derived_metric_status,
    )


def facets(
    storage: TableStorage,
    spec: BrowseQuerySpec,
    *,
    bins: int,
) -> dict[str, object]:
    with request_phase("analysis"):
        analysis = analyze_filter(storage, spec, None, lambda: False)
    return facets_from_analysis(storage, spec, analysis, bins=bins)


def facets_from_analysis(
    storage: TableStorage,
    spec: BrowseQuerySpec,
    analysis: TableFilterAnalysis,
    *,
    bins: int,
) -> dict[str, object]:
    norm, rows, _folders = query_context(storage, spec)
    return build_table_query_facet_summary(
        spec=spec,
        engine=storage.query_engine,
        analysis=analysis,
        scope_total=len(rows),
        generated_at=storage._generated_at,
        canonical_path=_canonical_path(norm),
        metric_keys=metric_keys_for_query_spec(spec, analysis.metric_keys),
        categorical_keys=storage.categorical_keys(),
        bins=bins,
    )


def _canonical_path(path: str) -> str:
    normalized = normalize_item_path(path)
    return f"/{normalized}" if normalized else "/"


def _generation_token(signature: str, generation: int) -> str:
    parts = [part for part in (str(signature).strip(), str(generation).strip()) if part]
    return "|".join(parts) if parts else "default"
