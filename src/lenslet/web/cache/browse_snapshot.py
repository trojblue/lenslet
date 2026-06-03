"""Snapshot payload types for recursive browse cache windows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from ...storage.image_media import ImageMime, normalize_image_mime


def canonical_scope(path: str) -> str:
    value = (path or "").replace("\\", "/").strip()
    if not value:
        return "/"
    value = "/" + value.lstrip("/")
    if value != "/":
        value = value.rstrip("/")
    return value


def _coerce_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _coerce_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _coerce_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_metrics(raw: Any) -> dict[str, float] | None:
    if not isinstance(raw, dict):
        return None
    metrics: dict[str, float] = {}
    for key, value in raw.items():
        try:
            metrics[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return metrics or None


def _normalize_metric_labels(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    labels: dict[str, str] = {}
    for key, value in raw.items():
        key_text = str(key).strip()
        value_text = str(value).strip()
        if key_text and value_text:
            labels[key_text] = value_text
    return labels or None


def _normalize_categoricals(raw: Any) -> dict[str, str] | None:
    if not isinstance(raw, dict):
        return None
    categoricals: dict[str, str] = {}
    for key, value in raw.items():
        key_text = str(key).strip()
        value_text = str(value).strip()
        if key_text and value_text:
            categoricals[key_text] = value_text
    return categoricals or None


class _RecursiveCachedItemSnapshotPayloadRequired(TypedDict):
    path: str
    name: str
    mime: ImageMime
    width: int
    height: int
    size: int
    mtime: float


class RecursiveCachedItemSnapshotPayload(_RecursiveCachedItemSnapshotPayloadRequired, total=False):
    url: str
    source: str
    metrics: dict[str, float]
    metric_labels: dict[str, str]
    categoricals: dict[str, str]


@dataclass(frozen=True)
class RecursiveCachedItemSnapshot:
    path: str
    name: str
    mime: ImageMime
    width: int
    height: int
    size: int
    mtime: float
    url: str | None = None
    source: str | None = None
    metrics: dict[str, float] | None = None
    metric_labels: dict[str, str] | None = None
    categoricals: dict[str, str] | None = None

    @classmethod
    def from_cached_item(cls, cached: Any) -> "RecursiveCachedItemSnapshot":
        return cls(
            path=canonical_scope(str(getattr(cached, "path", ""))),
            name=str(getattr(cached, "name", "")),
            mime=normalize_image_mime(getattr(cached, "mime", None), str(getattr(cached, "name", ""))),
            width=_coerce_int(getattr(cached, "width", 0)),
            height=_coerce_int(getattr(cached, "height", 0)),
            size=_coerce_int(getattr(cached, "size", 0)),
            mtime=_coerce_float(getattr(cached, "mtime", 0)),
            url=_coerce_optional_text(getattr(cached, "url", None)),
            source=_coerce_optional_text(getattr(cached, "source", None)),
            metrics=_normalize_metrics(getattr(cached, "metrics", None)),
            metric_labels=_normalize_metric_labels(getattr(cached, "metric_labels", None)),
            categoricals=_normalize_categoricals(getattr(cached, "categoricals", None)),
        )

    @classmethod
    def from_payload(cls, payload: Any) -> "RecursiveCachedItemSnapshot":
        if not isinstance(payload, dict):
            raise ValueError("invalid cached item payload")
        return cls(
            path=canonical_scope(str(payload.get("path", ""))),
            name=str(payload.get("name", "")),
            mime=normalize_image_mime(payload.get("mime"), str(payload.get("name", ""))),
            width=_coerce_int(payload.get("width", 0)),
            height=_coerce_int(payload.get("height", 0)),
            size=_coerce_int(payload.get("size", 0)),
            mtime=_coerce_float(payload.get("mtime", 0)),
            url=_coerce_optional_text(payload.get("url")),
            source=_coerce_optional_text(payload.get("source")),
            metrics=_normalize_metrics(payload.get("metrics")),
            metric_labels=_normalize_metric_labels(payload.get("metric_labels")),
            categoricals=_normalize_categoricals(payload.get("categoricals")),
        )

    def to_payload(self) -> RecursiveCachedItemSnapshotPayload:
        payload: RecursiveCachedItemSnapshotPayload = {
            "path": self.path,
            "name": self.name,
            "mime": self.mime,
            "width": self.width,
            "height": self.height,
            "size": self.size,
            "mtime": self.mtime,
        }
        if self.url:
            payload["url"] = self.url
        if self.source:
            payload["source"] = self.source
        if self.metrics is not None:
            payload["metrics"] = self.metrics
        if self.metric_labels is not None:
            payload["metric_labels"] = self.metric_labels
        if self.categoricals is not None:
            payload["categoricals"] = self.categoricals
        return payload


@dataclass(frozen=True)
class RecursiveSnapshotWindow:
    scope_path: str
    sort_mode: str
    generation: str
    items: tuple[RecursiveCachedItemSnapshot, ...]

    @property
    def total_items(self) -> int:
        return len(self.items)
