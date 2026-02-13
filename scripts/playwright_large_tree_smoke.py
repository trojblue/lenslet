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
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from PIL import Image

FIXTURE_VERSION = 1
BROWSE_ENDPOINTS = ("folders", "thumb", "file")


class SmokeFailure(RuntimeError):
    """Raised when smoke assertions fail."""


@dataclass(frozen=True)
class FixtureSpec:
    total_images: int
    total_folders: int
    image_width: int
    image_height: int
    jpeg_quality: int


@dataclass(frozen=True)
class SmokeResult:
    dataset_dir: str
    total_images: int
    total_folders: int
    first_grid_visible_seconds: float
    first_grid_threshold_seconds: float
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a large-tree Playwright browse smoke test.")
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=Path("data/fixtures/large_tree_40k"),
        help="Dataset fixture directory (default: data/fixtures/large_tree_40k).",
    )
    parser.add_argument("--total-images", type=int, default=40_000, help="Total fixture images.")
    parser.add_argument("--total-folders", type=int, default=10_000, help="Total fixture folders.")
    parser.add_argument("--image-width", type=int, default=100, help="Fixture image width.")
    parser.add_argument("--image-height", type=int, default=200, help="Fixture image height.")
    parser.add_argument("--jpeg-quality", type=int, default=70, help="Fixture JPEG quality.")
    parser.add_argument(
        "--regenerate-fixture",
        action="store_true",
        help="Delete and rebuild fixture directory before running smoke checks.",
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
        default=5.0,
        help="Fail if first visible grid cell takes longer than this threshold.",
    )
    parser.add_argument(
        "--first-thumbnail-threshold-ms",
        type=float,
        default=5_000.0,
        help="Fail if first thumbnail telemetry exceeds this threshold.",
    )
    parser.add_argument(
        "--interaction-seconds",
        type=float,
        default=5.0,
        help="Duration to run scroll responsiveness probe.",
    )
    parser.add_argument(
        "--max-frame-gap-ms",
        type=float,
        default=700.0,
        help="Fail if UI frame gap exceeds this threshold during scroll probe.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to write machine-readable smoke summary JSON.",
    )
    return parser.parse_args()


def choose_port(host: str, preferred: int) -> int:
    if _port_available(host, preferred):
        return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


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


def wait_for_health(base_url: str, timeout_seconds: float) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{base_url}/health", timeout=2.0) as response:
                if response.status != 200:
                    raise SmokeFailure(f"unexpected /health status: {response.status}")
                payload = json.load(response)
                if not isinstance(payload, dict):
                    raise SmokeFailure("unexpected /health payload")
                return payload
        except URLError as exc:
            last_error = exc
        time.sleep(0.2)
    raise SmokeFailure(f"/health unavailable after {timeout_seconds:.1f}s: {last_error!r}")


def _import_playwright() -> tuple[type[BaseException], type[BaseException], Callable[[], Any]]:
    try:
        from playwright.sync_api import Error as playwright_error
        from playwright.sync_api import TimeoutError as playwright_timeout_error
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - runtime dependency guard
        raise SmokeFailure(
            "playwright is required: pip install -e '.[dev]' && python -m playwright install chromium"
        ) from exc
    return playwright_error, playwright_timeout_error, sync_playwright


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
    coerced = _coerce_int(value)
    return coerced


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
    if first_thumbnail_latency_ms is None:
        raise SmokeFailure("first-thumbnail telemetry is unavailable")
    if float(first_thumbnail_latency_ms) > first_thumbnail_threshold_ms:
        raise SmokeFailure(
            f"first thumbnail latency exceeded threshold: {first_thumbnail_latency_ms}ms "
            f"(threshold {first_thumbnail_threshold_ms:.0f}ms)"
        )


