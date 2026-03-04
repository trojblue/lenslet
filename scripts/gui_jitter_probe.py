#!/usr/bin/env python3
"""Playwright jitter probe for front-end geometry stability checks."""

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
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from PIL import Image


class SmokeFailure(RuntimeError):
    """Raised when jitter constraints fail."""


@dataclass(frozen=True)
class ProbeResult:
    scenario: str
    max_delta_px: float
    max_anchor_delta_px: float
    max_toolbar_delta_px: float
    checks: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run UI jitter probe scenarios.")
    parser.add_argument(
        "--scenario",
        choices=["toolbar"],
        required=True,
        help="Probe scenario to execute.",
    )
    parser.add_argument("--max-delta-px", type=float, default=1.0, help="Maximum allowed CSS-pixel delta.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind Lenslet server.")
    parser.add_argument("--port", type=int, default=7070, help="Preferred Lenslet port.")
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
    return parser.parse_args()


def _build_fixture_dataset(root: Path) -> None:
    payload = _jpeg_payload()
    for idx in range(12):
        _write_image(root / f"group_{idx % 3}" / f"sample_{idx:03d}.jpg", payload)


def _jpeg_payload() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (48, 32), color=(44, 88, 132)).save(buf, format="JPEG", quality=80)
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
        except TimeoutError as exc:  # pragma: no cover - runtime guard
            last_error = exc
        time.sleep(0.2)
    raise SmokeFailure(f"/health was unavailable after {timeout_seconds:.1f}s: {last_error!r}")


def _import_playwright() -> tuple[type[BaseException], type[BaseException], Any]:
    try:
        from playwright.sync_api import Error as playwright_error
        from playwright.sync_api import TimeoutError as playwright_timeout_error
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SmokeFailure(
            "playwright is required: pip install -e '.[dev]' && python -m playwright install chromium"
        ) from exc
    return playwright_error, playwright_timeout_error, sync_playwright


def _wait_for_grid(page: Any, timeout_ms: float) -> None:
    page.wait_for_selector('[role="gridcell"][id^="cell-"]', timeout=timeout_ms)


def _snapshot_toolbar(page: Any) -> dict[str, Any]:
    snapshot = page.evaluate(
        """() => {
          const shell = document.querySelector('.toolbar-shell');
          if (!shell) return null;
          const appShell = document.querySelector('.app-shell');
          const slotNames = ['back', 'refresh', 'nav', 'upload', 'search-desktop', 'search-toggle', 'search-row'];
          const controlNames = ['back', 'refresh', 'upload', 'search-desktop', 'search-toggle', 'search-mobile'];
          const anchors = {};
          for (const slotName of slotNames) {
            const node = document.querySelector(`[data-toolbar-slot="${slotName}"]`);
            if (!node) {
              anchors[slotName] = null;
              continue;
            }
            const rect = node.getBoundingClientRect();
            anchors[slotName] = {
              left: rect.left,
              top: rect.top,
              width: rect.width,
              height: rect.height,
            };
          }
          const controls = {};
          for (const controlName of controlNames) {
            const node = document.querySelector(`[data-toolbar-control="${controlName}"]`);
            if (!(node instanceof HTMLElement)) {
              controls[controlName] = null;
              continue;
            }
            const disabled = 'disabled' in node ? Boolean((node).disabled) : false;
            controls[controlName] = {
              disabled,
              tabIndex: node.tabIndex,
              ariaHidden: node.getAttribute('aria-hidden') === 'true',
            };
          }
          const toolbarVarRaw = getComputedStyle(appShell || document.documentElement).getPropertyValue('--toolbar-h').trim();
          const toolbarVarValue = Number.parseFloat(toolbarVarRaw);
          const shellRect = shell.getBoundingClientRect();
          const searchRow = document.querySelector('[data-toolbar-slot="search-row"]');
          const searchRowPointerEvents = searchRow instanceof HTMLElement
            ? getComputedStyle(searchRow).pointerEvents
            : null;
          return {
            toolbarHeight: shellRect.height,
            toolbarVarPx: Number.isFinite(toolbarVarValue) ? toolbarVarValue : null,
            searchRowPointerEvents,
            anchors,
            controls,
          };
        }"""
    )
    if not isinstance(snapshot, dict):
        raise SmokeFailure("Failed to capture toolbar snapshot.")
    return snapshot


