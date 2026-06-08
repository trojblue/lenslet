from __future__ import annotations

import math


def coerce_finite_metric_value(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if hasattr(value, "as_py"):
        try:
            value = value.as_py()
        except Exception:
            return None
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def normalize_metric_mapping(value: object) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    metrics: dict[str, float] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key).strip()
        if not key:
            continue
        metric_value = coerce_finite_metric_value(raw_value)
        if metric_value is not None:
            metrics[key] = metric_value
    return metrics
