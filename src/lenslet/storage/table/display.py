from __future__ import annotations

import math
import os
from typing import Any, Final

from pyarrow.lib import ArrowException

from .schema import coerce_float

_DISPLAY_DEPTH_LIMIT: Final = 8
_UNHANDLED: Final = object()
_SCALAR_CONVERSION_ERRORS = (
    ArrowException,
    TypeError,
    ValueError,
    OverflowError,
    NotImplementedError,
)


def is_internal_metric_key(raw_key: object) -> bool:
    key = str(raw_key).strip()
    if not key.startswith("__index_level_") or not key.endswith("__"):
        return False
    return key[len("__index_level_"):-2].isdigit()


def normalize_display_value(value: object, *, depth: int = 0) -> Any | None:
    if depth > _DISPLAY_DEPTH_LIMIT or value is None:
        return None

    converted = _convert_known_scalar(value)
    if converted is not value:
        return normalize_display_value(converted, depth=depth + 1)

    scalar = _normalize_scalar_value(value)
    if scalar is not _UNHANDLED:
        return scalar

    if isinstance(value, dict):
        return _normalize_mapping(value, depth=depth)
    if isinstance(value, (list, tuple, set)):
        return _normalize_sequence(value, depth=depth)

    formatted = _normalize_isoformatted_value(value)
    if formatted is not _UNHANDLED:
        return formatted
    return _normalize_fallback_text(value)


def normalize_metrics_display_value(value: object) -> Any | None:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            if is_internal_metric_key(raw_key):
                continue
            if coerce_float(raw_value) is not None:
                continue
            display_value = normalize_display_value(raw_value, depth=1)
            if display_value is None:
                continue
            normalized[str(raw_key)] = display_value
        return normalized or None
    if coerce_float(value) is not None:
        return None
    return normalize_display_value(value)


def _convert_known_scalar(value: object) -> object:
    for method_name in ("as_py", "item"):
        method = getattr(value, method_name, None)
        if not callable(method):
            continue
        try:
            converted = method()
        except _SCALAR_CONVERSION_ERRORS:
            converted = value
        if converted is not value:
            return converted
    return value


def _normalize_scalar_value(value: object) -> object:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return value if value.strip() else None
    if isinstance(value, os.PathLike):
        return os.fspath(value)
    if isinstance(value, bytes):
        try:
            text = value.decode("utf-8")
        except UnicodeDecodeError:
            return None
        return text if text.strip() else None
    return _UNHANDLED


def _normalize_mapping(value: dict[object, object], *, depth: int) -> dict[str, Any] | None:
    normalized: dict[str, Any] = {}
    for raw_key, raw_value in value.items():
        display_value = normalize_display_value(raw_value, depth=depth + 1)
        if display_value is None:
            continue
        normalized[str(raw_key)] = display_value
    return normalized or None


def _normalize_sequence(
    value: list[object] | tuple[object, ...] | set[object],
    *,
    depth: int,
) -> list[Any] | None:
    normalized_items = []
    for entry in value:
        display_value = normalize_display_value(entry, depth=depth + 1)
        if display_value is None:
            continue
        normalized_items.append(display_value)
    return normalized_items or None


def _normalize_isoformatted_value(value: object) -> object:
    isoformat = getattr(value, "isoformat", None)
    if not callable(isoformat):
        return _UNHANDLED
    try:
        text = isoformat()
    except (TypeError, ValueError, OverflowError):
        return _UNHANDLED
    if isinstance(text, str) and text.strip():
        return text
    return _UNHANDLED


def _normalize_fallback_text(value: object) -> str | None:
    text = str(value)
    if not text.strip() or text in {"<NA>", "NaT"}:
        return None
    return text
