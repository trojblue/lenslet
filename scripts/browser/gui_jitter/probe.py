#!/usr/bin/env python3
"""Playwright jitter probe for front-end geometry stability checks."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

if __name__ == "__main__" and not __package__:
    raise SystemExit("Run from the repository root with: python -m scripts.browser.gui_jitter.probe")

from scripts.browser.gui_jitter.fixtures import build_fixture_dataset as _build_fixture_dataset
from scripts.browser.gui_jitter.grid import GridProbeConfig, run_grid_probe
from scripts.browser.gui_jitter.inspector import run_inspector_probe
from scripts.browser.gui_jitter.metrics import run_metrics_probe
from scripts.browser.gui_jitter.toolbar import run_toolbar_probe
from scripts.browser.gui_jitter.shared import (
    build_base_url as _build_base_url,
    write_json_atomic as _write_json_atomic,
)
from scripts.smoke_harness import (
    SmokeFailure,
    choose_port,
    launch_lenslet,
    stop_process,
    wait_for_health,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run UI jitter probe scenarios.")
    parser.add_argument(
        "--scenario",
        choices=["toolbar", "grid", "inspector", "metrics"],
        required=True,
        help="Probe scenario to execute.",
    )
    parser.add_argument("--max-delta-px", type=float, default=1.0, help="Maximum allowed CSS-pixel delta.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind Lenslet server.")
    parser.add_argument("--port", type=int, default=7070, help="Preferred Lenslet port.")
    parser.add_argument(
        "--fixture-profile",
        choices=["default", "table-1585"],
        default="default",
        help="Named generated fixture profile. table-1585 uses the paginated table backend.",
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
        help="Optional existing dataset directory. Temporary fixture is created when omitted.",
    )
    parser.add_argument(
        "--keep-dataset",
        action="store_true",
        help="Keep generated temporary fixture dataset.",
    )
    parser.add_argument(
        "--server-timeout-seconds",
        type=float,
        default=60.0,
        help="Timeout waiting for Lenslet /health.",
    )
    parser.add_argument(
        "--browser-timeout-ms",
        type=float,
        default=30_000,
        help="Playwright default timeout in milliseconds.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path for machine-readable probe output.",
    )
    parser.add_argument(
        "--expected-metric-key",
        default=None,
        help="Optional metric key that must appear in metric sort/filter controls.",
    )
    parser.add_argument(
        "--forbid-metric-key",
        action="append",
        default=[],
        help="Metric key that must not appear in metric sort/filter controls. May be provided multiple times.",
    )
    parser.add_argument(
        "--metric-filter-min",
        type=float,
        default=None,
        help="Optional minimum bound for metric range-filter validation.",
    )
    parser.add_argument(
        "--metric-filter-max",
        type=float,
        default=None,
        help="Optional maximum bound for metric range-filter validation.",
    )
    return parser.parse_args()


def _write_output_json(path: Path | None, summary: dict[str, Any]) -> None:
    if path is None:
        return
    _write_json_atomic(path, summary)


def main() -> int:
    args = parse_args()
    dataset_dir: Path
    cleanup_dataset = False

    if args.dataset_dir is not None:
        dataset_dir = args.dataset_dir.resolve()
        if not dataset_dir.exists():
            raise SystemExit(f"Dataset directory does not exist: {dataset_dir}")
    else:
        dataset_dir = Path(tempfile.mkdtemp(prefix="lenslet-jitter-probe-")).resolve()
        cleanup_dataset = not args.keep_dataset
        try:
            _build_fixture_dataset(dataset_dir)
        except Exception:
            if cleanup_dataset:
                shutil.rmtree(dataset_dir, ignore_errors=True)
            raise

    port = choose_port(args.host, args.port)
    base_url = _build_base_url(args.host, port)
    table_profile = args.fixture_profile == "table-1585"
    source_path = (
        dataset_dir / "metrics_items.parquet"
        if args.scenario == "metrics" or table_profile
        else dataset_dir
    )
    extra_args = ["--verbose"]
    if args.scenario == "metrics" or table_profile:
        extra_args.extend(["--source-column", "source", "--base-dir", str(dataset_dir)])
    process = launch_lenslet(
        source_path,
        host=args.host,
        port=port,
        extra_args=extra_args,
        cwd=Path(__file__).resolve().parents[1],
    )

    summary: dict[str, Any]
    try:
        wait_for_health(base_url, args.server_timeout_seconds)
        if process.poll() is not None:
            raise SmokeFailure(f"Lenslet exited unexpectedly with code {process.returncode}.")

        if args.scenario == "toolbar":
            result = run_toolbar_probe(base_url, args.max_delta_px, args.browser_timeout_ms)
        elif args.scenario == "grid":
            result = run_grid_probe(
                GridProbeConfig(
                    base_url=base_url,
                    max_delta_px=args.max_delta_px,
                    browser_timeout_ms=args.browser_timeout_ms,
                    expected_metric_key=args.expected_metric_key,
                    forbidden_metric_keys=tuple(args.forbid_metric_key),
                    metric_filter_min=args.metric_filter_min,
                    metric_filter_max=args.metric_filter_max,
                    fixture_profile=args.fixture_profile,
                )
            )
        elif args.scenario == "inspector":
            result = run_inspector_probe(base_url, args.max_delta_px, args.browser_timeout_ms)
        else:
            result = run_metrics_probe(base_url, args.max_delta_px, args.browser_timeout_ms)

        summary = {
            "status": "passed",
            "base_url": base_url,
            "dataset_dir": str(dataset_dir),
            "scenario": result.scenario,
            "fixture_profile": args.fixture_profile,
            "max_delta_px": result.max_delta_px,
            "max_anchor_delta_px": result.max_anchor_delta_px,
            "max_toolbar_delta_px": result.max_toolbar_delta_px,
            "max_top_stack_delta_px": result.max_top_stack_delta_px,
            "max_grid_width_delta_px": result.max_grid_width_delta_px,
            "max_inspector_delta_px": result.max_inspector_delta_px,
            "checks": result.checks,
        }
        print(json.dumps(summary, indent=2))
        _write_output_json(args.output_json, summary)
        return 0
    except (OSError, RuntimeError, SmokeFailure, ValueError) as exc:
        summary = {
            "status": "failed",
            "base_url": base_url,
            "dataset_dir": str(dataset_dir),
            "scenario": args.scenario,
            "fixture_profile": args.fixture_profile,
            "max_delta_px": args.max_delta_px,
            "error": str(exc),
        }
        evidence = getattr(exc, "evidence", None)
        if isinstance(evidence, dict):
            summary["checks"] = evidence
        print(json.dumps(summary, indent=2), file=sys.stderr)
        _write_output_json(args.output_json, summary)
        return 1
    finally:
        stop_process(process, kill_timeout_seconds=10.0)
        if cleanup_dataset:
            shutil.rmtree(dataset_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
