#!/usr/bin/env python3
"""Record the live annotation/filter baseline without enforcing post-fix targets."""

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


def run_browser_scenario(base_url: str, browser_timeout_ms: float) -> dict[str, Any]:
    playwright_error, playwright_timeout_error, sync_playwright = import_playwright()
    evidence = BrowserRequestEvidence()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 960})
            page = context.new_page()
            page.set_default_timeout(browser_timeout_ms)
            page.on("request", evidence.on_request)
            page.on("response", evidence.on_response)
            page.on("requestfailed", evidence.on_request_failed)
            page.on("requestfinished", evidence.on_request_finished)
            page.goto(filtered_gallery_url(base_url), wait_until="domcontentloaded")
            gallery = page.get_by_role("grid", name="Gallery")
            gallery.wait_for(state="visible")
            page.wait_for_function(
                """() => document.querySelectorAll('[role="gridcell"][id^="cell-"]').length > 0
                  && document.querySelector('[role="grid"][aria-label="Gallery"]')?.getAttribute('aria-busy') !== 'true'"""
            )
            initial_paths = visible_paths(page)
            if not initial_paths:
                raise SmokeFailure("filtered gallery did not expose a visible unrated item")
            page.locator('button[title="Filters"][aria-haspopup="dialog"]').click()
            page.get_by_role("button", name="Open Metrics Panel").click()
            initial_quiescence = wait_for_quiescence(
                page,
                evidence,
                "initial",
                timeout_ms=min(browser_timeout_ms, 15_000),
            )
            if not initial_quiescence["completed"]:
                raise SmokeFailure(
                    f"initial query/facet requests did not quiesce: {initial_quiescence}"
                )
            if evidence.phase_summary("initial")["facet_requests"] < 1:
                raise SmokeFailure("opening Metrics did not issue the baseline facets request")

            evidence.phase = "superseded_filter"
            superseded_filter_sequence = run_superseded_filter_sequence(page)
            superseded_filter_quiescence = wait_for_quiescence(
                page,
                evidence,
                "superseded_filter",
                timeout_ms=min(browser_timeout_ms, 15_000),
            )
            target_path = initial_paths[0]
            target_cell = page.locator(f'[id="cell-{_encode_path(target_path)}"]')
            evidence.phase = "selection"
            target_cell.click()
            star_button = page.get_by_role("button", name="1 star")
            star_button.wait_for(state="visible")

            install_projection_probe(page, target_path)
            evidence.phase = "mutation"
            star_button.click()
            page.wait_for_function(
                """() => window.__lensletAnnotationLatencyProbe?.projectionTimestamp != null"""
            )
            mutation_quiescence = wait_for_quiescence(
                page,
                evidence,
                "mutation",
                timeout_ms=min(browser_timeout_ms, 15_000),
            )
            snapshot = projection_snapshot(page)
            final_paths = visible_paths(page)
            session_id = page.evaluate("sessionStorage.getItem('lenslet.client_id.session')")
            context.close()
            browser.close()
    except playwright_timeout_error as exc:
        raise SmokeFailure(f"annotation latency scenario timed out: {exc}") from exc
    except playwright_error as exc:
        raise SmokeFailure(f"annotation latency browser failure: {exc}") from exc

    mutation_requests = evidence.phase_summary("mutation")
    loading_states = snapshot["loading_states"]
    active_loading_state_observed = any(bool(state.get("aria_busy")) for state in loading_states)
    page_clearing_loading_observed = any(
        state.get("grid_state") == "loading" and int(state.get("visible_cell_count", 0)) == 0
        for state in loading_states
    )
    return {
        "session_id": session_id,
        "semantic_revisions": {
            "protocol_present": False,
            "deliberate_superseded_filter_sequence": superseded_filter_sequence,
        },
        "target_path": target_path,
        "initial_visible_paths": initial_paths,
        "final_visible_paths": final_paths,
        "annotation_projection_ms": round(float(snapshot["projection_latency_ms"]), 3),
        "gallery_root_replaced": bool(snapshot["gallery_root_replaced"]),
        "active_loading_state_observed": active_loading_state_observed,
        "page_clearing_loading_observed": page_clearing_loading_observed,
        "loading_states": loading_states,
        "scroll_top_before": snapshot["scroll_top_before"],
        "scroll_top_after": snapshot["scroll_top_after"],
        "target_still_visible": snapshot["target_still_visible"],
        "initial_quiescence": initial_quiescence,
        "superseded_filter_quiescence": superseded_filter_quiescence,
        "superseded_filter_evidence": evidence.phase_summary("superseded_filter"),
        "mutation_quiescence": mutation_quiescence,
        **mutation_requests,
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
    return {
        "schema_version": 1,
        "status": "baseline_recorded",
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
            "post_fix_projection_target_met": (
                projection_ms <= 100.0 and not bool(scenario["page_clearing_loading_observed"])
            ),
            "post_fix_no_page_clear_target_met": not bool(
                scenario["page_clearing_loading_observed"]
            ),
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
