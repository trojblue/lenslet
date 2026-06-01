#!/usr/bin/env python3
"""Browser evidence entrypoint for viewer flicker, pan, click, and Back checks."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

if __name__ == "__main__" and not __package__:
    raise SystemExit("Run from the repository root with: python -m scripts.browser.viewer_probe.flicker_back")

from scripts.smoke_harness import (
    choose_port,
    import_playwright,
    read_log_tail,
    running_lenslet_server,
    server_base_url,
    wait_for_health,
    write_json_evidence,
)
from scripts.browser.viewer_probe.back import back_acceptance_failures, run_back_probe
from scripts.browser.viewer_probe.config import BACK_SWEEP_VIEWPORTS, ViewerProbeFailure
from scripts.browser.viewer_probe.fixtures import build_fixture_dataset
from scripts.browser.viewer_probe.interaction_checks import interactions_acceptance_failures
from scripts.browser.viewer_probe.interactions import run_interactions_probe
from scripts.browser.viewer_probe.open import ViewerOpenProbeConfig, run_viewer_open_probe
from scripts.browser.viewer_probe.open_checks import viewer_acceptance_failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect live-browser evidence for viewer flicker, pan, click, and Back regressions."
    )
    parser.add_argument(
        "--mode",
        choices=("baseline", "viewer", "interactions", "back", "all"),
        default="baseline",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7070)
    parser.add_argument("--dataset-dir", type=Path, default=None)
    parser.add_argument("--keep-dataset", action="store_true")
    parser.add_argument("--server-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--browser-timeout-ms", type=float, default=30_000)
    parser.add_argument("--delayed-file-route-ms", type=int, default=350)
    parser.add_argument("--open-sample-frames", type=int, default=24)
    parser.add_argument("--open-sample-interval-ms", type=int, default=20)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path(tempfile.gettempdir()) / "lenslet-viewer-flicker-back.json",
        help="Path for machine-readable probe evidence.",
    )
    return parser.parse_args()


def resolve_dataset(args: argparse.Namespace) -> tuple[Path, bool]:
    if args.dataset_dir is not None:
        dataset_dir = args.dataset_dir.resolve()
        if not dataset_dir.exists():
            raise SystemExit(f"Dataset directory does not exist: {dataset_dir}")
        return dataset_dir, False

    dataset_dir = Path(tempfile.mkdtemp(prefix="lenslet-viewer-probe-")).resolve()
    try:
        build_fixture_dataset(dataset_dir)
    except Exception:
        if not args.keep_dataset:
            shutil.rmtree(dataset_dir, ignore_errors=True)
        raise
    return dataset_dir, not args.keep_dataset


def run_browser_checks(base_url: str, args: argparse.Namespace) -> dict[str, Any]:
    _, _, sync_playwright = import_playwright()
    scenarios: dict[str, Any] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1200, "height": 820})
        try:
            if args.mode in ("baseline", "viewer", "all"):
                scenarios["viewerOpen"] = run_viewer_open_probe(
                    context,
                    base_url,
                    config=ViewerOpenProbeConfig(
                        timeout_ms=args.browser_timeout_ms,
                        frames=args.open_sample_frames,
                        interval_ms=args.open_sample_interval_ms,
                        delayed_file_route_ms=args.delayed_file_route_ms,
                    ),
                )
            if args.mode in ("baseline", "back", "all"):
                scenarios["backHitTarget"] = run_back_probe(
                    context,
                    base_url,
                    timeout_ms=args.browser_timeout_ms,
                )
            if args.mode in ("baseline", "interactions", "all"):
                scenarios["interactions"] = run_interactions_probe(
                    context,
                    base_url,
                    timeout_ms=args.browser_timeout_ms,
                )
        finally:
            context.close()
            browser.close()
    return scenarios


def acceptance_failures_for_mode(mode: str, scenarios: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if mode in ("viewer", "all"):
        failures.extend(viewer_acceptance_failures(scenarios.get("viewerOpen")))
    if mode in ("back", "all"):
        failures.extend(back_acceptance_failures(scenarios.get("backHitTarget")))
    if mode in ("interactions", "all"):
        failures.extend(interactions_acceptance_failures(scenarios.get("interactions")))
    return failures


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    write_json_evidence(path, summary, sort_keys=False)


def main() -> int:
    args = parse_args()
    dataset_dir, cleanup_dataset = resolve_dataset(args)
    port = choose_port(args.host, args.port)
    base_url = server_base_url(args.host, port)
    summary: dict[str, Any] = {
        "status": "running",
        "mode": args.mode,
        "baseUrl": base_url,
        "datasetDir": str(dataset_dir),
        "serverLog": None,
        "backSweepViewports": [
            {"name": item.name, "width": item.width, "height": item.height}
            for item in BACK_SWEEP_VIEWPORTS
        ],
        "delayedFileRouteMs": args.delayed_file_route_ms,
        "scenarios": {},
        "warnings": [],
    }

    try:
        with running_lenslet_server(
            dataset_dir,
            host=args.host,
            port=port,
            extra_args=["--verbose", "--no-skip-indexing"],
            cwd=Path(__file__).resolve().parents[1],
            log_prefix="lenslet-viewer-probe-server-",
        ) as server:
            summary["baseUrl"] = server.base_url
            summary["serverLog"] = str(server.log_path)
            summary["initialHealth"] = wait_for_health(server.base_url, args.server_timeout_seconds)
            if server.process.poll() is not None:
                raise ViewerProbeFailure(f"Lenslet exited unexpectedly with code {server.process.returncode}.")

            summary["scenarios"] = run_browser_checks(server.base_url, args)
            acceptance_failures = acceptance_failures_for_mode(args.mode, summary["scenarios"])
            summary["acceptance"] = {
                "mode": args.mode,
                "failures": acceptance_failures,
            }
            summary["finalHealth"] = wait_for_health(server.base_url, args.server_timeout_seconds)
            if acceptance_failures:
                raise ViewerProbeFailure(
                    "acceptance checks failed: " + "; ".join(acceptance_failures[:8])
                )

        summary["status"] = "passed"
        write_summary(args.output_json, summary)
        print(json.dumps(summary, indent=2))
        return 0
    except Exception as exc:
        summary["status"] = "failed"
        summary["error"] = str(exc)
        server_log = summary.get("serverLog")
        summary["serverLogTail"] = read_log_tail(Path(server_log), line_count=80) if isinstance(server_log, str) else "<unavailable>"
        write_summary(args.output_json, summary)
        print(json.dumps(summary, indent=2), file=sys.stderr)
        return 1
    finally:
        if cleanup_dataset:
            shutil.rmtree(dataset_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
