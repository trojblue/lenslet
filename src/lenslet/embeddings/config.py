from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

SUPPORTED_METRICS = ("cosine",)


def _normalize_metric(value: str) -> str:
    return value.strip().lower()


def _unique_ordered(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return tuple(ordered)


@dataclass(frozen=True)
class EmbeddingConfig:
    explicit_columns: tuple[str, ...] | None = None
    metric_overrides: dict[str, str] = field(default_factory=dict)
    default_metric: str = "cosine"

    def metric_for(self, name: str) -> str:
        return self.metric_overrides.get(name, self.default_metric)


def parse_embedding_columns(values: Iterable[str] | None) -> tuple[str, ...] | None:
    if not values:
        return None
    columns: list[str] = []
    for raw in values:
        for part in raw.split(","):
            name = part.strip()
            if name:
                columns.append(name)
    if not columns:
        return None
    return _unique_ordered(columns)


def parse_embedding_metrics(values: Iterable[str] | None) -> dict[str, str]:
    if not values:
        return {}
    overrides: dict[str, str] = {}
    for raw in values:
        if ":" not in raw:
            raise ValueError("--embedding-metric expects NAME:METRIC")
        name, metric = raw.split(":", 1)
        name = name.strip()
        metric = _normalize_metric(metric)
        if not name or not metric:
            raise ValueError("--embedding-metric expects NAME:METRIC")
        if metric not in SUPPORTED_METRICS:
            allowed = ", ".join(SUPPORTED_METRICS)
            raise ValueError(f"Unsupported embedding metric '{metric}'. Supported: {allowed}.")
        overrides[name] = metric
    return overrides
