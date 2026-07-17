#!/usr/bin/env python3
"""Validate immediate annotation projection and two-session reconciliation."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

if __name__ == "__main__" and not __package__:
    raise SystemExit(
        "Run from the repository root with: python -m scripts.browser.annotation_latency.acceptance"
    )

from scripts.browser.annotation_latency.probe import (
    BrowserRequestEvidence,
    arm_projection_probe,
    filtered_gallery_url,
    install_projection_probe,
    projection_snapshot,
    run_superseded_filter_sequence,
    visible_paths,
)
from scripts.perf.table_query_fixture import (
    DEFAULT_METRIC_COUNT,
    DEFAULT_RATED_COUNT,
    DEFAULT_ROW_COUNT,
    build_synthetic_table_fixture,
)
from scripts.smoke_harness import (
    SmokeFailure,
    choose_port,
    import_playwright,
    read_log_tail,
    running_lenslet_server,
    wait_for_health,
    write_json_evidence,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7070)
    parser.add_argument("--rows", type=int, default=DEFAULT_ROW_COUNT)
    parser.add_argument("--metrics", type=int, default=DEFAULT_METRIC_COUNT)
    parser.add_argument("--rated", type=int, default=DEFAULT_RATED_COUNT)
    parser.add_argument("--server-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--browser-timeout-ms", type=float, default=45_000)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--keep-fixture", action="store_true")
    return parser.parse_args()


def wait_for_quiescence(
    page: Any,
    evidence: BrowserRequestEvidence,
    phase: str,
    *,
    timeout_ms: float,
) -> dict[str, Any]:
    started = time.monotonic()
    deadline = started + timeout_ms / 1_000.0
    stable_since: float | None = None
    state: dict[str, Any] = {}
    while time.monotonic() < deadline:
        state = page.evaluate(
            """() => {
              const gallery = document.querySelector('[role="grid"][aria-label="Gallery"]');
              return {
                gallery_present: gallery != null,
                aria_busy: gallery?.getAttribute('aria-busy') === 'true',
                visible_cell_count: gallery?.querySelectorAll(
                  '[role="gridcell"][id^="cell-"]'
                ).length ?? 0,
              };
            }"""
        )
        settled = (
            evidence.inflight_count(phase) == 0
            and bool(state["gallery_present"])
            and not bool(state["aria_busy"])
            and int(state["visible_cell_count"]) > 0
        )
        now = time.monotonic()
        if settled:
            stable_since = stable_since or now
            if now - stable_since >= 0.25:
                return {
                    "completed": True,
                    "elapsed_ms": round((now - started) * 1_000.0, 3),
                    "inflight_requests": 0,
                    **state,
                }
        else:
            stable_since = None
        page.wait_for_timeout(50)
    return {
        "completed": False,
        "elapsed_ms": round((time.monotonic() - started) * 1_000.0, 3),
        "inflight_requests": evidence.inflight_count(phase),
        **state,
    }


def _attach_evidence(page: Any, evidence: BrowserRequestEvidence, timeout_ms: float) -> None:
    page.set_default_timeout(timeout_ms)
    page.on("request", evidence.on_request)
    page.on("response", evidence.on_response)
    page.on("requestfailed", evidence.on_request_failed)
    page.on("requestfinished", evidence.on_request_finished)


def _wait_for_ready_gallery(page: Any) -> None:
    page.get_by_role("grid", name="Gallery").wait_for(state="visible")
    page.wait_for_function(
        """() => document.querySelectorAll('[role="gridcell"][id^="cell-"]').length > 0
          && document.querySelector('[role="grid"][aria-label="Gallery"]')?.getAttribute('aria-busy') !== 'true'"""
    )


def _open_metrics_panel(page: Any) -> None:
    page.locator('button[title="Filters"][aria-haspopup="dialog"]').click()
    page.get_by_role("button", name="Open Metrics Panel").click()


def _run_annotation_round(
    *,
    owner_page: Any,
    owner_evidence: BrowserRequestEvidence,
    remote_page: Any,
    remote_evidence: BrowserRequestEvidence,
    target_path: str,
    phase: str,
    timeout_ms: float,
) -> dict[str, Any]:
    owner_evidence.phase = phase
    remote_evidence.phase = phase
    owner_page.locator(f'[id="cell-{_encode_path(target_path)}"]').click()
    star_button = owner_page.get_by_role("button", name="1 star")
    star_button.wait_for(state="visible")
    install_projection_probe(owner_page, target_path)
    install_projection_probe(remote_page, target_path)
    arm_projection_probe(remote_page)
    star_button.click()
    for page in (owner_page, remote_page):
        page.wait_for_function(
            """() => window.__lensletAnnotationLatencyProbe?.projectionTimestamp != null"""
        )
    owner_quiescence = wait_for_quiescence(
        owner_page, owner_evidence, phase, timeout_ms=timeout_ms
    )
    remote_quiescence = wait_for_quiescence(
        remote_page, remote_evidence, phase, timeout_ms=timeout_ms
    )
    owner_projection = projection_snapshot(owner_page)
    remote_projection = projection_snapshot(remote_page)
    owner_input_epoch = owner_projection.get("input_epoch_ms")
    remote_projection_epoch = remote_projection.get("projection_epoch_ms")
    if owner_input_epoch is not None and remote_projection_epoch is not None:
        remote_projection["projection_latency_ms"] = (
            float(remote_projection_epoch) - float(owner_input_epoch)
        )
    return {
        "target_path": target_path,
        "owner": {
            "projection": owner_projection,
            "quiescence": owner_quiescence,
            "requests": owner_evidence.phase_summary(phase),
        },
        "remote": {
            "projection": remote_projection,
            "quiescence": remote_quiescence,
            "requests": remote_evidence.phase_summary(phase),
        },
    }


def _page_cleared(snapshot: dict[str, Any]) -> bool:
    return any(
        state.get("grid_state") == "loading" and int(state.get("visible_cell_count", 0)) == 0
        for state in snapshot["loading_states"]
    )


def _validate_round(round_result: dict[str, Any]) -> None:
    for role in ("owner", "remote"):
        result = round_result[role]
        snapshot = result["projection"]
        latency = snapshot.get("projection_latency_ms")
        if latency is None or float(latency) > 100.0:
            raise SmokeFailure(f"{role} projection missed 100 ms target: {latency}")
        if snapshot["gallery_root_replaced"] or _page_cleared(snapshot):
            raise SmokeFailure(f"{role} gallery cleared or replaced during projection")
        if abs(float(snapshot["scroll_top_after"]) - float(snapshot["scroll_top_before"])) > 1.0:
            raise SmokeFailure(f"{role} scroll anchor moved during projection: {snapshot}")
        if snapshot["target_still_visible"]:
            raise SmokeFailure(f"{role} retained a conclusively filtered item")
        if not result["quiescence"]["completed"]:
            raise SmokeFailure(f"{role} reconciliation did not quiesce: {result['quiescence']}")
        requests = result["requests"]
        if not 1 <= requests["query_requests"] <= 2:
            raise SmokeFailure(f"{role} missed the query reconciliation bound: {requests}")
        if not 1 <= requests["facet_requests"] <= 2:
            raise SmokeFailure(f"{role} missed the facet reconciliation bound: {requests}")


def _gallery_count_label(page: Any) -> str:
    value = page.locator("[data-grid-state] span").last.text_content()
    return (value or "").strip()


def _projection_p95(values: list[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        raise SmokeFailure("no projection latency samples were recorded")
    position = 0.95 * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def run_browser_scenario(base_url: str, browser_timeout_ms: float) -> dict[str, Any]:
    playwright_error, playwright_timeout_error, sync_playwright = import_playwright()
    evidence_a = BrowserRequestEvidence()
    evidence_b = BrowserRequestEvidence()
    evidence_churn = BrowserRequestEvidence()
    timeout_ms = min(browser_timeout_ms, 15_000)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context_a = browser.new_context(viewport={"width": 1440, "height": 960})
            context_b = browser.new_context(viewport={"width": 1440, "height": 960})
            page_a = context_a.new_page()
            page_b = context_b.new_page()
            _attach_evidence(page_a, evidence_a, browser_timeout_ms)
            _attach_evidence(page_b, evidence_b, browser_timeout_ms)
            for page in (page_a, page_b):
                page.goto(filtered_gallery_url(base_url), wait_until="domcontentloaded")
                _wait_for_ready_gallery(page)
                _open_metrics_panel(page)
            initial_quiescence = {
                "session_a": wait_for_quiescence(page_a, evidence_a, "initial", timeout_ms=timeout_ms),
                "session_b": wait_for_quiescence(page_b, evidence_b, "initial", timeout_ms=timeout_ms),
            }
            if not all(result["completed"] for result in initial_quiescence.values()):
                raise SmokeFailure(f"initial requests did not quiesce: {initial_quiescence}")

            initial_paths = sorted(set(visible_paths(page_a)) & set(visible_paths(page_b)))
            if len(initial_paths) < 2:
                raise SmokeFailure("two sessions did not expose two common unrated items")

            round_one = _run_annotation_round(
                owner_page=page_a,
                owner_evidence=evidence_a,
                remote_page=page_b,
                remote_evidence=evidence_b,
                target_path=initial_paths[0],
                phase="mutation_1",
                timeout_ms=timeout_ms,
            )
            _validate_round(round_one)
            remaining = sorted(set(visible_paths(page_a)) & set(visible_paths(page_b)))
            if not remaining:
                raise SmokeFailure("sessions did not converge on a second visible unrated item")
            round_two = _run_annotation_round(
                owner_page=page_b,
                owner_evidence=evidence_b,
                remote_page=page_a,
                remote_evidence=evidence_a,
                target_path=remaining[0],
                phase="mutation_2",
                timeout_ms=timeout_ms,
            )
            _validate_round(round_two)

            context_churn = browser.new_context(viewport={"width": 1440, "height": 960})
            page_churn = context_churn.new_page()
            _attach_evidence(page_churn, evidence_churn, browser_timeout_ms)
            page_churn.goto(filtered_gallery_url(base_url), wait_until="domcontentloaded")
            _wait_for_ready_gallery(page_churn)
            wait_for_quiescence(
                page_churn, evidence_churn, "initial", timeout_ms=timeout_ms,
            )
            evidence_churn.phase = "superseded_filter"
            superseded_filter_sequence = run_superseded_filter_sequence(page_churn)
            superseded_filter_quiescence = wait_for_quiescence(
                page_churn, evidence_churn, "superseded_filter", timeout_ms=timeout_ms
            )

            session_ids = {
                "session_a": page_a.evaluate("sessionStorage.getItem('lenslet.client_id.session')"),
                "session_b": page_b.evaluate("sessionStorage.getItem('lenslet.client_id.session')"),
            }
            count_labels = {
                "session_a": _gallery_count_label(page_a),
                "session_b": _gallery_count_label(page_b),
            }
            final_paths = {
                "session_a": visible_paths(page_a),
                "session_b": visible_paths(page_b),
            }
            context_a.close()
            context_b.close()
            context_churn.close()
            browser.close()
    except playwright_timeout_error as exc:
        raise SmokeFailure(f"annotation latency scenario timed out: {exc}") from exc
    except playwright_error as exc:
        raise SmokeFailure(f"annotation latency browser failure: {exc}") from exc

    if not all(session_ids.values()) or session_ids["session_a"] == session_ids["session_b"]:
        raise SmokeFailure(f"browser contexts did not retain independent session IDs: {session_ids}")
    if count_labels["session_a"] != count_labels["session_b"]:
        raise SmokeFailure(f"authoritative counts did not converge: {count_labels}")
    projections = [
        (session, role, result[role]["projection"])
        for session, result, role in (
            ("session_a", round_one, "owner"),
            ("session_b", round_one, "remote"),
            ("session_b", round_two, "owner"),
            ("session_a", round_two, "remote"),
        )
    ]
    projection_values = [float(snapshot["projection_latency_ms"]) for _, _, snapshot in projections]
    request_summaries = [
        result[role]["requests"]
        for result in (round_one, round_two)
        for role in ("owner", "remote")
    ]
    loading_states = [
        state
        for _, _, snapshot in projections
        for state in snapshot["loading_states"]
    ]
    return {
        "session_id": session_ids["session_a"],
        "session_ids": session_ids,
        "semantic_revisions": {
            "protocol_present": True,
            "deliberate_superseded_filter_sequence": superseded_filter_sequence,
        },
        "target_path": round_one["target_path"],
        "target_paths": [round_one["target_path"], round_two["target_path"]],
        "initial_visible_paths": initial_paths,
        "final_visible_paths": final_paths["session_a"],
        "final_visible_paths_by_session": final_paths,
        "annotation_projection_ms": round(_projection_p95(projection_values), 3),
        "projection_samples": [
            {
                "session": session,
                "role": role,
                "latency_ms": round(float(snapshot["projection_latency_ms"]), 3),
            }
            for session, role, snapshot in projections
        ],
        "gallery_root_replaced": any(snapshot["gallery_root_replaced"] for _, _, snapshot in projections),
        "active_loading_state_observed": any(bool(state.get("aria_busy")) for state in loading_states),
        "page_clearing_loading_observed": any(_page_cleared(snapshot) for _, _, snapshot in projections),
        "loading_states": loading_states,
        "scroll_top_before": projections[0][2]["scroll_top_before"],
        "scroll_top_after": projections[-1][2]["scroll_top_after"],
        "target_still_visible": any(snapshot["target_still_visible"] for _, _, snapshot in projections),
        "initial_quiescence": initial_quiescence,
        "superseded_filter_quiescence": superseded_filter_quiescence,
        "superseded_filter_evidence": evidence_churn.phase_summary("superseded_filter"),
        "mutation_quiescence": {
            "mutation_1": {role: round_one[role]["quiescence"] for role in ("owner", "remote")},
            "mutation_2": {role: round_two[role]["quiescence"] for role in ("owner", "remote")},
        },
        "rounds": {"mutation_1": round_one, "mutation_2": round_two},
        "count_labels": count_labels,
        "multi_editor_converged": True,
        "query_requests": max(int(summary["query_requests"]) for summary in request_summaries),
        "facet_requests": max(int(summary["facet_requests"]) for summary in request_summaries),
        "mutation_requests": max(int(summary["mutation_requests"]) for summary in request_summaries),
        "query_response_bytes": sum(int(summary["query_response_bytes"]) for summary in request_summaries),
        "facet_response_bytes": sum(int(summary["facet_response_bytes"]) for summary in request_summaries),
        "failed_requests": [failure for summary in request_summaries for failure in summary["failed_requests"]],
        "responses": [response for summary in request_summaries for response in summary["responses"]],
        "acceptance_passed": True,
    }


def build_summary(
    *,
    fixture_name: str,
    scenario: dict[str, Any],
    initial_health: dict[str, Any],
    final_health: dict[str, Any],
    server_log: Path,
) -> dict[str, Any]:
    projection_ms = float(scenario["annotation_projection_ms"])
    query_requests = int(scenario["query_requests"])
    facet_requests = int(scenario["facet_requests"])
    projection_target_met = (
        projection_ms <= 100.0 and not bool(scenario["page_clearing_loading_observed"])
    )
    multi_editor_target_met = bool(scenario.get("multi_editor_converged", False))
    return {
        "schema_version": 1,
        "status": "accepted" if scenario.get("acceptance_passed") else "baseline_recorded",
        "fixture": fixture_name,
        **scenario,
        "analysis_diagnostics": final_health.get("hotpath", {}),
        "initial_health": initial_health,
        "server_log": str(server_log),
        "observations": {
            "current_duplicate_or_reset_behavior": (
                query_requests > 1
                or facet_requests > 1
                or bool(scenario["page_clearing_loading_observed"])
            ),
            "post_fix_projection_target_met": projection_target_met,
            "post_fix_no_page_clear_target_met": not bool(
                scenario["page_clearing_loading_observed"]
            ),
            "multi_editor_target_met": multi_editor_target_met,
        },
    }


def main() -> int:
    args = parse_args()
    fixture_root = Path(tempfile.mkdtemp(prefix="lenslet-annotation-latency-")).resolve()
    server_log: Path | None = None
    try:
        fixture = build_synthetic_table_fixture(
            fixture_root,
            row_count=args.rows,
            metric_count=args.metrics,
            rated_count=args.rated,
        )
        port = choose_port(args.host, args.port)
        with running_lenslet_server(
            fixture.parquet_path,
            host=args.host,
            port=port,
            extra_args=[
                "--source-column",
                "image_path",
                "--no-cache-dimensions",
                "--verbose",
            ],
            cwd=Path(__file__).resolve().parents[3],
            log_prefix="lenslet-annotation-latency-server-",
        ) as server:
            server_log = server.log_path
            initial_health = wait_for_health(server.base_url, args.server_timeout_seconds)
            scenario = run_browser_scenario(server.base_url, args.browser_timeout_ms)
            final_health = wait_for_health(server.base_url, args.server_timeout_seconds)
            summary = build_summary(
                fixture_name=fixture.name,
                scenario=scenario,
                initial_health=initial_health,
                final_health=final_health,
                server_log=server.log_path,
            )
        if args.output_json is not None:
            write_json_evidence(args.output_json, summary, sort_keys=False)
        print(json.dumps(summary, indent=2))
        return 0
    except SmokeFailure as exc:
        print(f"[annotation-latency] FAILED: {exc}", file=sys.stderr)
        if server_log is not None:
            print(read_log_tail(server_log), file=sys.stderr)
        return 1
    finally:
        if not args.keep_fixture:
            shutil.rmtree(fixture_root, ignore_errors=True)


def _encode_path(path: str) -> str:
    from urllib.parse import quote

    return quote(path, safe="~()*!.'-")


if __name__ == "__main__":
    raise SystemExit(main())
