#!/usr/bin/env python3
"""Playwright smoke test for large recursive browse scenarios.

Scenario target:
- 40,000 image entries distributed across 10,000 folders
- image dimensions 100x200
- verify page opens quickly enough and UI stays responsive while scrolling
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote

from PIL import Image
from scripts.smoke_harness import (
    SmokeFailure,
    choose_port,
    import_playwright,
    launch_lenslet,
    stop_process,
    wait_for_health,
)

FIXTURE_VERSION = 1
BROWSE_ENDPOINTS = ("folders", "thumb", "file")
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_BASELINE_FILE = SCRIPT_DIR / "playwright_large_tree_smoke_baselines.json"
DEFAULT_BASELINE_PROFILE = "primary_large_no_write"


@dataclass(frozen=True)
class FixtureSpec:
    total_images: int
    total_folders: int
    image_width: int
    image_height: int
    jpeg_quality: int


@dataclass(frozen=True)
class SmokeBaselineProfile:
    name: str
    gate_tier: str
    dataset_dir: Path
    total_images: int
    total_folders: int
    image_width: int
    image_height: int
    jpeg_quality: int
    first_grid_threshold_seconds: float
    first_grid_hotpath_threshold_ms: float
    first_thumbnail_threshold_ms: float
    interaction_seconds: float
    max_frame_gap_ms: float
    write_mode: bool
    expectations: str | None


@dataclass(frozen=True)
class SmokeResult:
    baseline_file: str
    baseline_profile: str
    gate_tier: str
    write_mode: bool
    dataset_dir: str
    source_path: str
    total_images: int
    total_folders: int
    first_grid_visible_seconds: float
    first_grid_threshold_seconds: float
    first_grid_hotpath_latency_ms: int | None
    first_grid_hotpath_threshold_ms: float
    first_thumbnail_latency_ms: int | None
    first_thumbnail_threshold_ms: float
    max_frame_gap_ms: float
    max_frame_gap_threshold_ms: float
    average_frame_gap_ms: float
    sampled_frames: int
    request_budget_limits: dict[str, int]
    request_budget_peak_inflight: dict[str, int]
    page_errors: int
    console_errors: int
    health_state: str
    indexing_done: int | None
    indexing_total: int | None
    scope_path: str | None
    metric_key: str | None
    forbidden_metric_key: str | None
    metric_sort_desc_top_path: str | None
    metric_sort_asc_top_path: str | None
    metric_filter_count_before: int | None
    metric_filter_count_after: int | None
    metric_filter_max: float | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a large-tree Playwright browse smoke test.")
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=None,
        help="Dataset fixture directory (defaults to selected baseline profile value).",
    )
    parser.add_argument(
        "--source-path",
        type=Path,
        default=None,
        help="Optional Lenslet source path override (for example a parquet file) to probe instead of the fixture dataset.",
    )
    parser.add_argument("--total-images", type=int, default=None, help="Total fixture images.")
    parser.add_argument("--total-folders", type=int, default=None, help="Total fixture folders.")
    parser.add_argument("--image-width", type=int, default=None, help="Fixture image width.")
    parser.add_argument("--image-height", type=int, default=None, help="Fixture image height.")
    parser.add_argument("--jpeg-quality", type=int, default=None, help="Fixture JPEG quality.")
    parser.add_argument(
        "--regenerate-fixture",
        action="store_true",
        help="Delete and rebuild fixture directory before running smoke checks.",
    )
    parser.add_argument(
        "--baseline-file",
        type=Path,
        default=DEFAULT_BASELINE_FILE,
        help=f"Baseline profile configuration file (default: {DEFAULT_BASELINE_FILE}).",
    )
    parser.add_argument(
        "--baseline-profile",
        default=DEFAULT_BASELINE_PROFILE,
        help=f"Baseline profile name (default: {DEFAULT_BASELINE_PROFILE}).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host for Lenslet server.")
    parser.add_argument("--port", type=int, default=7070, help="Preferred Lenslet port.")
    parser.add_argument(
        "--health-timeout-seconds",
        type=float,
        default=300.0,
        help="Timeout waiting for /health to become reachable.",
    )
    parser.add_argument(
        "--browser-timeout-ms",
        type=float,
        default=90_000,
        help="Playwright default timeout in milliseconds.",
    )
    parser.add_argument(
        "--first-grid-threshold-seconds",
        type=float,
        default=None,
        help="Fail if first visible grid cell takes longer than this threshold.",
    )
    parser.add_argument(
        "--first-grid-hotpath-threshold-ms",
        type=float,
        default=None,
        help="Fail if first-grid telemetry exceeds this threshold.",
    )
    parser.add_argument(
        "--first-thumbnail-threshold-ms",
        type=float,
        default=None,
        help="Fail if first thumbnail telemetry exceeds this threshold.",
    )
    parser.add_argument(
        "--interaction-seconds",
        type=float,
        default=None,
        help="Duration to run scroll responsiveness probe.",
    )
    parser.add_argument(
        "--max-frame-gap-ms",
        type=float,
        default=None,
        help="Fail if UI frame gap exceeds this threshold during scroll probe.",
    )
    parser.add_argument(
        "--write-mode",
        action="store_true",
        help="Run Lenslet in write mode for dual-mode validation evidence.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to write machine-readable smoke summary JSON.",
    )
    parser.add_argument(
        "--scope-path",
        default=None,
        help="Optional scope path to open via hash routing before running browser checks.",
    )
    parser.add_argument(
        "--metric-key",
        default=None,
        help="Optional metric key to verify in the sort menu and metrics panel.",
    )
    parser.add_argument(
        "--forbid-metric-key",
        default=None,
        help="Optional metric key that must not appear in metric sort/filter controls.",
    )
    return resolve_args_with_baseline(parser.parse_args())


def _profile_value(raw_profile: dict[str, Any], key: str) -> Any:
    if key not in raw_profile:
        raise SmokeFailure(f"baseline profile is missing required field: {key}")
    return raw_profile[key]


def _profile_int(raw_profile: dict[str, Any], key: str) -> int:
    raw = _profile_value(raw_profile, key)
    if isinstance(raw, bool):
        raise SmokeFailure(f"baseline profile field '{key}' must be an integer")
    if isinstance(raw, (int, float)):
        return int(raw)
    if isinstance(raw, str):
        try:
            return int(float(raw.strip()))
        except ValueError as exc:
            raise SmokeFailure(f"baseline profile field '{key}' must be an integer") from exc
    raise SmokeFailure(f"baseline profile field '{key}' must be an integer")


def _profile_float(raw_profile: dict[str, Any], key: str) -> float:
    raw = _profile_value(raw_profile, key)
    if isinstance(raw, bool):
        raise SmokeFailure(f"baseline profile field '{key}' must be a float")
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw.strip())
        except ValueError as exc:
            raise SmokeFailure(f"baseline profile field '{key}' must be a float") from exc
    raise SmokeFailure(f"baseline profile field '{key}' must be a float")


def load_baseline_profile(path: Path, name: str) -> SmokeBaselineProfile:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SmokeFailure(f"unable to read baseline file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SmokeFailure(f"invalid baseline JSON: {path}") from exc

    if not isinstance(payload, dict):
        raise SmokeFailure(f"baseline file payload must be an object: {path}")
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict):
        raise SmokeFailure(f"baseline file is missing 'profiles': {path}")
    raw_profile = profiles.get(name)
    if not isinstance(raw_profile, dict):
        available = ", ".join(sorted(str(key) for key in profiles.keys()))
        raise SmokeFailure(
            f"baseline profile '{name}' not found in {path}. Available profiles: {available or '(none)'}"
        )

    dataset_dir_raw = _profile_value(raw_profile, "dataset_dir")
    if not isinstance(dataset_dir_raw, str) or not dataset_dir_raw.strip():
        raise SmokeFailure("baseline profile field 'dataset_dir' must be a non-empty string")
    write_mode_raw = _profile_value(raw_profile, "write_mode")
    if not isinstance(write_mode_raw, bool):
        raise SmokeFailure("baseline profile field 'write_mode' must be a boolean")
    gate_tier_raw = raw_profile.get("gate_tier", "custom")
    gate_tier = gate_tier_raw if isinstance(gate_tier_raw, str) and gate_tier_raw.strip() else "custom"
    expectations_raw = raw_profile.get("expectations")
    expectations = expectations_raw if isinstance(expectations_raw, str) and expectations_raw.strip() else None

    return SmokeBaselineProfile(
        name=name,
        gate_tier=gate_tier,
        dataset_dir=Path(dataset_dir_raw),
        total_images=_profile_int(raw_profile, "total_images"),
        total_folders=_profile_int(raw_profile, "total_folders"),
        image_width=_profile_int(raw_profile, "image_width"),
        image_height=_profile_int(raw_profile, "image_height"),
        jpeg_quality=_profile_int(raw_profile, "jpeg_quality"),
        first_grid_threshold_seconds=_profile_float(raw_profile, "first_grid_threshold_seconds"),
        first_grid_hotpath_threshold_ms=_profile_float(raw_profile, "first_grid_hotpath_threshold_ms"),
        first_thumbnail_threshold_ms=_profile_float(raw_profile, "first_thumbnail_threshold_ms"),
        interaction_seconds=_profile_float(raw_profile, "interaction_seconds"),
        max_frame_gap_ms=_profile_float(raw_profile, "max_frame_gap_ms"),
        write_mode=write_mode_raw,
        expectations=expectations,
    )


def resolve_args_with_baseline(args: argparse.Namespace) -> argparse.Namespace:
    baseline_profile = load_baseline_profile(args.baseline_file, args.baseline_profile)

    def choose(override: Any, baseline_value: Any) -> Any:
        return baseline_value if override is None else override

    args.dataset_dir = choose(args.dataset_dir, baseline_profile.dataset_dir)
    args.total_images = choose(args.total_images, baseline_profile.total_images)
    args.total_folders = choose(args.total_folders, baseline_profile.total_folders)
    args.image_width = choose(args.image_width, baseline_profile.image_width)
    args.image_height = choose(args.image_height, baseline_profile.image_height)
    args.jpeg_quality = choose(args.jpeg_quality, baseline_profile.jpeg_quality)
    args.first_grid_threshold_seconds = choose(
        args.first_grid_threshold_seconds, baseline_profile.first_grid_threshold_seconds
    )
    args.first_grid_hotpath_threshold_ms = choose(
        args.first_grid_hotpath_threshold_ms, baseline_profile.first_grid_hotpath_threshold_ms
    )
    args.first_thumbnail_threshold_ms = choose(
        args.first_thumbnail_threshold_ms, baseline_profile.first_thumbnail_threshold_ms
    )
    args.interaction_seconds = choose(args.interaction_seconds, baseline_profile.interaction_seconds)
    args.max_frame_gap_ms = choose(args.max_frame_gap_ms, baseline_profile.max_frame_gap_ms)
    args.baseline_gate_tier = baseline_profile.gate_tier
    args.baseline_expectations = baseline_profile.expectations
    args.write_mode = bool(args.write_mode or baseline_profile.write_mode)
    return args


def _build_jpeg_payload(width: int, height: int, quality: int) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), color=(44, 88, 132)).save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def _expected_fixture_tail_path(root: Path, total_images: int, total_folders: int) -> Path:
    images_per_folder = max(1, (total_images + total_folders - 1) // total_folders)
    last_index = total_images - 1
    folder_index = last_index // images_per_folder
    return root / f"folder_{folder_index:05d}" / f"image_{last_index:05d}.jpg"


def ensure_fixture(root: Path, spec: FixtureSpec, regenerate: bool) -> None:
    manifest_path = root / ".fixture_manifest.json"
    if regenerate and root.exists():
        print(f"[fixture] removing existing fixture: {root}")
        shutil.rmtree(root)

    if root.exists() and manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
        tail_path = _expected_fixture_tail_path(root, spec.total_images, spec.total_folders)
        if (
            manifest.get("version") == FIXTURE_VERSION
            and manifest.get("spec") == asdict(spec)
            and tail_path.exists()
        ):
            print(f"[fixture] reusing existing fixture: {root}")
            return

    root.mkdir(parents=True, exist_ok=True)
    payload = _build_jpeg_payload(spec.image_width, spec.image_height, spec.jpeg_quality)
    images_per_folder = max(1, (spec.total_images + spec.total_folders - 1) // spec.total_folders)

    print(
        "[fixture] generating dataset "
        f"({spec.total_images} images in {spec.total_folders} folders at {spec.image_width}x{spec.image_height})"
    )
    generated = 0
    for folder_index in range(spec.total_folders):
        folder_path = root / f"folder_{folder_index:05d}"
        folder_path.mkdir(parents=True, exist_ok=True)
        for local_index in range(images_per_folder):
            image_index = folder_index * images_per_folder + local_index
            if image_index >= spec.total_images:
                break
            (folder_path / f"image_{image_index:05d}.jpg").write_bytes(payload)
            generated += 1
        if (folder_index + 1) % 500 == 0 or folder_index == spec.total_folders - 1:
            print(f"[fixture] folders built: {folder_index + 1}/{spec.total_folders}")

    manifest = {"version": FIXTURE_VERSION, "spec": asdict(spec), "generated_at_unix": time.time()}
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[fixture] generated {generated} image files.")


def _coerce_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.strip()))
        except ValueError:
            return 0
    return 0


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return _coerce_int(value)


def normalize_scope_path(raw: str | None) -> str:
    if raw is None or raw.strip() == "":
        return "/"
    normalized = raw.strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    normalized = normalized.rstrip("/")
    return normalized or "/"


def scope_url(base_url: str, scope_path: str | None) -> str:
    normalized = normalize_scope_path(scope_path)
    if normalized == "/":
        return base_url
    return f"{base_url}#{quote(normalized, safe='/@._-')}"


def parse_toolbar_count_label(raw: str) -> tuple[int, int | None]:
    text = raw.strip()
    if not text.endswith(" items"):
        raise SmokeFailure(f"unexpected toolbar count label: {raw!r}")
    body = text[: -len(" items")]
    parts = [segment.strip() for segment in body.split("/", 1)]
    try:
        current = int(parts[0].replace(",", ""))
    except ValueError as exc:
        raise SmokeFailure(f"unexpected toolbar count label: {raw!r}") from exc
    if len(parts) == 1:
        return current, None
    try:
        total = int(parts[1].replace(",", ""))
    except ValueError as exc:
        raise SmokeFailure(f"unexpected toolbar count label: {raw!r}") from exc
    return current, total


def top_visible_grid_path(page: Any) -> str:
    value = page.evaluate(
        """() => {
          const cells = Array.from(document.querySelectorAll('[role="gridcell"][id^="cell-"]'))
            .map((el) => {
              const rect = el.getBoundingClientRect();
              const id = el.id || '';
              const encodedPath = id.startsWith('cell-') ? id.slice(5) : '';
              let path = '';
              try {
                path = encodedPath ? decodeURIComponent(encodedPath) : '';
              } catch {
                path = '';
              }
              return { path, top: rect.top, left: rect.left, bottom: rect.bottom };
            })
            .filter((entry) => entry.path && entry.bottom > 0 && entry.top < window.innerHeight);
          cells.sort((a, b) => (a.top - b.top) || (a.left - b.left));
          return cells.length ? cells[0].path : null;
        }"""
    )
    if not value or not isinstance(value, str):
        raise SmokeFailure("no visible gallery grid path found")
    return value


def wait_for_top_visible_grid_path_change(page: Any, previous_path: str, timeout_ms: float) -> str:
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    latest_path = previous_path
    while time.monotonic() < deadline:
        latest_path = top_visible_grid_path(page)
        if latest_path != previous_path:
            return latest_path
        page.wait_for_timeout(120)
    raise SmokeFailure(
        f"timed out waiting for top visible grid path to change from {previous_path!r}; last={latest_path!r}"
    )


def read_toolbar_counts(page: Any) -> tuple[int, int | None]:
    raw = page.locator(".toolbar-count").first.inner_text()
    return parse_toolbar_count_label(raw)


def resolve_metric_filter_max(page: Any, scope_path: str, metric_key: str) -> float:
    payload = page.evaluate(
        """async ({scopePath, metricKey}) => {
          const params = new URLSearchParams({ path: scopePath, recursive: '1' });
          const response = await fetch(`/folders?${params.toString()}`);
          const body = await response.json();
          if (!response.ok) {
            return { ok: false, status: response.status, detail: body?.detail ?? null };
          }
          const metricKeys = Array.isArray(body?.metricKeys) ? body.metricKeys : [];
          const values = Array.isArray(body?.items)
            ? body.items
                .map((item) => item?.metrics?.[metricKey])
                .filter((value) => Number.isFinite(value))
                .sort((a, b) => a - b)
            : [];
          return { ok: true, metricKeys, values };
        }""",
        {"scopePath": scope_path, "metricKey": metric_key},
    )
    if not isinstance(payload, dict) or not payload.get("ok"):
        raise SmokeFailure(
            f"failed to resolve metric probe data for {metric_key!r} at {scope_path!r}: {payload!r}"
        )
    metric_keys = payload.get("metricKeys")
    if not isinstance(metric_keys, list) or metric_key not in metric_keys:
        raise SmokeFailure(f"metric key {metric_key!r} missing from recursive payload metricKeys")
    values = payload.get("values")
    if not isinstance(values, list) or len(values) < 2:
        raise SmokeFailure(f"metric key {metric_key!r} did not produce enough values for filtering")
    first = float(values[0])
    last = float(values[-1])
    if first == last:
        raise SmokeFailure(f"metric key {metric_key!r} is constant across the scoped payload")
    quantile_index = min(len(values) - 1, max(0, int((len(values) - 1) * 0.35)))
    return float(values[quantile_index])


def assert_request_budget_compliance(hotpath_snapshot: dict[str, Any] | None) -> tuple[dict[str, int], dict[str, int]]:
    if not isinstance(hotpath_snapshot, dict):
        raise SmokeFailure("hotpath telemetry is unavailable; cannot validate request-budget compliance")
    request_budget = hotpath_snapshot.get("requestBudget")
    if not isinstance(request_budget, dict):
        raise SmokeFailure("request-budget telemetry is unavailable in window.__lensletBrowseHotpath")

    limits_raw = request_budget.get("limits")
    peaks_raw = request_budget.get("peakInflight")
    if not isinstance(limits_raw, dict) or not isinstance(peaks_raw, dict):
        raise SmokeFailure("request-budget telemetry payload is incomplete")

    limits: dict[str, int] = {}
    peaks: dict[str, int] = {}
    for endpoint in BROWSE_ENDPOINTS:
        limit = _coerce_int(limits_raw.get(endpoint))
        peak = _coerce_int(peaks_raw.get(endpoint))
        if limit <= 0:
            raise SmokeFailure(f"request-budget limit for '{endpoint}' is missing or invalid")
        if peak > limit:
            raise SmokeFailure(
                f"request-budget overflow for '{endpoint}': peak {peak} > limit {limit}"
            )
        limits[endpoint] = limit
        peaks[endpoint] = peak
    return limits, peaks


def assert_responsiveness_thresholds(
    *,
    first_grid_visible_seconds: float,
    first_grid_threshold_seconds: float,
    first_grid_hotpath_latency_ms: int | None,
    first_grid_hotpath_threshold_ms: float,
    max_frame_gap_ms: float,
    max_frame_gap_threshold_ms: float,
    first_thumbnail_latency_ms: int | None,
    first_thumbnail_threshold_ms: float,
) -> None:
    if first_grid_visible_seconds > first_grid_threshold_seconds:
        raise SmokeFailure(
            f"first grid cell visible in {first_grid_visible_seconds:.2f}s "
            f"(threshold {first_grid_threshold_seconds:.2f}s)"
        )
    if max_frame_gap_ms > max_frame_gap_threshold_ms:
        raise SmokeFailure(
            f"UI freeze threshold exceeded: max frame gap {max_frame_gap_ms:.1f}ms "
            f"(threshold {max_frame_gap_threshold_ms:.1f}ms)"
        )
    if first_grid_hotpath_latency_ms is None:
        raise SmokeFailure("first-grid telemetry is unavailable")
    if float(first_grid_hotpath_latency_ms) > first_grid_hotpath_threshold_ms:
        raise SmokeFailure(
            f"first grid telemetry latency exceeded threshold: {first_grid_hotpath_latency_ms}ms "
            f"(threshold {first_grid_hotpath_threshold_ms:.0f}ms)"
        )
    if first_thumbnail_latency_ms is None:
        raise SmokeFailure("first-thumbnail telemetry is unavailable")
    if float(first_thumbnail_latency_ms) > first_thumbnail_threshold_ms:
        raise SmokeFailure(
            f"first thumbnail latency exceeded threshold: {first_thumbnail_latency_ms}ms "
            f"(threshold {first_thumbnail_threshold_ms:.0f}ms)"
        )


def run_metric_controls_probe(
    page: Any,
    *,
    scope_path: str,
    metric_key: str,
    forbidden_metric_key: str | None,
    browser_timeout_ms: float,
) -> dict[str, Any]:
    sort_trigger = page.locator('button[aria-label="Sort and layout"]').first
    if sort_trigger.is_disabled():
        switch_button = page.get_by_role("button", name="Switch to Most recent").first
        if switch_button.count() == 0:
            raise SmokeFailure("sort controls are disabled and no switch-to-most-recent banner is available")
        switch_button.click()
        deadline = time.monotonic() + (browser_timeout_ms / 1000.0)
        while time.monotonic() < deadline:
            if not sort_trigger.is_disabled():
                break
            page.wait_for_timeout(120)
        if sort_trigger.is_disabled():
            raise SmokeFailure("sort controls stayed disabled after switching to most recent")
    sort_trigger.click()
    sort_menu = page.locator('[role="listbox"][aria-label="Sort and layout"]').first
    sort_menu.wait_for(state="visible")
    if forbidden_metric_key:
        forbidden_count = sort_menu.get_by_role("menuitem", name=forbidden_metric_key).count()
        if forbidden_count > 0:
            raise SmokeFailure(f"forbidden metric key {forbidden_metric_key!r} leaked into sort controls")
    metric_option = sort_menu.get_by_role("menuitem", name=metric_key).first
    metric_option.wait_for(state="visible")
    metric_option.click()
    page.wait_for_timeout(250)
    metric_sort_desc_top_path = top_visible_grid_path(page)

    page.get_by_role("button", name="Toggle sort direction").first.click()
    metric_sort_asc_top_path = wait_for_top_visible_grid_path_change(
        page,
        metric_sort_desc_top_path,
        timeout_ms=browser_timeout_ms,
    )

    page.get_by_role("button", name="Metrics and Filters").first.click()
    metric_select = page.locator(".app-left-panel select.ui-select").first
    metric_option_locator = metric_select.locator(f'option[value="{metric_key}"]')
    if metric_option_locator.count() == 0:
        raise SmokeFailure(f"metric key {metric_key!r} is missing from the metrics panel selector")
    if forbidden_metric_key:
        forbidden_option_count = metric_select.locator(f'option[value="{forbidden_metric_key}"]').count()
        if forbidden_option_count > 0:
            raise SmokeFailure(f"forbidden metric key {forbidden_metric_key!r} leaked into the metrics panel")
    metric_select.select_option(metric_key)

    metric_filter_count_before, _ = read_toolbar_counts(page)
    metric_filter_max = resolve_metric_filter_max(page, scope_path, metric_key)
    metric_card = page.locator(".app-left-panel .ui-card").filter(
        has=page.get_by_text("Population:")
    ).first
    metric_card.wait_for(state="visible")
    max_input = metric_card.locator('input[type="number"]').nth(1)
    max_input.fill(f"{metric_filter_max:.6g}")
    max_input.press("Enter")

    deadline = time.monotonic() + (browser_timeout_ms / 1000.0)
    metric_filter_count_after = metric_filter_count_before
    while time.monotonic() < deadline:
        metric_filter_count_after, _ = read_toolbar_counts(page)
        if metric_filter_count_after < metric_filter_count_before:
            break
        page.wait_for_timeout(120)
    if metric_filter_count_after >= metric_filter_count_before:
        raise SmokeFailure(
            "metric range filter did not narrow the visible result count: "
            f"before={metric_filter_count_before}, after={metric_filter_count_after}"
        )

    return {
        "metric_sort_desc_top_path": metric_sort_desc_top_path,
        "metric_sort_asc_top_path": metric_sort_asc_top_path,
        "metric_filter_count_before": metric_filter_count_before,
        "metric_filter_count_after": metric_filter_count_after,
        "metric_filter_max": metric_filter_max,
    }


def run_playwright_probe(
    base_url: str,
    browser_timeout_ms: float,
    first_grid_threshold_seconds: float,
    interaction_seconds: float,
    scope_path: str,
    metric_key: str | None,
    forbidden_metric_key: str | None,
) -> tuple[float, dict[str, float], dict[str, Any] | None, list[str], list[str], dict[str, Any] | None]:
    playwright_error, playwright_timeout_error, sync_playwright = import_playwright()
    page_errors: list[str] = []
    console_errors: list[str] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1680, "height": 980})
            page = context.new_page()
            page.set_default_timeout(browser_timeout_ms)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text)
                if msg.type == "error"
                else None,
            )

            start = time.monotonic()
            page.goto(scope_url(base_url, scope_path), wait_until="domcontentloaded")
            page.get_by_role("grid", name="Gallery").wait_for(state="visible")
            try:
                page.wait_for_selector(
                    '[role="gridcell"][id^="cell-"]',
                    state="visible",
                    timeout=max(1, int(first_grid_threshold_seconds * 1_000)),
                )
            except playwright_timeout_error as exc:
                elapsed = time.monotonic() - start
                raise SmokeFailure(
                    f"first grid cell did not become visible within {first_grid_threshold_seconds:.2f}s "
                    f"(elapsed={elapsed:.2f}s)"
                ) from exc
            first_grid_visible_seconds = time.monotonic() - start

            try:
                page.wait_for_function(
                    """() => {
                      const hotpath = window.__lensletBrowseHotpath;
                      if (!hotpath || !hotpath.requestBudget) return false;
                      return hotpath.firstGridItemLatencyMs !== null && hotpath.firstThumbnailLatencyMs !== null;
                    }""",
                    timeout=max(1, int(first_grid_threshold_seconds * 1_000)),
                )
            except playwright_timeout_error as exc:
                raise SmokeFailure(
                    "timed out waiting for hotpath request-budget, first-grid, and first-thumbnail telemetry"
                ) from exc

            probe_raw = page.evaluate(
                """async ({durationMs, scrollStepPx}) => {
                  const grid = document.querySelector('[role="grid"]');
                  if (!grid) {
                    return {
                      frames: 0,
                      maxGapMs: Number.POSITIVE_INFINITY,
                      avgGapMs: Number.POSITIVE_INFINITY,
                      hotpath: window.__lensletBrowseHotpath ?? null,
                    };
                  }

                  const findScrollContainer = (node) => {
                    let current = node;
                    while (current) {
                      if (current.scrollHeight > current.clientHeight + 4) {
                        return current;
                      }
                      current = current.parentElement;
                    }
                    return document.scrollingElement || document.documentElement;
                  };

                  const scroller = findScrollContainer(grid);
                  const start = performance.now();
                  let last = start;
                  let maxGapMs = 0;
                  let totalGapMs = 0;
                  let sampledFrames = 0;

                  return await new Promise((resolve) => {
                    const step = (now) => {
                      const gap = now - last;
                      if (sampledFrames > 0) {
                        maxGapMs = Math.max(maxGapMs, gap);
                        totalGapMs += gap;
                      }
                      sampledFrames += 1;
                      last = now;

                      if (typeof scroller.scrollTop === 'number') {
                        scroller.scrollTop += scrollStepPx;
                      } else {
                        window.scrollBy(0, scrollStepPx);
                      }

                      if (now - start < durationMs) {
                        requestAnimationFrame(step);
                        return;
                      }

                      const divisor = Math.max(1, sampledFrames - 1);
                      resolve({
                        frames: sampledFrames,
                        maxGapMs,
                        avgGapMs: totalGapMs / divisor,
                        hotpath: window.__lensletBrowseHotpath ?? null,
                      });
                    };
                    requestAnimationFrame(step);
                  });
                }""",
                {"durationMs": max(500, int(interaction_seconds * 1000)), "scrollStepPx": 280},
            )

            if not isinstance(probe_raw, dict):
                raise SmokeFailure("playwright probe returned invalid payload")

            probe_result: dict[str, float] = {
                "frames": float(_coerce_int(probe_raw.get("frames"))),
                "maxGapMs": float(probe_raw.get("maxGapMs", 0.0)),
                "avgGapMs": float(probe_raw.get("avgGapMs", 0.0)),
            }
            hotpath_snapshot = probe_raw.get("hotpath")
            if not isinstance(hotpath_snapshot, dict):
                hotpath_snapshot = None
            metric_probe = None
            if metric_key:
                metric_probe = run_metric_controls_probe(
                    page,
                    scope_path=normalize_scope_path(scope_path),
                    metric_key=metric_key,
                    forbidden_metric_key=forbidden_metric_key,
                    browser_timeout_ms=browser_timeout_ms,
                )

            context.close()
            browser.close()
    except playwright_error as exc:
        raise SmokeFailure(f"playwright probe failed: {exc}") from exc

    return first_grid_visible_seconds, probe_result, hotpath_snapshot, page_errors, console_errors, metric_probe


def main() -> int:
    try:
        args = parse_args()
    except SmokeFailure as exc:
        print(f"[smoke:error] {exc}")
        return 1

    scope_path = normalize_scope_path(args.scope_path)
    fixture_spec = FixtureSpec(
        total_images=args.total_images,
        total_folders=args.total_folders,
        image_width=args.image_width,
        image_height=args.image_height,
        jpeg_quality=args.jpeg_quality,
    )
    dataset_dir = args.dataset_dir.resolve()
    if args.source_path is None:
        if args.total_images <= 0:
            print("[smoke:error] --total-images must be > 0")
            return 1
        if args.total_folders <= 0:
            print("[smoke:error] --total-folders must be > 0")
            return 1
        if args.total_folders > args.total_images:
            print("[smoke:error] --total-folders cannot exceed --total-images for this fixture layout")
            return 1
        ensure_fixture(dataset_dir, fixture_spec, regenerate=args.regenerate_fixture)
        source_path = dataset_dir
    else:
        source_path = args.source_path.resolve()
        if not source_path.exists():
            print(f"[smoke:error] --source-path does not exist: {source_path}")
            return 1

    port = choose_port(args.host, args.port)
    base_url = f"http://{args.host}:{port}"
    extra_args: list[str] = []
    if not args.write_mode:
        extra_args.append("--no-write")
    print(
        f"[smoke] baseline={args.baseline_profile} tier={args.baseline_gate_tier} "
        f"write_mode={args.write_mode} source={source_path}"
    )
    if args.baseline_expectations:
        print(f"[smoke] baseline expectation: {args.baseline_expectations}")
    print(
        "[smoke] starting lenslet: "
        f"python -m lenslet.cli {source_path} --host {args.host} --port {port}"
        f"{' --no-write' if not args.write_mode else ''}"
    )
    process = launch_lenslet(
        source_path,
        host=args.host,
        port=port,
        extra_args=extra_args,
    )

    try:
        health_payload = wait_for_health(base_url, args.health_timeout_seconds, request_timeout=2.0)
        print(f"[smoke] /health reachable, indexing state={health_payload.get('indexing', {}).get('state')}")

        first_visible, probe_result, hotpath_snapshot, page_errors, console_errors, metric_probe = run_playwright_probe(
            base_url=base_url,
            browser_timeout_ms=args.browser_timeout_ms,
            first_grid_threshold_seconds=args.first_grid_threshold_seconds,
            interaction_seconds=args.interaction_seconds,
            scope_path=scope_path,
            metric_key=args.metric_key,
            forbidden_metric_key=args.forbid_metric_key,
        )
        request_budget_limits, request_budget_peaks = assert_request_budget_compliance(hotpath_snapshot)
        first_grid_hotpath_latency_ms = _coerce_optional_int(
            hotpath_snapshot.get("firstGridItemLatencyMs") if isinstance(hotpath_snapshot, dict) else None
        )
        first_thumbnail_latency_ms = _coerce_optional_int(
            hotpath_snapshot.get("firstThumbnailLatencyMs") if isinstance(hotpath_snapshot, dict) else None
        )
        assert_responsiveness_thresholds(
            first_grid_visible_seconds=first_visible,
            first_grid_threshold_seconds=args.first_grid_threshold_seconds,
            first_grid_hotpath_latency_ms=first_grid_hotpath_latency_ms,
            first_grid_hotpath_threshold_ms=args.first_grid_hotpath_threshold_ms,
            max_frame_gap_ms=float(probe_result["maxGapMs"]),
            max_frame_gap_threshold_ms=args.max_frame_gap_ms,
            first_thumbnail_latency_ms=first_thumbnail_latency_ms,
            first_thumbnail_threshold_ms=args.first_thumbnail_threshold_ms,
        )

        health_after = wait_for_health(base_url, timeout_seconds=10.0, request_timeout=2.0)
        indexing = health_after.get("indexing", {}) if isinstance(health_after, dict) else {}
        result = SmokeResult(
            baseline_file=str(args.baseline_file.resolve()),
            baseline_profile=args.baseline_profile,
            gate_tier=args.baseline_gate_tier,
            write_mode=bool(args.write_mode),
            dataset_dir=str(dataset_dir),
            source_path=str(source_path),
            total_images=args.total_images,
            total_folders=args.total_folders,
            first_grid_visible_seconds=first_visible,
            first_grid_threshold_seconds=args.first_grid_threshold_seconds,
            first_grid_hotpath_latency_ms=first_grid_hotpath_latency_ms,
            first_grid_hotpath_threshold_ms=args.first_grid_hotpath_threshold_ms,
            first_thumbnail_latency_ms=first_thumbnail_latency_ms,
            first_thumbnail_threshold_ms=args.first_thumbnail_threshold_ms,
            max_frame_gap_ms=float(probe_result["maxGapMs"]),
            max_frame_gap_threshold_ms=args.max_frame_gap_ms,
            average_frame_gap_ms=float(probe_result["avgGapMs"]),
            sampled_frames=int(probe_result["frames"]),
            request_budget_limits=request_budget_limits,
            request_budget_peak_inflight=request_budget_peaks,
            page_errors=len(page_errors),
            console_errors=len(console_errors),
            health_state=str(indexing.get("state", "unknown")),
            indexing_done=indexing.get("done"),
            indexing_total=indexing.get("total"),
            scope_path=scope_path if scope_path != "/" else None,
            metric_key=args.metric_key,
            forbidden_metric_key=args.forbid_metric_key,
            metric_sort_desc_top_path=(
                str(metric_probe.get("metric_sort_desc_top_path")) if isinstance(metric_probe, dict) else None
            ),
            metric_sort_asc_top_path=(
                str(metric_probe.get("metric_sort_asc_top_path")) if isinstance(metric_probe, dict) else None
            ),
            metric_filter_count_before=(
                _coerce_optional_int(metric_probe.get("metric_filter_count_before"))
                if isinstance(metric_probe, dict)
                else None
            ),
            metric_filter_count_after=(
                _coerce_optional_int(metric_probe.get("metric_filter_count_after"))
                if isinstance(metric_probe, dict)
                else None
            ),
            metric_filter_max=(
                float(metric_probe.get("metric_filter_max"))
                if isinstance(metric_probe, dict) and metric_probe.get("metric_filter_max") is not None
                else None
            ),
        )

        print(
            "[smoke] pass: first-grid="
            f"{result.first_grid_visible_seconds:.2f}s (hotpath={result.first_grid_hotpath_latency_ms}ms), "
            f"first-thumb={result.first_thumbnail_latency_ms}ms, "
            f"max-frame-gap={result.max_frame_gap_ms:.1f}ms, peaks={result.request_budget_peak_inflight}, "
            f"frames={result.sampled_frames}"
        )
        if result.metric_key:
            print(
                "[smoke] metric-flow: "
                f"key={result.metric_key} desc-top={result.metric_sort_desc_top_path} "
                f"asc-top={result.metric_sort_asc_top_path} "
                f"count={result.metric_filter_count_before}->{result.metric_filter_count_after} "
                f"max={result.metric_filter_max}"
            )
        if page_errors:
            print("[smoke:warn] page errors observed:")
            for message in page_errors:
                print(f"  - {message}")
        if console_errors:
            print("[smoke:warn] console errors observed:")
            for message in console_errors:
                print(f"  - {message}")

        if args.output_json is not None:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
            print(f"[smoke] wrote summary: {args.output_json}")
        return 0
    except SmokeFailure as exc:
        print(f"[smoke:error] {exc}")
        return 1
    finally:
        stop_process(process)


if __name__ == "__main__":
    raise SystemExit(main())
