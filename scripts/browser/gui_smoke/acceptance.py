#!/usr/bin/env python3
"""Default headless browser smoke suite for Lenslet GUI acceptance flows."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

if __name__ == "__main__" and not __package__:
    raise SystemExit("Run from the repository root with: python -m scripts.browser.gui_smoke.acceptance")

from scripts.browser.gui_smoke.fixtures import (
    build_backend_browse_filter_table_fixture,
    build_derived_metric_table_fixture,
    build_fixture_dataset,
)
from scripts.browser.gui_smoke.scenarios import (
    BackendBrowseFilterSmokeResult,
    DerivedMetricSmokeResult,
    SmokeResult,
    run_backend_browse_filter_checks,
    run_browser_checks,
    run_derived_metric_checks,
)
from scripts.smoke_harness import (
    SmokeFailure,
    choose_port,
    read_log_tail,
    running_lenslet_server,
    wait_for_health,
    write_json_evidence,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Lenslet browser acceptance smoke checks.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind the Lenslet server (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=7070, help="Preferred port (default: 7070).")
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
        help="Optional existing dataset directory. If omitted, a temporary fixture dataset is generated.",
    )
    parser.add_argument(
        "--keep-dataset",
        action="store_true",
        help="Keep generated temporary dataset after completion.",
    )
    parser.add_argument(
        "--server-timeout-seconds",
        type=float,
        default=60.0,
        help="Timeout for initial /health availability (default: 60).",
    )
    parser.add_argument(
        "--browser-timeout-ms",
        type=float,
        default=45_000,
        help="Playwright default timeout in milliseconds (default: 45000).",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path for machine-readable smoke summary JSON.",
    )
    parser.add_argument(
        "--strict-reentry-anchor",
        action="store_true",
        help="Fail if re-entry top-anchor is not an exact path match.",
    )
    return parser.parse_args()


def resolve_dataset(args: argparse.Namespace) -> tuple[Path, bool]:
    if args.dataset_dir is not None:
        dataset_dir = args.dataset_dir.resolve()
        if not dataset_dir.exists():
            raise SystemExit(f"Dataset directory does not exist: {dataset_dir}")
        return dataset_dir, False

    dataset_dir = Path(tempfile.mkdtemp(prefix="lenslet-gui-smoke-")).resolve()
    try:
        build_fixture_dataset(dataset_dir)
    except Exception:
        if not args.keep_dataset:
            shutil.rmtree(dataset_dir, ignore_errors=True)
        raise
    return dataset_dir, not args.keep_dataset


def parse_iso8601_timestamp(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or raw.strip() == "":
        return None
    candidate = raw.strip()
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        return None


def has_indexing_lifecycle_proof(payload: dict[str, Any]) -> bool:
    indexing = payload.get("indexing")
    if not isinstance(indexing, dict):
        return False
    if indexing.get("state") != "ready":
        return False
    started_at = parse_iso8601_timestamp(indexing.get("started_at"))
    finished_at = parse_iso8601_timestamp(indexing.get("finished_at"))
    if started_at is None or finished_at is None:
        return False
    return finished_at >= started_at


def build_summary(
    *,
    base_url: str,
    dataset_dir: Path,
    server_log: Path,
    initial_health: dict[str, Any],
    final_health: dict[str, Any],
    result: SmokeResult,
    backend_filter_result: BackendBrowseFilterSmokeResult | None = None,
    backend_filter_server_log: Path | None = None,
    derived_metric_result: DerivedMetricSmokeResult | None = None,
    derived_metric_server_log: Path | None = None,
) -> dict[str, Any]:
    indexing_lifecycle_proof = has_indexing_lifecycle_proof(initial_health) or has_indexing_lifecycle_proof(final_health)

    warnings: list[str] = []
    if not result.indexing_banner_seen and not indexing_lifecycle_proof:
        warnings.append(
            "Indexing banner was not observed and `/health.indexing` did not provide deterministic lifecycle timestamps."
        )
    if not result.anchor_reentry_exact:
        warnings.append(
            "Folder re-entry anchor did not restore to the exact pre-switch path in this run."
        )

    return {
        "base_url": base_url,
        "dataset_dir": str(dataset_dir),
        "server_log": str(server_log),
        "initial_health": initial_health,
        "final_health": final_health,
        "checks": {
            "indexing_banner_seen": result.indexing_banner_seen,
            "indexing_lifecycle_proof": indexing_lifecycle_proof,
            "sidebar_resize_delta_px": result.sidebar_resize_delta_px,
            "left_collapsed_width_px": result.left_collapsed_width_px,
            "left_hotkey_reopen_width_px": result.left_hotkey_reopen_width_px,
            "right_resized_width_px": result.right_resized_width_px,
            "center_width_after_right_resize_px": result.center_width_after_right_resize_px,
            "anchor_before": result.anchor_before,
            "anchor_restored": result.anchor_restored,
            "anchor_settled": result.anchor_settled,
            "anchor_reentry_exact": result.anchor_reentry_exact,
            "search_visible_matches": result.search_visible_matches,
            "viewer_restore_open_path": result.viewer_restore_open_path,
            "viewer_restore_navigated_path": result.viewer_restore_navigated_path,
            "viewer_restore_focused_path": result.viewer_restore_focused_path,
            "inspector_default_order": result.inspector_default_order,
            "inspector_reordered_order": result.inspector_reordered_order,
            "inspector_reloaded_order": result.inspector_reloaded_order,
            "inspector_reorder_persisted": result.inspector_reordered_order == result.inspector_reloaded_order,
            "inspector_compare_over_cap_message": result.inspector_compare_over_cap_message,
            "backend_browse_filter": None if backend_filter_result is None else {
                "scope_total": backend_filter_result.scope_total,
                "filtered_total": backend_filter_result.filtered_total,
                "initial_visible_paths": backend_filter_result.initial_visible_paths,
                "filtered_visible_paths": backend_filter_result.filtered_visible_paths,
                "toolbar_count_label": backend_filter_result.toolbar_count_label,
                "shared_url_sort": backend_filter_result.shared_url_sort,
                "shared_url_filter_count": backend_filter_result.shared_url_filter_count,
                "shared_url_restored_paths": backend_filter_result.shared_url_restored_paths,
                "server_log": None if backend_filter_server_log is None else str(backend_filter_server_log),
            },
            "derived_metric_ranking": None if derived_metric_result is None else {
                "metric_inputs": derived_metric_result.metric_inputs,
                "backend_request_seen": derived_metric_result.backend_request_seen,
                "restored_sort_key": derived_metric_result.restored_sort_key,
                "visible_paths_after_rank": derived_metric_result.visible_paths_after_rank,
                "metric_rail_summary_count": derived_metric_result.metric_rail_summary_count,
                "server_log": None if derived_metric_server_log is None else str(derived_metric_server_log),
            },
        },
        "warnings": warnings,
        "status": "passed",
    }


def write_output(path: Path | None, summary: dict[str, Any]) -> None:
    if path is None:
        return
    write_json_evidence(path, summary, sort_keys=False)


def main() -> int:
    args = parse_args()
    dataset_dir, cleanup_dir = resolve_dataset(args)
    backend_filter_dataset_dir = Path(tempfile.mkdtemp(prefix="lenslet-backend-filter-smoke-")).resolve()
    derived_dataset_dir = Path(tempfile.mkdtemp(prefix="lenslet-derived-metric-smoke-")).resolve()
    log_path: Path | None = None

    try:
        backend_filter_table_path = build_backend_browse_filter_table_fixture(backend_filter_dataset_dir)
        backend_filter_target_paths = [
            "/backend-query/target_1004.jpg",
            "/backend-query/target_1005.jpg",
        ]
        derived_table_path = build_derived_metric_table_fixture(derived_dataset_dir)
        port = choose_port(args.host, args.port)

        with running_lenslet_server(
            dataset_dir,
            host=args.host,
            port=port,
            extra_args=["--verbose"],
            cwd=Path(__file__).resolve().parents[1],
            log_prefix="lenslet-gui-smoke-server-",
        ) as server:
            log_path = server.log_path
            initial_health = wait_for_health(server.base_url, args.server_timeout_seconds)
            if server.process.poll() is not None:
                raise SmokeFailure(f"Lenslet exited unexpectedly with code {server.process.returncode}.")

            result = run_browser_checks(server.base_url, args.browser_timeout_ms, args.strict_reentry_anchor)
            final_health = wait_for_health(server.base_url, args.server_timeout_seconds)

        backend_filter_port = choose_port(args.host, args.port)
        with running_lenslet_server(
            backend_filter_table_path,
            host=args.host,
            port=backend_filter_port,
            extra_args=["--source-column", "image_path", "--no-cache-dimensions", "--verbose"],
            cwd=Path(__file__).resolve().parents[1],
            log_prefix="lenslet-backend-filter-smoke-server-",
        ) as backend_filter_server:
            log_path = backend_filter_server.log_path
            _backend_filter_initial_health = wait_for_health(
                backend_filter_server.base_url,
                args.server_timeout_seconds,
            )
            if backend_filter_server.process.poll() is not None:
                raise SmokeFailure(f"Lenslet exited unexpectedly with code {backend_filter_server.process.returncode}.")
            backend_filter_result = run_backend_browse_filter_checks(
                backend_filter_server.base_url,
                args.browser_timeout_ms,
                categorical_key="source_column",
                categorical_value="v0603_ema14k_image_url",
                expected_paths=backend_filter_target_paths,
            )
            _backend_filter_final_health = wait_for_health(
                backend_filter_server.base_url,
                args.server_timeout_seconds,
            )

        derived_port = choose_port(args.host, args.port)
        with running_lenslet_server(
            derived_table_path,
            host=args.host,
            port=derived_port,
            extra_args=["--source-column", "image_path", "--no-cache-dimensions", "--verbose"],
            cwd=Path(__file__).resolve().parents[1],
            log_prefix="lenslet-derived-metric-smoke-server-",
        ) as derived_server:
            log_path = derived_server.log_path
            _derived_initial_health = wait_for_health(derived_server.base_url, args.server_timeout_seconds)
            if derived_server.process.poll() is not None:
                raise SmokeFailure(f"Lenslet exited unexpectedly with code {derived_server.process.returncode}.")
            derived_metric_result = run_derived_metric_checks(derived_server.base_url, args.browser_timeout_ms)
            _derived_final_health = wait_for_health(derived_server.base_url, args.server_timeout_seconds)

            summary = build_summary(
                base_url=server.base_url,
                dataset_dir=dataset_dir,
                server_log=server.log_path,
                initial_health=initial_health,
                final_health=final_health,
                result=result,
                backend_filter_result=backend_filter_result,
                backend_filter_server_log=backend_filter_server.log_path,
                derived_metric_result=derived_metric_result,
                derived_metric_server_log=derived_server.log_path,
            )
            print(json.dumps(summary, indent=2))
            write_output(args.output_json, summary)
            return 0
    except Exception as exc:
        tail = read_log_tail(log_path) if log_path is not None else "<unavailable>"
        print(f"[gui-smoke] FAILED: {exc}", file=sys.stderr)
        print(f"[gui-smoke] Server log tail ({log_path}):\n{tail}", file=sys.stderr)
        return 1
    finally:
        if cleanup_dir and dataset_dir is not None:
            shutil.rmtree(dataset_dir, ignore_errors=True)
        shutil.rmtree(backend_filter_dataset_dir, ignore_errors=True)
        shutil.rmtree(derived_dataset_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
