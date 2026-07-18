from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.perf import table_row_group_detail


def test_multi_row_group_probe_reuses_bounded_working_set() -> None:
    result = table_row_group_detail.run_probe(
        row_count=40,
        row_group_size=5,
        warmup_rounds=1,
        repetitions=2,
    )

    assert result["schema_version"] == 1
    assert result["detail_endpoint"] == "/item"
    assert result["row_group_count"] == 8
    assert result["working_set_groups"] == 4
    assert result["requests"] == 8
    assert result["row_group_reads"] == {"warmup": 4, "measured": 0}
    assert result["cache"] == {"capacity_groups": 4, "retained_groups": 4}
    assert result["latency_ms"]["p95"] >= 0
