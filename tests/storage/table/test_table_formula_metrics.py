from __future__ import annotations

import pyarrow as pa

from lenslet.storage.table.index import is_formula_metric_column_name
from lenslet.storage.table.launch import is_formula_metric_browse_column


def test_formula_metric_column_names_include_q_fields_and_metric_like_names() -> None:
    included = [
        "q1",
        "q2",
        "q10",
        "Q12",
        "anatomy_ana_pixai_1_2_value",
        "clip_aesthetic",
        "hamming_distance",
        "manual_l2_direct_value",
        "quality_score",
    ]
    excluded = [
        "__index_level_0__",
        "created_at",
        "height",
        "image_id",
        "image_path",
        "is_selected",
        "mime",
        "pending_gpt_q4_value_view",
        "quality_score_count",
        "row_index",
        "size",
        "source",
        "timestamp",
        "width",
    ]

    assert [column for column in included if is_formula_metric_column_name(column)] == included
    assert [column for column in excluded if is_formula_metric_column_name(column)] == []


def test_formula_metric_browse_column_requires_numeric_non_boolean_scalar() -> None:
    schema = pa.schema(
        [
            ("q1", pa.float64()),
            ("q2", pa.int64()),
            ("q10", pa.decimal128(8, 3)),
            ("q3", pa.bool_()),
            ("q4", pa.list_(pa.float64())),
            ("anatomy_ana_pixai_1_2_value", pa.float64()),
            ("manual_l2_direct_value", pa.float64()),
            ("quality_score", pa.float64()),
            ("image_id", pa.int64()),
            ("width", pa.int64()),
            ("timestamp", pa.timestamp("ms")),
            ("image_path", pa.string()),
        ]
    )

    assert is_formula_metric_browse_column(schema, "q1")
    assert is_formula_metric_browse_column(schema, "q2")
    assert is_formula_metric_browse_column(schema, "q10")
    assert is_formula_metric_browse_column(schema, "quality_score")
    assert not is_formula_metric_browse_column(schema, "q3")
    assert not is_formula_metric_browse_column(schema, "q4")
    assert is_formula_metric_browse_column(schema, "anatomy_ana_pixai_1_2_value")
    assert is_formula_metric_browse_column(schema, "manual_l2_direct_value")
    assert not is_formula_metric_browse_column(schema, "image_id")
    assert not is_formula_metric_browse_column(schema, "width")
    assert not is_formula_metric_browse_column(schema, "timestamp")
    assert not is_formula_metric_browse_column(schema, "image_path")
