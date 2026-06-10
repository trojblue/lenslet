from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import Any, Iterable

from ...browse.query import (
    BrowseQueryRecord,
    BrowseQuerySpec,
    browse_analysis_query_key,
    evaluate_browse_records,
)
from ...metrics import coerce_finite_metric_value


def build_table_query_facet_summary(
    *,
    spec: BrowseQuerySpec,
    records: Iterable[BrowseQueryRecord[Any]],
    scope_total: int,
    generated_at: str,
    canonical_path: str,
    metric_keys: Iterable[str],
    categorical_keys: Iterable[str],
    bins: int,
) -> dict[str, Any]:
    metric_key_list = list(metric_keys)
    categorical_key_list = list(categorical_keys)
    evaluation = evaluate_browse_records(
        tuple(records),
        replace(spec, offset=0, limit=max(1, scope_total)),
        metric_keys=metric_key_list,
        categorical_keys=categorical_key_list,
    )

    metric_values: dict[str, list[float]] = {key: [] for key in metric_key_list}
    categorical_counts: dict[str, Counter[str]] = {
        key: Counter()
        for key in categorical_key_list
    }
    for record in evaluation.window:
        for key, value in (record.metrics or {}).items():
            coerced = coerce_finite_metric_value(value)
            if coerced is not None:
                metric_values.setdefault(key, []).append(coerced)
        for key, value in (record.categoricals or {}).items():
            normalized = _normalize_categorical_value(value)
            if normalized is not None:
                categorical_counts.setdefault(key, Counter())[normalized] += 1

    metric_keys_out = sorted(metric_values)
    categorical_keys_out = sorted(categorical_counts)
    return {
        "version": 1,
        "path": canonical_path,
        "generated_at": generated_at,
        "analysis_query_key": browse_analysis_query_key(spec),
        "total_items": evaluation.filtered_total,
        "count_provenance": {
            "scope_total": scope_total,
            "query_filtered_total": evaluation.filtered_total,
            "loaded_window_total": None,
            "source": "backend_query",
        },
        "metric_keys": metric_keys_out,
        "categorical_keys": categorical_keys_out,
        "metrics": {
            key: {
                "histogram": _histogram_summary(values, bins),
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


def _histogram_summary(values: list[float], bins: int) -> dict[str, Any] | None:
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


def _normalize_categorical_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