def run_playwright_probe(
    base_url: str,
    browser_timeout_ms: float,
    first_grid_threshold_seconds: float,
    interaction_seconds: float,
) -> tuple[float, dict[str, float], dict[str, Any] | None, list[str], list[str]]:
    playwright_error, playwright_timeout_error, sync_playwright = _import_playwright()
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
            page.goto(base_url, wait_until="domcontentloaded")
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
                      return hotpath.firstThumbnailLatencyMs !== null;
                    }""",
                    timeout=max(1, int(first_grid_threshold_seconds * 1_000)),
                )
            except playwright_timeout_error as exc:
                raise SmokeFailure(
                    "timed out waiting for hotpath request-budget and first-thumbnail telemetry"
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

            context.close()
            browser.close()
    except playwright_error as exc:
        raise SmokeFailure(f"playwright probe failed: {exc}") from exc

    return first_grid_visible_seconds, probe_result, hotpath_snapshot, page_errors, console_errors


def main() -> int:
    args = parse_args()
    if args.total_images <= 0:
        print("[smoke:error] --total-images must be > 0")
        return 1
    if args.total_folders <= 0:
        print("[smoke:error] --total-folders must be > 0")
        return 1
    if args.total_folders > args.total_images:
        print("[smoke:error] --total-folders cannot exceed --total-images for this fixture layout")
        return 1

    fixture_spec = FixtureSpec(
        total_images=args.total_images,
        total_folders=args.total_folders,
        image_width=args.image_width,
        image_height=args.image_height,
        jpeg_quality=args.jpeg_quality,
    )
    dataset_dir = args.dataset_dir.resolve()
    ensure_fixture(dataset_dir, fixture_spec, regenerate=args.regenerate_fixture)

    port = choose_port(args.host, args.port)
    base_url = f"http://{args.host}:{port}"
    command = [
        sys.executable,
        "-m",
        "lenslet.cli",
        str(dataset_dir),
        "--host",
        args.host,
        "--port",
        str(port),
        "--no-write",
    ]
    print(f"[smoke] starting lenslet: {' '.join(command)}")
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        health_payload = wait_for_health(base_url, args.health_timeout_seconds)
        print(f"[smoke] /health reachable, indexing state={health_payload.get('indexing', {}).get('state')}")

        first_visible, probe_result, hotpath_snapshot, page_errors, console_errors = run_playwright_probe(
            base_url=base_url,
            browser_timeout_ms=args.browser_timeout_ms,
            first_grid_threshold_seconds=args.first_grid_threshold_seconds,
            interaction_seconds=args.interaction_seconds,
        )
        request_budget_limits, request_budget_peaks = assert_request_budget_compliance(hotpath_snapshot)
        first_thumbnail_latency_ms = _coerce_optional_int(
            hotpath_snapshot.get("firstThumbnailLatencyMs") if isinstance(hotpath_snapshot, dict) else None
        )
        assert_responsiveness_thresholds(
            first_grid_visible_seconds=first_visible,
            first_grid_threshold_seconds=args.first_grid_threshold_seconds,
            max_frame_gap_ms=float(probe_result["maxGapMs"]),
            max_frame_gap_threshold_ms=args.max_frame_gap_ms,
            first_thumbnail_latency_ms=first_thumbnail_latency_ms,
            first_thumbnail_threshold_ms=args.first_thumbnail_threshold_ms,
        )

        health_after = wait_for_health(base_url, timeout_seconds=10.0)
        indexing = health_after.get("indexing", {}) if isinstance(health_after, dict) else {}
        result = SmokeResult(
            dataset_dir=str(dataset_dir),
            total_images=args.total_images,
            total_folders=args.total_folders,
            first_grid_visible_seconds=first_visible,
            first_grid_threshold_seconds=args.first_grid_threshold_seconds,
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
        )

        print(
            "[smoke] pass: first-grid="
            f"{result.first_grid_visible_seconds:.2f}s, first-thumb={result.first_thumbnail_latency_ms}ms, "
            f"max-frame-gap={result.max_frame_gap_ms:.1f}ms, peaks={result.request_budget_peak_inflight}, "
            f"frames={result.sampled_frames}"
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
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
