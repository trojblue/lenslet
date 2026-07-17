from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from ...browse.query import (
    BrowseQuerySpec,
    browse_analysis_query_key,
    derived_metric_key,
    normalize_derived_metric_spec,
)
from ...diagnostics import request_phase
from .query_engine import TableFilterAnalysis, TableQueryEngine


def metric_keys_for_query_spec(
    spec: BrowseQuerySpec,
    metric_keys: Iterable[str],
) -> list[str]:
    result = list(metric_keys)
    normalized = normalize_derived_metric_spec(spec.derived_metric)
    if normalized is not None and (key := derived_metric_key(normalized)) not in result:
        result.append(key)
    return result


def build_table_query_facet_summary(
    *,
    spec: BrowseQuerySpec,
    engine: TableQueryEngine,
    analysis: TableFilterAnalysis,
    scope_total: int,
    generated_at: str,
    canonical_path: str,
    metric_keys: Iterable[str],
    categorical_keys: Iterable[str],
    bins: int,
) -> dict[str, Any]:
    metric_key_list = list(metric_keys)
    categorical_key_list = list(categorical_keys)

    with request_phase("facet"):
        metric_values = {
            key: list(engine.iter_metric_values(analysis, key))
            for key in metric_key_list
        }
        categorical_counts = {
            key: Counter(engine.iter_categorical_values(analysis, key))
            for key in categorical_key_list
        }

        metric_keys_out = sorted(metric_values)
        categorical_keys_out = sorted(categorical_counts)
        return {
            "version": 1,
            "path": canonical_path,
            "generated_at": generated_at,
            "analysis_query_key": browse_analysis_query_key(spec),
            "total_items": len(analysis.row_ids),
            "count_provenance": {
                "scope_total": scope_total,
                "query_filtered_total": len(analysis.row_ids),
                "loaded_window_total": None,
                "source": "backend_query",
            },
            "metric_keys": metric_keys_out,
            "categorical_keys": categorical_keys_out,
            "metrics": {
                key: {
                    "histogram": histogram_summary(values, bins),
                    "categories": [],
                }
                for key, values in metric_values.items()
                if values
            },
            "categoricals": {
                key: {
                    "values": [
                        {"value": value, "population_count": count}
                        for value, count in sorted(
                            counts.items(),
                            key=lambda item: (-item[1], item[0]),
                        )
                    ]
                }
                for key, counts in categorical_counts.items()
                if counts
            },
        }


def histogram_summary(values: list[float], bins: int) -> dict[str, Any] | None:
    if not values:
        return None
    safe_bins = max(1, bins)
    min_value = min(values)
    max_value = max(values)
    if min_value == max_value:
        max_value = min_value + 1
    counts = [0] * safe_bins
    scale = safe_bins / (max_value - min_value)
    for value in values:
        idx = max(0, min(safe_bins - 1, int((value - min_value) * scale)))
        counts[idx] += 1
    return {
        "bins": counts,
        "min": min_value,
        "max": max_value,
        "count": len(values),
    }
