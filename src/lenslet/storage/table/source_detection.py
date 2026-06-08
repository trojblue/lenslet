from __future__ import annotations

import math
import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from ..source.paths import extract_name, is_supported_image

MEDIA_SOURCE_EXTS = (".jpg", ".jpeg", ".png", ".webp")


@dataclass(frozen=True, slots=True)
class SourceColumnScore:
    name: str
    score: float
    total: int
    matches: int = 0
    image_name_matches: int = 0
    non_image_name_matches: int = 0
    name_priority: int = 0
    loadable_ratio: float = 0.0
    image_name_ratio: float = 0.0


_EXACT_SOURCE_NAME_PRIORITIES = {
    "s3key": 115,
    "image_url": 110,
    "image_uri": 110,
    "image_path": 110,
    "image_file": 110,
    "img_url": 108,
    "img_uri": 108,
    "img_path": 108,
    "image": 105,
    "img": 105,
    "media_url": 96,
    "media_uri": 96,
    "media_path": 96,
    "asset_url": 94,
    "asset_uri": 94,
    "asset_path": 94,
    "source": 85,
    "src": 85,
    "local_path": 84,
    "file_path": 84,
    "filepath": 84,
    "path": 80,
    "url": 75,
    "uri": 75,
    "source_url": 65,
    "source_uri": 65,
    "source_path": 65,
}


def normalized_source_text(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "as_py"):
        try:
            value = value.as_py()
        except Exception:
            return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, os.PathLike):
        value = os.fspath(value)
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    return candidate or None


def is_remote_source(value: str) -> bool:
    return value.startswith("s3://") or value.startswith("http://") or value.startswith("https://")


def source_loadability_score(
    values: Iterable[object],
    is_loadable_value: Callable[[str], bool],
    *,
    sample_size: int | None = None,
) -> tuple[int, int]:
    total = 0
    matches = 0
    for raw_value in values:
        value = normalized_source_text(raw_value)
        if value is None:
            continue
        total += 1
        if is_loadable_value(value):
            matches += 1
        if sample_size is not None and total >= sample_size:
            break
    return total, matches


def source_column_name_priority(name: str) -> int:
    normalized = _normalized_column_name(name)
    exact = _EXACT_SOURCE_NAME_PRIORITIES.get(normalized)
    if exact is not None:
        return exact

    tokens = set(filter(None, normalized.split("_")))
    locator_tokens = {"file", "path", "source", "src", "uri", "url"}
    media_tokens = {"asset", "image", "img", "media", "photo", "picture"}
    if tokens & media_tokens:
        return 90 if tokens & locator_tokens else 70
    if tokens & locator_tokens:
        return 55
    return 0


def score_source_column_values(
    name: str,
    values: Iterable[object],
    *,
    is_loadable_value: Callable[[str], bool],
    loadable_threshold: float,
    sample_size: int | None = None,
) -> SourceColumnScore | None:
    total = 0
    matches = 0
    image_name_matches = 0
    non_image_name_matches = 0
    for raw_value in values:
        value = normalized_source_text(raw_value)
        if value is None:
            continue
        total += 1
        if is_loadable_value(value):
            matches += 1
        if _supported_image_source_name(value):
            image_name_matches += 1
        elif _has_non_image_suffix(value):
            non_image_name_matches += 1
        if sample_size is not None and total >= sample_size:
            break

    if total == 0:
        return None

    loadable_ratio = matches / total
    if loadable_ratio < loadable_threshold:
        return None

    image_name_ratio = image_name_matches / total
    non_image_name_ratio = non_image_name_matches / total
    name_priority = source_column_name_priority(name)
    score = name_priority + (image_name_ratio * 100.0) - (non_image_name_ratio * 80.0)
    score += loadable_ratio * 10.0
    return SourceColumnScore(
        name=name,
        score=score,
        total=total,
        matches=matches,
        image_name_matches=image_name_matches,
        non_image_name_matches=non_image_name_matches,
        name_priority=name_priority,
        loadable_ratio=loadable_ratio,
        image_name_ratio=image_name_ratio,
    )


def better_source_column(candidate: SourceColumnScore, current: SourceColumnScore | None) -> bool:
    if current is None:
        return True
    return (
        candidate.score,
        candidate.image_name_ratio,
        candidate.loadable_ratio,
        candidate.total,
    ) > (
        current.score,
        current.image_name_ratio,
        current.loadable_ratio,
        current.total,
    )


def best_source_column_name(
    columns: list[str],
    values_for_column: Callable[[str], Iterable[object]],
    *,
    is_loadable_value: Callable[[str], bool],
    loadable_threshold: float,
    sample_size: int | None = None,
) -> str | None:
    best: SourceColumnScore | None = None
    for name in columns:
        score = score_source_column_values(
            name,
            values_for_column(name),
            is_loadable_value=is_loadable_value,
            loadable_threshold=loadable_threshold,
            sample_size=sample_size,
        )
        if score is not None and better_source_column(score, best):
            best = score
    return best.name if best is not None else None


def _normalized_column_name(name: str) -> str:
    split_camel = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(name))
    return re.sub(r"[^a-z0-9]+", "_", split_camel.lower()).strip("_")


def _supported_image_source_name(value: str) -> bool:
    return is_supported_image(extract_name(value), MEDIA_SOURCE_EXTS)


def _has_non_image_suffix(value: str) -> bool:
    name = extract_name(value)
    if not name:
        return False
    suffix = os.path.splitext(name)[1].lower()
    return bool(suffix and suffix not in MEDIA_SOURCE_EXTS)