def _anchor_delta(lhs: dict[str, Any], rhs: dict[str, Any], slot: str) -> float | None:
    left = lhs.get("anchors", {}).get(slot)
    right = rhs.get("anchors", {}).get(slot)
    if not isinstance(left, dict) or not isinstance(right, dict):
        return None
    try:
        left_delta = abs(float(left["left"]) - float(right["left"]))
        width_delta = abs(float(left["width"]) - float(right["width"]))
        top_delta = abs(float(left["top"]) - float(right["top"]))
    except (KeyError, TypeError, ValueError):
        return None
    return max(left_delta, width_delta, top_delta)


def _state_delta(lhs: dict[str, Any], rhs: dict[str, Any], key: str) -> float:
    left_raw = lhs.get(key)
    right_raw = rhs.get(key)
    if left_raw is None or right_raw is None:
        return 0.0
    try:
        return abs(float(left_raw) - float(right_raw))
    except (TypeError, ValueError):
        return 0.0


def _assert_hidden_control_state(
    snapshot: dict[str, Any],
    control_name: str,
    context: str,
    violations: list[str],
) -> None:
    control = snapshot.get("controls", {}).get(control_name)
    if not isinstance(control, dict):
        violations.append(f"{context}: missing control state for {control_name}")
        return
    if not bool(control.get("disabled")):
        violations.append(f"{context}: expected {control_name} to be disabled")
    if int(control.get("tabIndex", 0)) != -1:
        violations.append(f"{context}: expected {control_name} tabindex=-1")
    if not bool(control.get("ariaHidden")):
        violations.append(f"{context}: expected {control_name} aria-hidden=true")


def _wait_for_back_button(page: Any, timeout_ms: float) -> None:
    page.wait_for_function(
        """() => {
          const button = document.querySelector('[data-toolbar-control="back"]');
          return button instanceof HTMLButtonElement
            && !button.disabled
            && button.getAttribute('aria-hidden') !== 'true';
        }""",
        timeout=timeout_ms,
    )


def _is_viewer_open(page: Any) -> bool:
    raw = page.evaluate(
        """() => {
          const viewer = document.querySelector('[role="dialog"][aria-label="Image viewer"]');
          if (!(viewer instanceof HTMLElement)) return false;
          const rect = viewer.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0;
        }"""
    )
    return bool(raw)


def _open_viewer_with_fallback(
    page: Any,
    browser_timeout_ms: float,
    playwright_timeout_error: type[BaseException],
    playwright_error: type[BaseException],
) -> None:
    attempts = [
        lambda: page.locator('[role="gridcell"][id^="cell-"] > div').first.dblclick(),
        lambda: (
            page.locator('[role="gridcell"][id^="cell-"]').first.click(),
            page.keyboard.press("Enter"),
        ),
        lambda: page.evaluate(
            """() => {
              const target = document.querySelector('[role="gridcell"][id^="cell-"] > div');
              if (!(target instanceof HTMLElement)) return false;
              target.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true, detail: 2 }));
              return true;
            }"""
        ),
    ]
    for attempt in attempts:
        if _is_viewer_open(page):
            return
        try:
            attempt()
        except playwright_error:
            if _is_viewer_open(page):
                return
            continue
        if _is_viewer_open(page):
            return
        try:
            _wait_for_back_button(page, min(5_000, browser_timeout_ms))
            return
        except playwright_timeout_error:
            if _is_viewer_open(page):
                return
            continue
    raise SmokeFailure("Timed out waiting for viewer back button to become interactive.")


