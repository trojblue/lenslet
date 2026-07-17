from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.perf import table_query_latency
from scripts.perf.table_query_fixture import build_synthetic_table_fixture


def test_percentile_uses_linear_interpolation() -> None:
    values = [1.0, 2.0, 3.0, 4.0]

    assert table_query_latency.percentile(values, 0.0) == 1.0
    assert table_query_latency.percentile(values, 0.5) == 2.5
    assert table_query_latency.percentile(values, 0.95) == pytest.approx(3.85)
    assert table_query_latency.percentile(values, 1.0) == 4.0


def test_probe_emits_stable_schema_and_preserves_input(tmp_path: Path) -> None:
    fixture = build_synthetic_table_fixture(
        tmp_path,
        row_count=40,
        metric_count=4,
        rated_count=5,
    )

    result = table_query_latency.run_probe(
        fixture.parquet_path,
        fixture_name=fixture.name,
        source_column="image_path",
        path_column="path",
        base_dir=tmp_path,
        rated_count=fixture.rated_count,
        warmups=1,
        repetitions=2,
    )

    assert result["schema_version"] == 1
    assert result["fixture"] == "synthetic-40x4"
    assert result["input_unchanged"] is True
    assert result["warmups"] == 1
    assert result["repetitions"] == 2
    assert result["analysis_started"] == 2
    assert result["analysis_joined"] == 0
    assert result["analysis_superseded"] == 0
    assert result["analysis_cancelled"] == 0
    assert result["correctness"]["scope_total"] == 40
    assert result["correctness"]["filtered_total"] == 35
    assert result["correctness"]["facet_total"] == 35
    assert result["sidecars"] == {"rated": 5}
    assert result["latency_ms"]["query"]["count"] == 2
    assert result["response_bytes"]["combined"]["p95"] > 0
    assert {
        "queue",
        "analysis",
        "ordering",
        "projection",
        "serialize",
    } <= result["server_timing_ms"]["query"].keys()
    assert "facet" in result["server_timing_ms"]["facets"]


def test_probe_rejects_detected_input_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_synthetic_table_fixture(
        tmp_path,
        row_count=12,
        metric_count=3,
        rated_count=2,
    )
    states = iter(({"input": "before"}, {"input": "after"}))
    monkeypatch.setattr(table_query_latency, "_input_state", lambda _paths: next(states))

    with pytest.raises(
        table_query_latency.InputMutationError, match="files changed during read-only probe"
    ):
        table_query_latency.run_probe(
            fixture.parquet_path,
            fixture_name=fixture.name,
            source_column="image_path",
            path_column="path",
            base_dir=tmp_path,
            rated_count=fixture.rated_count,
            warmups=0,
            repetitions=1,
        )
