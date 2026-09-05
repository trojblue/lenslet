from __future__ import annotations

import pyarrow as pa

from lenslet.storage.table.launch import is_numeric_metric_candidate


def test_numeric_metric_candidate_requires_numeric_non_boolean_scalar() -> None:
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
            ("quality_score_count", pa.int64()),
            ("count_votes", pa.int64()),
            ("image_id", pa.int64()),
            ("width", pa.int64()),
            ("timestamp", pa.timestamp("ms")),
            ("image_path", pa.string()),
        ]
    )

    for column in (
        "q1",
        "q2",
        "q10",
        "quality_score",
        "quality_score_count",
        "count_votes",
        "anatomy_ana_pixai_1_2_value",
        "manual_l2_direct_value",
        "image_id",
        "width",
    ):
        assert is_numeric_metric_candidate(schema, column)
    for column in ("q3", "q4", "timestamp", "image_path"):
        assert not is_numeric_metric_candidate(schema, column)
