from __future__ import annotations

import math
from pathlib import Path
from typing import get_type_hints

import pyarrow as pa

from lenslet.storage.table.display import (
    is_internal_metric_key,
    normalize_display_value,
    normalize_metrics_display_value,
)


class _FallbackScalar:
    def as_py(self) -> str:
        raise ValueError("bad scalar")

    def item(self) -> str:
        return "fallback"


def test_normalize_display_value_unwraps_known_scalar_types() -> None:
    assert normalize_display_value(pa.scalar("cat")) == "cat"
    assert normalize_display_value(_FallbackScalar()) == "fallback"
    assert normalize_display_value(Path("nested/cat.jpg")) == "nested/cat.jpg"


def test_normalize_display_value_filters_empty_and_nonfinite_values() -> None:
    assert normalize_display_value("") is None
    assert normalize_display_value(b"\xff") is None
    assert normalize_display_value(math.nan) is None
    assert normalize_display_value({"empty": "", "label": b"sharp"}) == {"label": "sharp"}


def test_normalize_metrics_display_value_keeps_only_non_numeric_display_fields() -> None:
    assert is_internal_metric_key("__index_level_0__")
    assert not is_internal_metric_key("quality")
    assert normalize_metrics_display_value(
        {
            "__index_level_0__": "hidden",
            "score": "0.75",
            "label": "sharp",
        }
    ) == {"label": "sharp"}


def test_table_display_normalizers_use_object_input_annotations() -> None:
    assert get_type_hints(is_internal_metric_key)["raw_key"] is object
    assert get_type_hints(normalize_display_value)["value"] is object
    assert get_type_hints(normalize_metrics_display_value)["value"] is object