def run_toolbar_probe(base_url: str, max_delta_px: float, browser_timeout_ms: float) -> ProbeResult:
    playwright_error, playwright_timeout_error, sync_playwright = _import_playwright()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1120, "height": 840})
            page = context.new_page()
            page.set_default_timeout(browser_timeout_ms)
            page.goto(base_url, wait_until="domcontentloaded")
            _wait_for_grid(page, browser_timeout_ms)
            desktop_browse = _snapshot_toolbar(page)

            _open_viewer_with_fallback(page, browser_timeout_ms, playwright_timeout_error, playwright_error)
            desktop_viewer = _snapshot_toolbar(page)

            back_button = page.locator('[data-toolbar-control="back"]').first
            if back_button.count() > 0 and back_button.is_enabled():
                back_button.click()
            else:
                page.keyboard.press("Escape")
            _wait_for_grid(page, browser_timeout_ms)
            desktop_restored = _snapshot_toolbar(page)

            page.set_viewport_size({"width": 760, "height": 840})
            page.reload(wait_until="domcontentloaded")
            _wait_for_grid(page, browser_timeout_ms)
            narrow_closed = _snapshot_toolbar(page)

            toggle_button = page.locator('[data-toolbar-control="search-toggle"]').first
            toggle_button.click()
            try:
                page.wait_for_function(
                    """() => {
                      const input = document.querySelector('[data-toolbar-control="search-mobile"]');
                      return input instanceof HTMLInputElement && !input.disabled;
                    }""",
                    timeout=browser_timeout_ms,
                )
            except playwright_timeout_error as exc:
                raise SmokeFailure("Timed out waiting for mobile search row to open.") from exc
            narrow_open = _snapshot_toolbar(page)

            toggle_button.click()
            try:
                page.wait_for_function(
                    """() => {
                      const input = document.querySelector('[data-toolbar-control="search-mobile"]');
                      return input instanceof HTMLInputElement && input.disabled;
                    }""",
                    timeout=browser_timeout_ms,
                )
            except playwright_timeout_error as exc:
                raise SmokeFailure("Timed out waiting for mobile search row to close.") from exc
            narrow_restored = _snapshot_toolbar(page)

            context.close()
            browser.close()
    except playwright_timeout_error as exc:
        raise SmokeFailure(f"playwright timeout: {exc}") from exc
    except playwright_error as exc:
        raise SmokeFailure(f"playwright probe failed: {exc}") from exc

    slot_deltas: dict[str, float] = {}
    tracked_slots = ("back", "refresh", "nav", "upload", "search-desktop", "search-toggle")
    for slot_name in tracked_slots:
        comparisons: list[float] = []
        desktop_delta = _anchor_delta(desktop_browse, desktop_viewer, slot_name)
        if desktop_delta is not None:
            comparisons.append(desktop_delta)
        desktop_restore_delta = _anchor_delta(desktop_browse, desktop_restored, slot_name)
        if desktop_restore_delta is not None:
            comparisons.append(desktop_restore_delta)
        narrow_delta = _anchor_delta(narrow_closed, narrow_open, slot_name)
        if narrow_delta is not None:
            comparisons.append(narrow_delta)
        narrow_restore_delta = _anchor_delta(narrow_closed, narrow_restored, slot_name)
        if narrow_restore_delta is not None:
            comparisons.append(narrow_restore_delta)
        if comparisons:
            slot_deltas[slot_name] = max(comparisons)

    toolbar_deltas = {
        "desktop_toolbar_height_delta": max(
            _state_delta(desktop_browse, desktop_viewer, "toolbarHeight"),
            _state_delta(desktop_browse, desktop_restored, "toolbarHeight"),
        ),
        "desktop_toolbar_var_delta": max(
            _state_delta(desktop_browse, desktop_viewer, "toolbarVarPx"),
            _state_delta(desktop_browse, desktop_restored, "toolbarVarPx"),
        ),
        "narrow_toolbar_height_delta": max(
            _state_delta(narrow_closed, narrow_open, "toolbarHeight"),
            _state_delta(narrow_closed, narrow_restored, "toolbarHeight"),
        ),
        "narrow_toolbar_var_delta": max(
            _state_delta(narrow_closed, narrow_open, "toolbarVarPx"),
            _state_delta(narrow_closed, narrow_restored, "toolbarVarPx"),
        ),
    }

    max_anchor_delta = max(slot_deltas.values(), default=0.0)
    max_toolbar_delta = max(toolbar_deltas.values(), default=0.0)

    violations: list[str] = []
    if max_anchor_delta > max_delta_px:
        violations.append(
            f"anchor delta {max_anchor_delta:.3f}px exceeded threshold {max_delta_px:.3f}px"
        )
    if max_toolbar_delta > max_delta_px:
        violations.append(
            f"toolbar delta {max_toolbar_delta:.3f}px exceeded threshold {max_delta_px:.3f}px"
        )

    _assert_hidden_control_state(desktop_browse, "back", "desktop browse state", violations)
    _assert_hidden_control_state(desktop_viewer, "refresh", "desktop viewer state", violations)
    _assert_hidden_control_state(desktop_viewer, "upload", "desktop viewer state", violations)
    _assert_hidden_control_state(desktop_viewer, "search-desktop", "desktop viewer state", violations)
    _assert_hidden_control_state(narrow_closed, "search-mobile", "narrow browse closed state", violations)
    if narrow_closed.get("searchRowPointerEvents") != "none":
        violations.append("narrow browse closed state: expected search-row pointer-events=none")
    if narrow_open.get("searchRowPointerEvents") == "none":
        violations.append("narrow browse open state: expected search-row pointer-events to be interactive")

    checks: dict[str, Any] = {
        "slot_deltas_px": slot_deltas,
        "toolbar_deltas_px": toolbar_deltas,
        "desktop_browse_snapshot": desktop_browse,
        "desktop_viewer_snapshot": desktop_viewer,
        "desktop_restored_snapshot": desktop_restored,
        "narrow_closed_snapshot": narrow_closed,
        "narrow_open_snapshot": narrow_open,
        "narrow_restored_snapshot": narrow_restored,
        "violations": violations,
    }

    if violations:
        raise SmokeFailure("; ".join(violations))

    return ProbeResult(
        scenario="toolbar",
        max_delta_px=max_delta_px,
        max_anchor_delta_px=max_anchor_delta,
        max_toolbar_delta_px=max_toolbar_delta,
        checks=checks,
    )


