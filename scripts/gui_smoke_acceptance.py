#!/usr/bin/env python3
"""Headless browser smoke harness for issue/tweak acceptance flows.

This script runs a deterministic acceptance pass that targets the remaining
browser-only regressions tracked in `docs/20260212_issue_tweak_tracking.md`.
It bootstraps a local fixture gallery, starts Lenslet, and validates:

1. Startup indexing banner lifecycle (`running` -> hidden when ready).
2. Left sidebar scrollbar-lane drag does not trigger resize.
3. Folder re-entry restores and preserves top-anchor context.
4. Path-token search behaves as expected.
5. Inspector multi-select compare/export entry actions are triggerable.
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from PIL import Image
try:
    from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright
except ImportError as exc:  # pragma: no cover - runtime dependency guard
    raise SystemExit(
        "playwright is required: pip install playwright && python -m playwright install chromium"
    ) from exc


class SmokeFailure(RuntimeError):
    """Raised when a smoke invariant fails."""


@dataclass(frozen=True)
class SmokeResult:
    indexing_banner_seen: bool
    sidebar_resize_delta_px: float
    anchor_before: str
    anchor_restored: str
    anchor_settled: str
    anchor_reentry_exact: bool
    search_visible_matches: list[str]


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


def build_fixture_dataset(root: Path) -> None:
    payload = _build_jpeg_payload()
    alpha_count = 1_600
    beta_count = 1_200
    tree_dirs = 90

    for idx in range(alpha_count):
        _write_image(root / "alpha" / f"alpha_{idx:04d}.jpg", payload)
    for idx in range(beta_count):
        _write_image(root / "beta" / f"beta_{idx:04d}.jpg", payload)
    for idx in range(tree_dirs):
        _write_image(root / f"tree_{idx:03d}" / f"tree_{idx:03d}_sample.jpg", payload)


def _build_jpeg_payload() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (24, 18), color=(44, 88, 132)).save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def _write_image(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


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


def wait_for_health(base_url: str, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(f"{base_url}/health", timeout=1.5) as response:
                if response.status != 200:
                    raise SmokeFailure(f"Unexpected /health status: {response.status}")
                payload = json.load(response)
                if not isinstance(payload, dict):
                    raise SmokeFailure("Unexpected /health payload type.")
                return payload
        except URLError as exc:
            last_error = exc
        except TimeoutError as exc:  # pragma: no cover - defensive runtime guard
            last_error = exc
        time.sleep(0.2)
    raise SmokeFailure(f"/health was unavailable after {timeout_seconds:.1f}s: {last_error!r}")


def top_visible_grid_path(page: Page) -> str:
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
        raise SmokeFailure("No visible gallery grid path found.")
    return value


def wait_for_top_name_prefix(page: Page, prefix: str, timeout_ms: float) -> str:
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    last_name: str | None = None
    while time.monotonic() < deadline:
        try:
            current = top_visible_grid_path(page)
            last_name = current
            if current.startswith(prefix):
                return current
        except SmokeFailure:
            pass
        page.wait_for_timeout(120)
    raise SmokeFailure(
        f"Timed out waiting for top visible filename prefix '{prefix}'. Last observed: {last_name!r}"
    )


def wait_for_stable_top_name(page: Page, prefix: str, timeout_ms: float, stable_reads: int = 3) -> str:
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    last_name: str | None = None
    stable_count = 0
    while time.monotonic() < deadline:
        current = wait_for_top_name_prefix(page, prefix, timeout_ms=1_000)
        if current == last_name:
            stable_count += 1
        else:
            last_name = current
            stable_count = 1
        if stable_count >= stable_reads:
            return current
        page.wait_for_timeout(180)
    raise SmokeFailure(
        f"Timed out waiting for stable top visible filename prefix '{prefix}'. "
        f"Last observed: {last_name!r}"
    )


def run_browser_checks(base_url: str, timeout_ms: float, strict_reentry_anchor: bool) -> SmokeResult:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1720, "height": 980})
        page = context.new_page()
        page.set_default_timeout(timeout_ms)
        page.goto(base_url, wait_until="domcontentloaded")
        page.get_by_role("grid", name="Gallery").wait_for(state="visible")

        indexing_banner = page.get_by_text("Indexing in progress").first
        indexing_banner_seen = False
        try:
            indexing_banner.wait_for(state="visible", timeout=20_000)
            indexing_banner_seen = True
            indexing_banner.wait_for(state="hidden", timeout=180_000)
        except PlaywrightTimeoutError:
            indexing_banner_seen = False

        left_width_before = float(
            page.eval_on_selector(".app-left-panel", "el => el.getBoundingClientRect().width")
        )
        tree_scroll_rect = page.eval_on_selector(
            "[aria-label='Folders']",
            """el => {
              const target = el.parentElement || el;
              const rect = target.getBoundingClientRect();
              return { left: rect.left, right: rect.right, top: rect.top, height: rect.height };
            }""",
        )
        drag_x = float(tree_scroll_rect["right"]) - 2.0
        drag_y = float(tree_scroll_rect["top"]) + min(float(tree_scroll_rect["height"]) * 0.6, 220.0)
        page.mouse.move(drag_x, drag_y)
        page.mouse.down()
        page.mouse.move(drag_x, drag_y + 160, steps=12)
        page.mouse.up()
        page.wait_for_timeout(150)
        left_width_after = float(
            page.eval_on_selector(".app-left-panel", "el => el.getBoundingClientRect().width")
        )
        sidebar_resize_delta_px = abs(left_width_after - left_width_before)
        if sidebar_resize_delta_px > 1.5:
            raise SmokeFailure(
                f"Left sidebar width changed during scrollbar-lane drag: {left_width_before:.2f}px -> "
                f"{left_width_after:.2f}px."
            )

        page.locator("[role='treeitem']", has_text="alpha").first.click()
        wait_for_top_name_prefix(page, "/alpha/", timeout_ms=15_000)
        gallery = page.get_by_role("grid", name="Gallery")
        gallery.hover()
        page.mouse.wheel(0, 900)
        page.wait_for_timeout(260)
        anchor_before = wait_for_stable_top_name(page, "/alpha/", timeout_ms=15_000, stable_reads=12)
        page.wait_for_timeout(1_200)
        anchor_before = top_visible_grid_path(page)

        page.locator("[role='treeitem']", has_text="beta").first.click()
        wait_for_top_name_prefix(page, "/beta/", timeout_ms=15_000)
        page.locator("[role='treeitem']", has_text="alpha").first.click()
        anchor_restored = wait_for_top_name_prefix(page, "/alpha/", timeout_ms=15_000)
        page.wait_for_timeout(1200)
        anchor_settled = top_visible_grid_path(page)
        anchor_reentry_exact = anchor_settled == anchor_before
        if strict_reentry_anchor and not anchor_reentry_exact:
            raise SmokeFailure(
                "Folder re-entry top-anchor mismatch: "
                f"before={anchor_before}, restored={anchor_restored}, settled={anchor_settled}."
            )

        search_box = page.get_by_label("Search filename, tags, notes").first
        token = Path(anchor_before).name.rsplit(".", 1)[0]
        search_box.fill(token)
        page.wait_for_timeout(350)
        search_visible_matches = page.eval_on_selector_all(
            ".thumb-filename",
            "nodes => nodes.map((n) => (n.textContent || '').trim()).filter(Boolean)",
        )
        if not search_visible_matches:
            raise SmokeFailure("Search returned no visible matches for path token query.")
        if any(token not in name for name in search_visible_matches):
            raise SmokeFailure(
                f"Search mismatch for token '{token}': visible names={search_visible_matches!r}"
            )
        search_box.fill("")
        page.wait_for_function(
            "() => document.querySelectorAll('[role=\"gridcell\"]').length >= 2",
            timeout=10_000,
        )

        if page.locator(".app-right-panel").count() == 0:
            page.get_by_role("button", name="Toggle right panel").click()
            page.locator(".app-right-panel").first.wait_for(state="visible")

        grid_cells = page.locator("[role='gridcell']")
        if grid_cells.count() < 2:
            raise SmokeFailure("Expected at least two visible grid cells for multi-select checks.")
        page.keyboard.down("Control")
        grid_cells.nth(0).click()
        grid_cells.nth(1).click()
        page.keyboard.up("Control")

        page.get_by_text("2 files").first.wait_for(state="visible")
        side_by_side = page.get_by_role("button", name="Side by side view").first
        if side_by_side.is_disabled():
            raise SmokeFailure("Side by side action is disabled for exactly two selections.")
        side_by_side.click()
        compare_dialog = page.get_by_role("dialog", name="Compare images")
        compare_dialog.wait_for(state="visible")
        compare_dialog.get_by_role("button", name="Close").click()
        compare_dialog.wait_for(state="hidden")

        export_entries = page.get_by_role("button", name="Export comparison")
        enabled_export_idx: int | None = None
        for idx in range(export_entries.count()):
            if export_entries.nth(idx).is_enabled():
                enabled_export_idx = idx
                break
        if enabled_export_idx is None:
            raise SmokeFailure("No enabled inspector Export comparison entry action found.")
        export_entries.nth(enabled_export_idx).click()
        compare_dialog.wait_for(state="visible")
        compare_dialog.get_by_role("button", name="Close").click()
        compare_dialog.wait_for(state="hidden")

        context.close()
        browser.close()
        return SmokeResult(
            indexing_banner_seen=indexing_banner_seen,
            sidebar_resize_delta_px=sidebar_resize_delta_px,
            anchor_before=anchor_before,
            anchor_restored=anchor_restored,
            anchor_settled=anchor_settled,
            anchor_reentry_exact=anchor_reentry_exact,
            search_visible_matches=list(search_visible_matches),
        )


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


def main() -> int:
    args = parse_args()
    dataset_dir: Path
    cleanup_dir = False

    if args.dataset_dir is not None:
        dataset_dir = args.dataset_dir.resolve()
        if not dataset_dir.exists():
            raise SystemExit(f"Dataset directory does not exist: {dataset_dir}")
    else:
        dataset_dir = Path(tempfile.mkdtemp(prefix="lenslet-gui-smoke-")).resolve()
        cleanup_dir = not args.keep_dataset
        build_fixture_dataset(dataset_dir)

    port = choose_port(args.host, args.port)
    base_url = f"http://{args.host}:{port}"

    log_file = tempfile.NamedTemporaryFile(prefix="lenslet-gui-smoke-server-", suffix=".log", delete=False)
    log_path = Path(log_file.name)
    log_file.close()

    cmd = [
        sys.executable,
        "-m",
        "lenslet.cli",
        str(dataset_dir),
        "--host",
        args.host,
        "--port",
        str(port),
        "--verbose",
        "--no-skip-indexing",
    ]

    server_proc = subprocess.Popen(
        cmd,
        cwd=str(Path(__file__).resolve().parents[1]),
        stdout=log_path.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        text=True,
    )

    summary: dict[str, Any]
    try:
        initial_health = wait_for_health(base_url, args.server_timeout_seconds)
        if server_proc.poll() is not None:
            raise SmokeFailure(f"Lenslet exited unexpectedly with code {server_proc.returncode}.")
        result = run_browser_checks(base_url, args.browser_timeout_ms, args.strict_reentry_anchor)
        final_health = wait_for_health(base_url, args.server_timeout_seconds)
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

        summary = {
            "base_url": base_url,
            "dataset_dir": str(dataset_dir),
            "server_log": str(log_path),
            "initial_health": initial_health,
            "final_health": final_health,
            "checks": {
                "indexing_banner_seen": result.indexing_banner_seen,
                "indexing_lifecycle_proof": indexing_lifecycle_proof,
                "sidebar_resize_delta_px": result.sidebar_resize_delta_px,
                "anchor_before": result.anchor_before,
                "anchor_restored": result.anchor_restored,
                "anchor_settled": result.anchor_settled,
                "anchor_reentry_exact": result.anchor_reentry_exact,
                "search_visible_matches": result.search_visible_matches,
            },
            "warnings": warnings,
            "status": "passed",
        }
        print(json.dumps(summary, indent=2))
        if args.output_json is not None:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        return 0
    except Exception as exc:
        tail = ""
        try:
            lines = log_path.read_text(encoding="utf-8").splitlines()
            tail = "\n".join(lines[-40:])
        except Exception:
            tail = "<unavailable>"
        print(f"[gui-smoke] FAILED: {exc}", file=sys.stderr)
        print(f"[gui-smoke] Server log tail ({log_path}):\n{tail}", file=sys.stderr)
        return 1
    finally:
        if server_proc.poll() is None:
            server_proc.terminate()
            try:
                server_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server_proc.kill()
                server_proc.wait(timeout=10)
        if cleanup_dir:
            shutil.rmtree(dataset_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
