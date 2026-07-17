from __future__ import annotations

from scripts.perf.thumbnail_event_loop import run_probe


def test_injected_thumbnail_hit_and_miss_leave_event_loop_responsive() -> None:
    result = run_probe(delay_seconds=0.5)

    assert result["schema_version"] == 1
    assert result["injected_delay_ms"] == 500
    assert result["max_heartbeat_gap_ms"] < 100
    for mode in ("hit", "miss"):
        case = result[mode]
        assert case["thumbnail_status"] == 200
        assert case["health_status"] == 200
        assert case["query_status"] == 200
        assert case["sse_event_received"] is True
        assert case["traffic_completed_during_thumbnail_work"] is True
    assert result["miss"]["thumbnail_returned_before_persistence"] is True