def _write_output_json(path: Path | None, summary: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


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
        _build_fixture_dataset(dataset_dir)

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
        "--verbose",
        "--no-skip-indexing",
    ]
    process = subprocess.Popen(command, cwd=str(Path(__file__).resolve().parents[1]), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    summary: dict[str, Any]
    try:
        wait_for_health(base_url, args.server_timeout_seconds)
        if process.poll() is not None:
            raise SmokeFailure(f"Lenslet exited unexpectedly with code {process.returncode}.")

        result = run_toolbar_probe(base_url, args.max_delta_px, args.browser_timeout_ms)

        summary = {
            "status": "passed",
            "base_url": base_url,
            "dataset_dir": str(dataset_dir),
            "scenario": result.scenario,
            "max_delta_px": result.max_delta_px,
            "max_anchor_delta_px": result.max_anchor_delta_px,
            "max_toolbar_delta_px": result.max_toolbar_delta_px,
            "checks": result.checks,
        }
        print(json.dumps(summary, indent=2))
        _write_output_json(args.output_json, summary)
        return 0
    except Exception as exc:
        summary = {
            "status": "failed",
            "base_url": base_url,
            "dataset_dir": str(dataset_dir),
            "scenario": args.scenario,
            "max_delta_px": args.max_delta_px,
            "error": str(exc),
        }
        print(json.dumps(summary, indent=2), file=sys.stderr)
        _write_output_json(args.output_json, summary)
        return 1
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        if cleanup_dataset:
            shutil.rmtree(dataset_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
