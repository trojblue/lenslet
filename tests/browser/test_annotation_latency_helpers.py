from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.browser.annotation_latency.acceptance import build_summary
from scripts.browser.annotation_latency.probe import (
    BrowserRequestEvidence,
    filtered_gallery_url,
)
from scripts.perf.table_query_fixture import build_synthetic_table_fixture
from lenslet.workspace import Workspace


def test_filtered_gallery_url_carries_required_four_filter_scenario() -> None:
    url = filtered_gallery_url("http://127.0.0.1:7070")
    parsed = urlparse(url)
    filters = json.loads(parse_qs(parsed.query)["filters"][0])

    assert parsed.fragment == "/gallery"
    assert filters["and"][0] == {"starsIn": {"values": [0]}}
    assert [clause["metricRange"]["key"] for clause in filters["and"][1:]] == [
        "metric_000",
        "metric_001",
        "metric_002",
    ]


def test_request_evidence_separates_mutation_window_counts_and_bytes() -> None:
    evidence = BrowserRequestEvidence(phase="mutation")
    query = SimpleNamespace(url="http://test/folders/query", method="POST")
    second_query = SimpleNamespace(url="http://test/folders/query", method="POST")
    facets = SimpleNamespace(url="http://test/folders/facets", method="POST")
    evidence.on_request(query)
    evidence.on_request(second_query)
    evidence.on_request(facets)
    evidence.on_response(
        SimpleNamespace(
            url=query.url,
            request=query,
            status=200,
            headers={"content-length": "123", "server-timing": "analysis;dur=4.5"},
        )
    )
    facets.failure = "net::ERR_ABORTED"
    evidence.on_request_failed(facets)
    evidence.on_request_finished(query)
    evidence.on_request_finished(second_query)

    summary = evidence.phase_summary("mutation")

    assert summary["query_requests"] == 2
    assert summary["facet_requests"] == 1
    assert summary["query_response_bytes"] == 123
    assert summary["responses"][0]["server_timing_ms"] == {"analysis": 4.5}
    assert summary["failed_requests"][0]["failure"] == "net::ERR_ABORTED"
    assert summary["inflight_requests"] == 0


def test_request_evidence_keeps_start_phase_when_response_arrives_later() -> None:
    evidence = BrowserRequestEvidence(phase="initial")
    request = SimpleNamespace(url="http://test/folders/query", method="POST")
    evidence.on_request(request)

    evidence.phase = "mutation"
    evidence.on_response(
        SimpleNamespace(
            url=request.url,
            request=request,
            status=200,
            headers={"content-length": "42"},
        )
    )
    evidence.on_request_finished(request)

    assert evidence.phase_summary("initial")["query_response_bytes"] == 42
    assert evidence.phase_summary("initial")["inflight_requests"] == 0
    assert evidence.phase_summary("mutation")["query_response_bytes"] == 0


def test_fixture_persists_requested_rated_sidecars_for_live_server(tmp_path: Path) -> None:
    fixture = build_synthetic_table_fixture(
        tmp_path,
        row_count=20,
        metric_count=3,
        rated_count=4,
    )
    snapshot = Workspace.for_parquet(
        fixture.parquet_path,
        can_write=True,
    ).read_labels_snapshot()

    assert snapshot is not None
    assert snapshot["last_event_id"] == 4
    assert len(snapshot["items"]) == 4
    assert snapshot["items"]["/gallery/item_00000.jpg"]["star"] == 1


def test_baseline_summary_records_targets_without_claiming_acceptance(tmp_path: Path) -> None:
    scenario = {
        "session_id": "client-1",
        "semantic_revisions": None,
        "target_path": "/gallery/item_00300.jpg",
        "initial_visible_paths": ["/gallery/item_00300.jpg"],
        "final_visible_paths": ["/gallery/item_00301.jpg"],
        "annotation_projection_ms": 250.0,
        "gallery_root_replaced": False,
        "active_loading_state_observed": True,
        "page_clearing_loading_observed": True,
        "loading_states": [
            {"grid_state": "ready", "aria_busy": False, "visible_cell_count": 30},
            {"grid_state": "loading", "aria_busy": True, "visible_cell_count": 0},
            {"grid_state": "ready", "aria_busy": False, "visible_cell_count": 30},
        ],
        "scroll_top_before": 0,
        "scroll_top_after": 0,
        "target_still_visible": False,
        "query_requests": 2,
        "facet_requests": 2,
        "mutation_requests": 1,
        "query_response_bytes": 100,
        "facet_response_bytes": 50,
        "failed_requests": [],
        "responses": [],
    }

    summary = build_summary(
        fixture_name="synthetic-2000x30",
        scenario=scenario,
        initial_health={"ok": True},
        final_health={"hotpath": {"counters": {"analysis_started_total": 4}}},
        server_log=tmp_path / "server.log",
    )

    assert summary["status"] == "baseline_recorded"
    assert summary["observations"] == {
        "current_duplicate_or_reset_behavior": True,
        "post_fix_projection_target_met": False,
        "post_fix_no_page_clear_target_met": False,
        "multi_editor_target_met": False,
    }
