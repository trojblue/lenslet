#!/usr/bin/env python3
"""Incremental browser evidence for the overall cleanup plan.

The script intentionally starts with the Sprint 1 comparison-export path and a
small layout snapshot. Later cleanup sprints should extend this file with their
new browser-facing assertions instead of creating parallel one-off harnesses.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from smoke_harness import choose_port, import_playwright, stop_process, wait_for_health


class OverallCleanupBrowserFailure(RuntimeError):
    """Raised when the browser cleanup evidence path fails."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Lenslet overall-cleanup browser evidence.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7070)
    parser.add_argument("--dataset-dir", type=Path, default=None)
    parser.add_argument("--keep-dataset", action="store_true")
    parser.add_argument("--server-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--browser-timeout-ms", type=float, default=30_000)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("/tmp/lenslet-overall-cleanup-browser.json"),
        help="Path for machine-readable cleanup evidence.",
    )
    parser.add_argument(
        "--screenshot-dir",
        type=Path,
        default=Path("/tmp/lenslet-overall-cleanup-browser-screenshots"),
        help="Directory for screenshots captured on scenario failure.",
    )
    return parser.parse_args()


def build_fixture_dataset(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    colors = (
        (215, 80, 75),
        (74, 150, 92),
        (64, 112, 202),
        (222, 171, 66),
        (126, 91, 180),
        (42, 164, 176),
        (202, 96, 148),
        (86, 86, 96),
    )
    sizes = (
        (96, 64),
        (80, 64),
        (72, 96),
        (112, 70),
        (90, 90),
        (120, 72),
        (84, 108),
        (100, 76),
    )
    for idx, (color, size) in enumerate(zip(colors, sizes)):
        path = root / f"cleanup_fixture_{idx:02d}.png"
        path.write_bytes(_png_payload(size=size, color=color))


def _png_payload(*, size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="PNG")
    return buffer.getvalue()


def visible_grid_cell_ids(page: Any) -> list[str]:
    raw = page.evaluate(
        """() => {
          const cells = Array.from(document.querySelectorAll('[role="gridcell"][id^="cell-"]'))
            .map((el) => {
              const rect = el.getBoundingClientRect()
              return {
                id: el.id,
                top: rect.top,
                left: rect.left,
                bottom: rect.bottom,
                right: rect.right,
              }
            })
            .filter((entry) => (
              entry.id &&
              entry.bottom > 0 &&
              entry.right > 0 &&
              entry.top < window.innerHeight &&
              entry.left < window.innerWidth
            ))
          cells.sort((a, b) => (a.top - b.top) || (a.left - b.left))
          return cells.map((entry) => entry.id)
        }""",
    )
    if not isinstance(raw, list):
        raise OverallCleanupBrowserFailure("Failed to evaluate visible grid cells.")
    return [cell_id for cell_id in raw if isinstance(cell_id, str) and cell_id.startswith("cell-")]


def wait_for_visible_grid_cell_ids(page: Any, minimum_count: int, timeout_ms: float) -> list[str]:
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    latest_ids: list[str] = []
    while time.monotonic() < deadline:
        latest_ids = visible_grid_cell_ids(page)
        if len(latest_ids) >= minimum_count:
            return latest_ids
        page.wait_for_timeout(120)
    raise OverallCleanupBrowserFailure(
        f"Expected at least {minimum_count} visible grid cells; last visible ids={latest_ids!r}."
    )


def set_right_panel_open(page: Any, open_state: bool, timeout_ms: float) -> None:
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        is_open = page.locator(".app-right-panel").count() > 0
        if is_open == open_state:
            return
        toggle_button = page.locator("button[aria-label='Toggle right panel']").first
        if toggle_button.count() == 0:
            page.wait_for_timeout(120)
            continue
        toggle_button.click()
        page.wait_for_timeout(180)
    raise OverallCleanupBrowserFailure(
        f"Timed out setting right panel open state to {open_state}; "
        f"current panel count={page.locator('.app-right-panel').count()}."
    )


def select_two_visible_images(page: Any, timeout_ms: float) -> list[str]:
    cell_ids = wait_for_visible_grid_cell_ids(page, minimum_count=2, timeout_ms=timeout_ms)
    first_cell_id = cell_ids[0]
    second_cell_id = next((cell_id for cell_id in cell_ids if cell_id != first_cell_id), None)
    if second_cell_id is None:
        raise OverallCleanupBrowserFailure(f"No distinct second grid cell in {cell_ids!r}.")

    page.locator(f"[id='{first_cell_id}']").first.click()
    page.locator(f"[id='{second_cell_id}']").first.click(modifiers=["Control"])
    page.get_by_text("2 files").first.wait_for(state="visible")
    return [first_cell_id, second_cell_id]


def collect_layout_evidence(page: Any, name: str) -> dict[str, Any]:
    return page.evaluate(
        """(name) => {
          const rectPayload = (rect) => rect ? ({
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
            left: rect.left,
            right: rect.right,
            top: rect.top,
            bottom: rect.bottom,
          }) : null
          const rectFor = (selector) => {
            const el = document.querySelector(selector)
            return el ? rectPayload(el.getBoundingClientRect()) : null
          }
          const visibleCells = Array.from(document.querySelectorAll('[role="gridcell"][id^="cell-"]'))
            .map((el) => {
              const rect = el.getBoundingClientRect()
              return { id: el.id, rect: rectPayload(rect) }
            })
            .filter((entry) => (
              entry.rect &&
              entry.rect.bottom > 0 &&
              entry.rect.right > 0 &&
              entry.rect.top < window.innerHeight &&
              entry.rect.left < window.innerWidth
            ))
            .slice(0, 8)
          const visualViewport = window.visualViewport ? {
            width: window.visualViewport.width,
            height: window.visualViewport.height,
            offsetLeft: window.visualViewport.offsetLeft,
            offsetTop: window.visualViewport.offsetTop,
            scale: window.visualViewport.scale,
          } : null
          return {
            name,
            viewport: {
              innerWidth: window.innerWidth,
              innerHeight: window.innerHeight,
              devicePixelRatio: window.devicePixelRatio,
              visualViewport,
            },
            grid: rectFor('[role="grid"][aria-label="Gallery"]'),
            rightPanel: rectFor('.app-right-panel'),
            compareDialog: rectFor('[role="dialog"][aria-label="Compare images"]'),
            selectedCellCount: document.querySelectorAll('[role="gridcell"][aria-selected="true"]').length,
            visibleCells,
            exportButtonCount: Array.from(document.querySelectorAll('button'))
              .filter((button) => (button.textContent || '').includes('Export comparison')).length,
          }
        }""",
        name,
    )


def open_compare_dialog(page: Any, timeout_ms: float) -> dict[str, Any]:
    side_by_side = page.get_by_role("button", name="Side by side view").first
    if side_by_side.is_disabled():
        raise OverallCleanupBrowserFailure("Side by side action is disabled for two selected images.")
    side_by_side.click()
    dialog = page.get_by_role("dialog", name="Compare images")
    dialog.wait_for(state="visible", timeout=timeout_ms)
    evidence = collect_layout_evidence(page, "compare-dialog-open")
    dialog.get_by_role("button", name="Close").click()
    dialog.wait_for(state="hidden", timeout=timeout_ms)
    return evidence


def trigger_comparison_export(page: Any) -> dict[str, Any]:
    export_entries = page.get_by_role("button", name="Export comparison")
    enabled_export_idx: int | None = None
    for idx in range(export_entries.count()):
        if export_entries.nth(idx).is_enabled():
            enabled_export_idx = idx
            break
    if enabled_export_idx is None:
        raise OverallCleanupBrowserFailure("No enabled Export comparison button found.")

    button = export_entries.nth(enabled_export_idx)
    button.scroll_into_view_if_needed()
    with page.expect_response(
        lambda response: response.request.method == "POST" and response.url.endswith("/export-comparison")
    ) as export_response_info, page.expect_download() as export_download_info:
        button.click()

    response = export_response_info.value
    download = export_download_info.value
    body = response.body()
    if response.status != 200:
        raise OverallCleanupBrowserFailure(
            f"Comparison export returned status {response.status}: {body[:200]!r}."
        )
    content_type = response.headers.get("content-type", "")
    if not content_type.startswith("image/png"):
        raise OverallCleanupBrowserFailure(f"Unexpected comparison export content type: {content_type!r}.")
    content_length_header = response.headers.get("content-length")
    declared_length = int(content_length_header) if content_length_header and content_length_header.isdigit() else None
    if declared_length is not None and declared_length <= 0:
        raise OverallCleanupBrowserFailure("Comparison export returned an empty content-length header.")
    download_path = download.path()
    if download_path is None:
        raise OverallCleanupBrowserFailure("Comparison export did not produce an inspectable browser download.")
    downloaded = Path(download_path).read_bytes()
    if not downloaded:
        raise OverallCleanupBrowserFailure("Comparison export produced an empty browser download.")
    with Image.open(BytesIO(downloaded)) as exported:
        exported.load()
        if exported.format != "PNG":
            raise OverallCleanupBrowserFailure(f"Downloaded export is not a PNG: {exported.format!r}.")
        export_width, export_height = exported.size
    if export_width <= 0 or export_height <= 0:
        raise OverallCleanupBrowserFailure(f"Downloaded export has invalid dimensions: {export_width}x{export_height}.")
    return {
        "status": response.status,
        "content_type": content_type,
        "content_disposition": response.headers.get("content-disposition", ""),
        "suggested_filename": download.suggested_filename,
        "content_length": declared_length if declared_length is not None else len(downloaded),
        "observed_body_length": len(body),
        "downloaded_content_length": len(downloaded),
        "downloaded_png_width": export_width,
        "downloaded_png_height": export_height,
    }


def run_browser_checks(base_url: str, timeout_ms: float, screenshot_dir: Path) -> dict[str, Any]:
    playwright_import = import_playwright()
    sync_playwright = playwright_import[2]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 920})
        page = context.new_page()
        page.set_default_timeout(timeout_ms)
        try:
            page.goto(base_url, wait_until="domcontentloaded")
            page.get_by_role("grid", name="Gallery").wait_for(state="visible")
            before_selection = collect_layout_evidence(page, "browse-ready")
            selected_cell_ids = select_two_visible_images(page, timeout_ms)
            set_right_panel_open(page, open_state=True, timeout_ms=10_000)
            after_selection = collect_layout_evidence(page, "two-selected")
            compare_dialog = open_compare_dialog(page, timeout_ms)
            export_result = trigger_comparison_export(page)
            after_export = collect_layout_evidence(page, "export-complete")
            return {
                "selected_cell_ids": selected_cell_ids,
                "layout": [before_selection, after_selection, compare_dialog, after_export],
                "comparison_export": export_result,
            }
        except Exception as exc:
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            screenshot_path = screenshot_dir / "overall_cleanup_failure.png"
            try:
                page.screenshot(path=str(screenshot_path), full_page=True)
            except Exception:
                screenshot_path = Path("")
            suffix = f" Screenshot: {screenshot_path}" if str(screenshot_path) else ""
            raise OverallCleanupBrowserFailure(f"{exc}{suffix}") from exc
        finally:
            context.close()
            browser.close()


def server_command(dataset_dir: Path, host: str, port: int) -> list[str]:
    return [
        sys.executable,
        "-m",
        "lenslet.cli",
        str(dataset_dir),
        "--host",
        host,
        "--port",
        str(port),
        "--verbose",
        "--no-skip-indexing",
    ]


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    cleanup_dir = False
    if args.dataset_dir is not None:
        dataset_dir = args.dataset_dir.resolve()
        if not dataset_dir.exists():
            raise SystemExit(f"Dataset directory does not exist: {dataset_dir}")
    else:
        dataset_dir = Path(tempfile.mkdtemp(prefix="lenslet-overall-cleanup-")).resolve()
        cleanup_dir = not args.keep_dataset
        build_fixture_dataset(dataset_dir)

    port = choose_port(args.host, args.port)
    base_url = f"http://{args.host}:{port}"
    log_file = tempfile.NamedTemporaryFile(
        prefix="lenslet-overall-cleanup-server-",
        suffix=".log",
        delete=False,
    )
    log_path = Path(log_file.name)
    log_file.close()

    command = server_command(dataset_dir, args.host, port)
    server_log = log_path.open("w", encoding="utf-8")
    try:
        server_proc = subprocess.Popen(
            command,
            cwd=str(Path(__file__).resolve().parents[1]),
            stdout=server_log,
            stderr=subprocess.STDOUT,
            text=True,
        )
    finally:
        server_log.close()

    summary: dict[str, Any]
    try:
        initial_health = wait_for_health(base_url, args.server_timeout_seconds)
        if server_proc.poll() is not None:
            raise OverallCleanupBrowserFailure(
                f"Lenslet exited unexpectedly with code {server_proc.returncode}."
            )
        checks = run_browser_checks(base_url, args.browser_timeout_ms, args.screenshot_dir)
        final_health = wait_for_health(base_url, args.server_timeout_seconds)
        summary = {
            "base_url": base_url,
            "dataset_dir": str(dataset_dir),
            "server_log": str(log_path),
            "initial_health": initial_health,
            "final_health": final_health,
            "checks": checks,
            "status": "passed",
        }
        print(json.dumps(summary, indent=2))
        write_summary(args.output_json, summary)
        return 0
    except Exception as exc:
        tail = ""
        try:
            tail = "\n".join(log_path.read_text(encoding="utf-8").splitlines()[-40:])
        except Exception:
            tail = "<unavailable>"
        summary = {
            "base_url": base_url,
            "dataset_dir": str(dataset_dir),
            "server_log": str(log_path),
            "error": str(exc),
            "server_log_tail": tail,
            "status": "failed",
        }
        write_summary(args.output_json, summary)
        print(f"[overall-cleanup-browser] FAILED: {exc}", file=sys.stderr)
        print(f"[overall-cleanup-browser] Server log tail ({log_path}):\n{tail}", file=sys.stderr)
        return 1
    finally:
        stop_process(server_proc)
        if cleanup_dir:
            shutil.rmtree(dataset_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
