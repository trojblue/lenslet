#!/usr/bin/env python3
"""Playwright jitter probe for front-end geometry stability checks."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.error import URLError
from urllib.request import urlopen

from PIL import Image, PngImagePlugin


class SmokeFailure(RuntimeError):
    """Raised when jitter constraints fail."""


@dataclass(frozen=True)
class ProbeResult:
    scenario: str
    max_delta_px: float
    max_anchor_delta_px: float = 0.0
    max_toolbar_delta_px: float = 0.0
    max_top_stack_delta_px: float = 0.0
    max_grid_width_delta_px: float = 0.0
    max_inspector_delta_px: float = 0.0
    checks: dict[str, Any] = field(default_factory=dict)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run UI jitter probe scenarios.")
    parser.add_argument(
        "--scenario",
        choices=["toolbar", "grid", "inspector"],
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


def _build_fixture_dataset(root: Path) -> None:
    payload = _jpeg_payload()
    for idx in range(12):
        _write_image(root / f"sample_{idx:03d}.jpg", payload)
    _build_inspector_fixture_images(root)
    _write_fixture_items_parquet(root)
    _write_fixture_labels_snapshot(root)


def _build_inspector_fixture_images(root: Path) -> None:
    _write_png_with_metadata(
        root / "quick_00_meta.png",
        itxt_chunks={
            "qfty_meta": json.dumps(
                {
                    "prompt": "alpha prompt",
                    "model": "alpha-model",
                    "lora": {"alpha-lora.safetensors": 0.8},
                }
            )
        },
    )
    _write_png_with_metadata(
        root / "quick_01_meta.png",
        itxt_chunks={
            "qfty_meta": json.dumps(
                {
                    "prompt": "beta prompt",
                    "model": "beta-model",
                    "lora": {"beta-lora.safetensors": 1.2},
                }
            )
        },
    )
    _write_png_with_metadata(
        root / "quick_02_plain.png",
        text_chunks={"comment": "no quick-view defaults"},
    )
    _write_png_with_metadata(
        root / "quick_03_meta.png",
        itxt_chunks={
            "qfty_meta": json.dumps(
                {
                    "prompt": "gamma prompt",
                    "model": "gamma-model",
                    "lora": {"gamma-lora.safetensors": 0.6},
                }
            )
        },
    )


def _iter_fixture_image_paths(root: Path) -> list[Path]:
    allowed = {".jpg", ".jpeg", ".png", ".webp"}
    paths = [path for path in root.iterdir() if path.is_file() and path.suffix.lower() in allowed]
    return sorted(paths, key=lambda path: path.name)


def _write_fixture_labels_snapshot(root: Path) -> None:
    items: dict[str, Any] = {}
    for idx, image_path in enumerate(_iter_fixture_image_paths(root)):
        path = f"/{image_path.name}"
        score = round((idx % 7) / 7.0, 6)
        items[path] = {
            "tags": [],
            "notes": "",
            "star": None,
            "version": 100,
            "updated_at": "",
            "updated_by": "probe",
            "metrics": {
                "probe_score": score,
                "probe_rank": float(idx),
            },
        }

    payload = {
        "version": 1,
        "last_event_id": len(items),
        "items": items,
    }
    snapshot_path = root / ".lenslet" / "labels.snapshot.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_fixture_items_parquet(root: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    rows: list[dict[str, Any]] = []
    for idx, image_path in enumerate(_iter_fixture_image_paths(root)):
        rel_path = image_path.name
        score = round((idx % 7) / 7.0, 6)
        rows.append(
            {
                "path": rel_path,
                "source": str((root / rel_path).resolve()),
                "metrics": {
                    "probe_score": score,
                    "probe_rank": float(idx),
                },
            }
        )
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, root / "items.parquet")


def _jpeg_payload() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (48, 32), color=(44, 88, 132)).save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def _write_image(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _write_png_with_metadata(
    path: Path,
    *,
    text_chunks: dict[str, str] | None = None,
    itxt_chunks: dict[str, str] | None = None,
) -> None:
    meta = PngImagePlugin.PngInfo()
    for key, value in (text_chunks or {}).items():
        meta.add_text(key, value)
    for key, value in (itxt_chunks or {}).items():
        meta.add_itxt(key, value)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (48, 32), color=(72, 36, 120)).save(path, format="PNG", pnginfo=meta)


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


COUNT_LABEL_RE = re.compile(r"^\s*(\d[\d,]*)\s*(?:/\s*(\d[\d,]*)\s*)?items\s*$")


def _read_toolbar_counts(page: Any) -> dict[str, Any]:
    label = page.locator(".toolbar-count").first.text_content()
    if not isinstance(label, str):
        raise SmokeFailure("Toolbar count label is missing.")
    match = COUNT_LABEL_RE.match(label.strip())
    if match is None:
        raise SmokeFailure(f"Unexpected toolbar count label: {label!r}")
    current = int(match.group(1).replace(",", ""))
    total_raw = match.group(2)
    total = current if total_raw is None else int(total_raw.replace(",", ""))
    return {
        "label": label.strip(),
        "current": current,
        "total": total,
    }


def _visible_grid_paths(page: Any, limit: int = 12) -> list[str]:
    raw = page.evaluate(
        """(maxItems) => {
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
              return { path, top: rect.top, left: rect.left, bottom: rect.bottom, right: rect.right };
            })
            .filter((entry) => entry.path && entry.bottom > 0 && entry.right > 0 && entry.top < window.innerHeight && entry.left < window.innerWidth);
          cells.sort((a, b) => (a.top - b.top) || (a.left - b.left));
          return cells.slice(0, maxItems).map((entry) => entry.path);
        }""",
        limit,
    )
    if not isinstance(raw, list):
        raise SmokeFailure("Failed to capture visible grid paths.")
    return [candidate for candidate in raw if isinstance(candidate, str) and candidate]


def _open_metrics_panel(page: Any, timeout_ms: float) -> None:
    button = page.locator('button[aria-label="Metrics and Filters"]').first
    if button.count() == 0:
        raise SmokeFailure("Metrics panel trigger is missing.")
    if button.get_attribute("aria-pressed") != "true":
        button.click()
    page.wait_for_function(
        """() => {
          const button = document.querySelector('button[aria-label="Metrics and Filters"]');
          return button instanceof HTMLButtonElement && button.getAttribute('aria-pressed') === 'true';
        }""",
        timeout=timeout_ms,
    )


def _read_metric_panel_keys(page: Any) -> list[str]:
    raw = page.evaluate(
        """() => {
          const metricSelect = document.querySelector('.app-left-panel select.ui-select');
          if (!(metricSelect instanceof HTMLSelectElement)) return [];
          return Array.from(metricSelect.options)
            .map((option) => option.textContent || '')
            .map((label) => label.trim())
            .filter((label) => label.length > 0);
        }"""
    )
    if not isinstance(raw, list):
        raise SmokeFailure("Failed to read metric panel options.")
    return [candidate for candidate in raw if isinstance(candidate, str)]


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


def _snapshot_grid(page: Any) -> dict[str, Any]:
    snapshot = page.evaluate(
        """() => {
          const topStack = document.querySelector('[data-grid-top-stack]');
          const topStackRect = topStack instanceof HTMLElement ? topStack.getBoundingClientRect() : null;
          const bandNames = ['status', 'similarity', 'filters'];
          const bandHeights = {};
          const bandHidden = {};
          for (const bandName of bandNames) {
            const band = document.querySelector(`[data-grid-top-band="${bandName}"]`);
            if (!(band instanceof HTMLElement)) {
              bandHeights[bandName] = null;
              bandHidden[bandName] = null;
              continue;
            }
            const rect = band.getBoundingClientRect();
            bandHeights[bandName] = rect.height;
            bandHidden[bandName] = band.getAttribute('aria-hidden') === 'true';
          }

          const bodyMain = document.querySelector('[data-grid-body-main]');
          const bodyRect = bodyMain instanceof HTMLElement ? bodyMain.getBoundingClientRect() : null;
          const rail = document.querySelector('[data-metric-rail-slot]');
          const railRect = rail instanceof HTMLElement ? rail.getBoundingClientRect() : null;
          const railActive = rail instanceof HTMLElement
            ? rail.getAttribute('data-metric-rail-active') === 'true'
            : null;

          const scrollRoot = document.querySelector('[role="grid"][aria-label="Gallery"]');
          const scrollRootClasses = scrollRoot instanceof HTMLElement ? Array.from(scrollRoot.classList) : [];
          const usesHiddenScrollbar = scrollRootClasses.includes('scrollbar-hidden');

          let persistedSortSpec = null;
          try {
            const rawSortSpec = window.localStorage.getItem('sortSpec');
            if (rawSortSpec) {
              const parsedSortSpec = JSON.parse(rawSortSpec);
              if (parsedSortSpec && typeof parsedSortSpec === 'object') {
                persistedSortSpec = parsedSortSpec;
              }
            }
          } catch (error) {
            persistedSortSpec = null;
          }

          const firstCell = document.querySelector('[role="gridcell"][id^="cell-"]');
          const firstCellRect = firstCell instanceof HTMLElement ? firstCell.getBoundingClientRect() : null;

          return {
            topStackHeight: topStackRect ? topStackRect.height : null,
            topStackTop: topStackRect ? topStackRect.top : null,
            bandHeights,
            bandHidden,
            gridBodyWidth: bodyRect ? bodyRect.width : null,
            gridBodyLeft: bodyRect ? bodyRect.left : null,
            metricRailWidth: railRect ? railRect.width : null,
            metricRailActive: railActive,
            firstCellLeft: firstCellRect ? firstCellRect.left : null,
            firstCellWidth: firstCellRect ? firstCellRect.width : null,
            scrollRootClasses,
            scrollRootUsesHiddenScrollbar: usesHiddenScrollbar,
            persistedSortKind: persistedSortSpec ? persistedSortSpec.kind ?? null : null,
            persistedSortKey: persistedSortSpec ? persistedSortSpec.key ?? null : null,
          };
        }"""
    )
    if not isinstance(snapshot, dict):
        raise SmokeFailure("Failed to capture grid snapshot.")
    return snapshot


def _set_local_storage(page: Any, values: dict[str, str | None]) -> None:
    page.evaluate(
        """(entries) => {
          for (const [key, value] of Object.entries(entries)) {
            if (value === null) {
              window.localStorage.removeItem(key);
            } else {
              window.localStorage.setItem(key, value);
            }
          }
        }""",
        values,
    )


def _state_delta_nested(lhs: dict[str, Any], rhs: dict[str, Any], parent_key: str, key: str) -> float:
    left_parent = lhs.get(parent_key)
    right_parent = rhs.get(parent_key)
    if not isinstance(left_parent, dict) or not isinstance(right_parent, dict):
        return 0.0
    left_raw = left_parent.get(key)
    right_raw = right_parent.get(key)
    if left_raw is None or right_raw is None:
        return 0.0
    try:
        return abs(float(left_raw) - float(right_raw))
    except (TypeError, ValueError):
        return 0.0


def run_grid_probe(
    base_url: str,
    max_delta_px: float,
    browser_timeout_ms: float,
    *,
    expected_metric_key: str | None = None,
    forbidden_metric_keys: list[str] | None = None,
    metric_filter_min: float | None = None,
    metric_filter_max: float | None = None,
) -> ProbeResult:
    playwright_error, playwright_timeout_error, sync_playwright = _import_playwright()
    sort_panel_selector = '.dropdown-panel[role="listbox"][aria-label="Sort and layout"]'
    forbidden_metric_keys = forbidden_metric_keys or []

    def ensure_sort_trigger(page: Any) -> Any:
        trigger = page.locator('button[aria-label="Sort and layout"]').first
        if trigger.count() == 0:
            raise SmokeFailure("Sort dropdown trigger is missing.")
        if trigger.is_disabled():
            switch_button = page.locator('button:has-text("Switch to Most recent")').first
            if switch_button.count() > 0:
                switch_button.click()
                page.wait_for_function(
                    """() => {
                      const button = document.querySelector('button[aria-label="Sort and layout"]');
                      return button instanceof HTMLButtonElement ? !button.disabled : false;
                    }""",
                    timeout=browser_timeout_ms,
                )
            if trigger.is_disabled():
                raise SmokeFailure("Sort dropdown trigger is disabled.")
        return trigger

    def open_sort_panel(page: Any) -> tuple[Any, Any]:
        trigger = ensure_sort_trigger(page)
        trigger.click()
        page.wait_for_selector(sort_panel_selector, timeout=browser_timeout_ms)
        panel = page.locator(sort_panel_selector).first
        return trigger, panel

    def list_metric_sort_labels(page: Any) -> list[str]:
        trigger, panel = open_sort_panel(page)
        option_labels = [label.strip() for label in panel.locator("button.dropdown-item").all_inner_texts()]
        builtin_options = {"Grid", "Masonry", "Date added", "Filename", "Random"}
        metric_labels = [label for label in option_labels if label and label not in builtin_options]
        trigger.click()
        return metric_labels

    def set_json_storage(page: Any, payload: dict[str, Any]) -> None:
        serialized: dict[str, str | None] = {}
        for key, value in payload.items():
            if value is None:
                serialized[key] = None
            elif isinstance(value, str):
                serialized[key] = value
            else:
                serialized[key] = json.dumps(value)
        _set_local_storage(page, serialized)

    def reload_with_state(page: Any, payload: dict[str, Any]) -> None:
        set_json_storage(page, payload)
        page.reload(wait_until="domcontentloaded")
        _wait_for_grid(page, browser_timeout_ms)

    def wait_for_sort_state(page: Any, kind: str, key: str, direction: str) -> None:
        page.wait_for_function(
            """(expected) => {
              try {
                const rawSortSpec = window.localStorage.getItem('sortSpec');
                if (!rawSortSpec) return false;
                const sortSpec = JSON.parse(rawSortSpec);
                return sortSpec?.kind === expected.kind
                  && sortSpec?.key === expected.key
                  && sortSpec?.dir === expected.dir;
              } catch {
                return false;
              }
            }""",
            arg={"kind": kind, "key": key, "dir": direction},
            timeout=browser_timeout_ms,
        )

    def wait_for_count_change(page: Any, previous_label: str) -> None:
        page.wait_for_function(
            """(baselineLabel) => {
              const node = document.querySelector('.toolbar-count');
              if (!(node instanceof HTMLElement)) return false;
              const label = (node.textContent || '').trim();
              return label.includes('/') || label !== baselineLabel;
            }""",
            arg=previous_label,
            timeout=browser_timeout_ms,
        )

    def wait_for_metric_rail(page: Any, *, active: bool) -> None:
        page.wait_for_function(
            """(expectedActive) => {
              const rail = document.querySelector('[data-metric-rail-slot]');
              if (!(rail instanceof HTMLElement)) return false;
              const isActive = rail.getAttribute('data-metric-rail-active') === 'true';
              return isActive === expectedActive;
            }""",
            arg=active,
            timeout=browser_timeout_ms,
        )

    def select_sort_option(page: Any, label: str) -> None:
        _, panel = open_sort_panel(page)
        option = panel.locator("button.dropdown-item", has_text=label).first
        if option.count() == 0:
            available = panel.locator("button.dropdown-item").all_inner_texts()
            raise SmokeFailure(f"Sort option '{label}' not found. Available options: {available}")
        option.click()

    def wait_for_filters_band(page: Any, *, hidden: bool) -> None:
        page.wait_for_function(
            """(expectedHidden) => {
              const band = document.querySelector('[data-grid-top-band="filters"]');
              if (!(band instanceof HTMLElement)) return false;
              const isHidden = band.getAttribute('aria-hidden') === 'true';
              return isHidden === expectedHidden;
            }""",
            arg=hidden,
            timeout=browser_timeout_ms,
        )

    def enable_unrated_filter(page: Any) -> None:
        filters_button = page.locator('button[title="Filters"]').first
        filters_button.click()
        page.wait_for_selector('[role="dialog"][aria-label="Filters"]', timeout=browser_timeout_ms)
        page.locator('[role="dialog"][aria-label="Filters"] button:has-text("Unrated")').first.click()
        try:
            filters_button.click()
        except playwright_error:
            pass
        wait_for_filters_band(page, hidden=False)

    def clear_filter_chips(page: Any) -> None:
        clear_button = page.locator('[data-grid-top-band="filters"] button:has-text("Clear all")').first
        if clear_button.count() > 0:
            clear_button.click()
        wait_for_filters_band(page, hidden=True)

    metric_sort_label = ""
    metric_sort_labels: list[str] = []
    metric_panel_keys: list[str] = []
    baseline_counts: dict[str, Any] | None = None
    filtered_counts: dict[str, Any] | None = None
    metric_desc_visible_paths: list[str] = []
    metric_asc_visible_paths: list[str] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 840})
            page = context.new_page()
            page.set_default_timeout(browser_timeout_ms)

            page.goto(base_url, wait_until="domcontentloaded")
            _wait_for_grid(page, browser_timeout_ms)

            base_payload = {
                "sortSpec": {"kind": "builtin", "key": "added", "dir": "desc"},
                "sortKey": "added",
                "sortDir": "desc",
                "selectedMetric": None,
                "filterAst": {"and": []},
                "starFilters": [],
            }

            reload_with_state(page, base_payload)
            baseline_counts = _read_toolbar_counts(page)

            # Warm up reservation on the running page so hide/show checks capture steady-state toggles.
            enable_unrated_filter(page)
            warmup_filters_active = _snapshot_grid(page)
            clear_filter_chips(page)

            builtin_initial = _snapshot_grid(page)

            enable_unrated_filter(page)
            filters_active = _snapshot_grid(page)

            clear_filter_chips(page)
            filters_cleared = _snapshot_grid(page)

            metric_sort_labels = list_metric_sort_labels(page)
            if not metric_sort_labels:
                raise SmokeFailure("No metric sort options found in the sort menu.")
            if expected_metric_key and expected_metric_key not in metric_sort_labels:
                raise SmokeFailure(
                    f"Expected metric sort option '{expected_metric_key}' not found. "
                    f"Available metric options: {metric_sort_labels}"
                )
            forbidden_in_sort = [key for key in forbidden_metric_keys if key in metric_sort_labels]
            if forbidden_in_sort:
                raise SmokeFailure(f"Forbidden metric sort options found: {forbidden_in_sort}")
            metric_sort_label = expected_metric_key or metric_sort_labels[0]

            _open_metrics_panel(page, browser_timeout_ms)
            metric_panel_keys = _read_metric_panel_keys(page)
            if expected_metric_key and expected_metric_key not in metric_panel_keys:
                raise SmokeFailure(
                    f"Expected metric filter option '{expected_metric_key}' not found. "
                    f"Available metric filters: {metric_panel_keys}"
                )
            forbidden_in_panel = [key for key in forbidden_metric_keys if key in metric_panel_keys]
            if forbidden_in_panel:
                raise SmokeFailure(f"Forbidden metric filter options found: {forbidden_in_panel}")

            select_sort_option(page, metric_sort_label)
            wait_for_metric_rail(page, active=True)
            wait_for_sort_state(page, "metric", metric_sort_label, "desc")
            metric_mode = _snapshot_grid(page)
            metric_desc_visible_paths = _visible_grid_paths(page)

            sort_dir_toggle = page.locator('button[aria-label="Toggle sort direction"]').first
            sort_dir_toggle.click()
            wait_for_sort_state(page, "metric", metric_sort_label, "asc")
            page.wait_for_timeout(150)
            metric_asc_visible_paths = _visible_grid_paths(page)

            select_sort_option(page, "Date added")
            wait_for_sort_state(page, "builtin", "added", "asc")
            wait_for_metric_rail(page, active=False)
            builtin_restored = _snapshot_grid(page)

            filter_metric_key = expected_metric_key or metric_sort_label
            if metric_filter_min is not None or metric_filter_max is not None:
                reload_with_state(
                    page,
                    {
                        **base_payload,
                        "selectedMetric": filter_metric_key,
                        "filterAst": {
                            "and": [
                                {
                                    "metricRange": {
                                        "key": filter_metric_key,
                                        "min": metric_filter_min if metric_filter_min is not None else -1e308,
                                        "max": metric_filter_max if metric_filter_max is not None else 1e308,
                                    }
                                }
                            ]
                        },
                    },
                )
                if baseline_counts is not None:
                    wait_for_count_change(page, baseline_counts["label"])
                filtered_counts = _read_toolbar_counts(page)

            context.close()
            browser.close()
    except playwright_timeout_error as exc:
        raise SmokeFailure(f"playwright timeout: {exc}") from exc
    except playwright_error as exc:
        raise SmokeFailure(f"playwright probe failed: {exc}") from exc

    top_stack_deltas = {
        "baseline_to_filters_top_stack_delta": _state_delta(builtin_initial, filters_active, "topStackHeight"),
        "baseline_to_restored_top_stack_delta": _state_delta(builtin_initial, filters_cleared, "topStackHeight"),
    }
    for band_name in ("status", "similarity", "filters"):
        top_stack_deltas[f"baseline_to_filters_{band_name}_band_delta"] = _state_delta_nested(
            builtin_initial,
            filters_active,
            "bandHeights",
            band_name,
        )
        top_stack_deltas[f"baseline_to_restored_{band_name}_band_delta"] = _state_delta_nested(
            builtin_initial,
            filters_cleared,
            "bandHeights",
            band_name,
        )

    grid_width_deltas = {
        "metric_to_restored_body_width_delta": _state_delta(metric_mode, builtin_restored, "gridBodyWidth"),
        "metric_to_restored_first_cell_left_delta": _state_delta(metric_mode, builtin_restored, "firstCellLeft"),
        "metric_to_restored_first_cell_width_delta": _state_delta(metric_mode, builtin_restored, "firstCellWidth"),
        "metric_to_restored_rail_width_delta": _state_delta(metric_mode, builtin_restored, "metricRailWidth"),
    }

    max_top_stack_delta = max(top_stack_deltas.values(), default=0.0)
    max_grid_width_delta = max(grid_width_deltas.values(), default=0.0)

    violations: list[str] = []
    if max_top_stack_delta > max_delta_px:
        violations.append(
            f"top-stack delta {max_top_stack_delta:.3f}px exceeded threshold {max_delta_px:.3f}px"
        )
    if max_grid_width_delta > max_delta_px:
        violations.append(
            f"grid-width delta {max_grid_width_delta:.3f}px exceeded threshold {max_delta_px:.3f}px"
        )

    snapshots = {
        "warmup_filters_active": warmup_filters_active,
        "builtin_initial": builtin_initial,
        "filters_active": filters_active,
        "filters_cleared": filters_cleared,
        "metric_mode": metric_mode,
        "builtin_restored": builtin_restored,
    }

    for name, snapshot in snapshots.items():
        if bool(snapshot.get("scrollRootUsesHiddenScrollbar")):
            violations.append(f"{name}: expected scroll root to avoid scrollbar-hidden mode")
        if snapshot.get("metricRailWidth") is None:
            violations.append(f"{name}: missing metric rail slot width measurement")
        for band_name in ("status", "similarity", "filters"):
            band_value = snapshot.get("bandHeights", {}).get(band_name)
            if band_value is None:
                violations.append(f"{name}: missing mounted top-stack band '{band_name}'")

    if metric_mode.get("metricRailActive") is not True:
        violations.append("metric_mode: metric rail did not activate after requesting metric sort")
    if metric_mode.get("persistedSortKind") != "metric":
        violations.append("metric_mode: expected persisted sort kind to be metric")
    if metric_sort_label and metric_mode.get("persistedSortKey") != metric_sort_label:
        violations.append(
            f"metric_mode: expected persisted metric sort key {metric_sort_label}"
        )
    if builtin_restored.get("persistedSortKind") != "builtin":
        violations.append("builtin_restored: expected persisted sort kind to return to builtin")
    if metric_desc_visible_paths and metric_asc_visible_paths and metric_desc_visible_paths == metric_asc_visible_paths:
        violations.append("metric sort direction toggle did not reorder visible items")
    if baseline_counts is not None and filtered_counts is not None:
        if filtered_counts["current"] >= baseline_counts["current"]:
            violations.append(
                "metric range filter did not reduce the visible item count "
                f"({filtered_counts['label']} vs {baseline_counts['label']})"
            )
        if filtered_counts["current"] >= filtered_counts["total"]:
            violations.append(
                "metric range filter did not produce a filtered count label "
                f"({filtered_counts['label']})"
            )

    checks: dict[str, Any] = {
        "top_stack_deltas_px": top_stack_deltas,
        "grid_width_deltas_px": grid_width_deltas,
        "builtin_initial_snapshot": builtin_initial,
        "filters_active_snapshot": filters_active,
        "filters_cleared_snapshot": filters_cleared,
        "metric_mode_snapshot": metric_mode,
        "builtin_restored_snapshot": builtin_restored,
        "metric_sort_label": metric_sort_label,
        "metric_sort_labels": metric_sort_labels,
        "metric_panel_keys": metric_panel_keys,
        "metric_desc_visible_paths": metric_desc_visible_paths,
        "metric_asc_visible_paths": metric_asc_visible_paths,
        "baseline_counts": baseline_counts,
        "filtered_counts": filtered_counts,
        "violations": violations,
    }

    if violations:
        raise SmokeFailure("; ".join(violations))

    return ProbeResult(
        scenario="grid",
        max_delta_px=max_delta_px,
        max_top_stack_delta_px=max_top_stack_delta,
        max_grid_width_delta_px=max_grid_width_delta,
        checks=checks,
    )


def _snapshot_quick_view_section(page: Any) -> dict[str, Any]:
    snapshot = page.evaluate(
        """() => {
          const section = document.querySelector('[data-inspector-section-id="quickView"]');
          if (!(section instanceof HTMLElement)) {
            return {
              present: false,
              top: null,
              height: null,
              rowCount: 0,
              placeholderRowCount: 0,
              loading: false,
              promptValue: null,
            };
          }

          const rect = section.getBoundingClientRect();
          const rows = Array.from(section.querySelectorAll('.ui-kv-row'));
          const visibleRows = rows.filter((row) => row.getAttribute('aria-hidden') !== 'true');
          const placeholderRows = rows.filter((row) => row.getAttribute('aria-hidden') === 'true');
          let promptValue = null;

          for (const row of visibleRows) {
            const label = row.querySelector('.ui-kv-label');
            const value = row.querySelector('.ui-kv-value');
            if (!(label instanceof HTMLElement) || !(value instanceof HTMLElement)) continue;
            if ((label.textContent || '').trim() !== 'Prompt') continue;
            promptValue = (value.textContent || '').trim();
            break;
          }

          return {
            present: true,
            top: rect.top,
            height: rect.height,
            rowCount: visibleRows.length,
            placeholderRowCount: placeholderRows.length,
            loading: (section.textContent || '').includes('Loading metadata…'),
            promptValue,
          };
        }"""
    )
    if not isinstance(snapshot, dict):
        raise SmokeFailure("Failed to capture Quick View snapshot.")
    return snapshot


def _quick_view_delta(lhs: dict[str, Any], rhs: dict[str, Any]) -> float:
    if not bool(lhs.get("present")) or not bool(rhs.get("present")):
        return 0.0
    try:
        top_delta = abs(float(lhs.get("top")) - float(rhs.get("top")))
        height_delta = abs(float(lhs.get("height")) - float(rhs.get("height")))
    except (TypeError, ValueError):
        return 0.0
    return max(top_delta, height_delta)


def _select_grid_path(page: Any, path: str, browser_timeout_ms: float) -> None:
    selector = f'[id="cell-{quote(path, safe="")}"]'
    cell = page.locator(selector).first
    if cell.count() == 0:
        raise SmokeFailure(f"Grid cell for {path} not found.")
    cell.click()
    page.wait_for_function(
        """(targetPath) => {
          const panel = document.querySelector('.app-right-panel');
          if (!(panel instanceof HTMLElement)) return false;
          const filename = targetPath.split('/').filter(Boolean).pop() || targetPath;
          return (panel.textContent || '').includes(filename);
        }""",
        arg=path,
        timeout=browser_timeout_ms,
    )


def run_inspector_probe(base_url: str, max_delta_px: float, browser_timeout_ms: float) -> ProbeResult:
    playwright_error, playwright_timeout_error, sync_playwright = _import_playwright()
    quick_zero_path = "/quick_00_meta.png"
    quick_one_path = "/quick_01_meta.png"
    plain_path = "/quick_02_plain.png"
    quick_three_path = "/quick_03_meta.png"

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})

            def metadata_delay(route: Any) -> None:
                request_url = route.request.url
                delay_ms = 100
                if "quick_00_meta.png" in request_url:
                    delay_ms = 320
                elif "quick_01_meta.png" in request_url:
                    delay_ms = 45
                elif "quick_02_plain.png" in request_url:
                    delay_ms = 180
                elif "quick_03_meta.png" in request_url:
                    delay_ms = 260
                time.sleep(delay_ms / 1000.0)
                route.continue_()

            context.route("**/metadata**", metadata_delay)
            page = context.new_page()
            page.set_default_timeout(browser_timeout_ms)

            page.goto(base_url, wait_until="domcontentloaded")
            _wait_for_grid(page, browser_timeout_ms)

            _set_local_storage(
                page,
                {
                    "autoloadImageMetadata": "true",
                    "sortSpec": json.dumps({"kind": "builtin", "key": "name", "dir": "asc"}),
                    "sortKey": "name",
                    "sortDir": "asc",
                    "selectedMetric": None,
                    "filterAst": json.dumps({"and": []}),
                    "starFilters": json.dumps([]),
                    "lenslet.inspector.sections": json.dumps(
                        {
                            "quickView": True,
                            "overview": True,
                            "compare": True,
                            "metadata": True,
                            "basics": True,
                            "notes": True,
                        }
                    ),
                },
            )
            page.reload(wait_until="domcontentloaded")
            _wait_for_grid(page, browser_timeout_ms)

            _select_grid_path(page, quick_zero_path, browser_timeout_ms)
            page.wait_for_timeout(20)
            _select_grid_path(page, quick_one_path, browser_timeout_ms)

            try:
                page.wait_for_function(
                    """() => {
                      const section = document.querySelector('[data-inspector-section-id="quickView"]');
                      if (!(section instanceof HTMLElement)) return false;
                      const promptRow = Array.from(section.querySelectorAll('.ui-kv-row')).find((row) => {
                        const label = row.querySelector('.ui-kv-label');
                        return label instanceof HTMLElement && (label.textContent || '').trim() === 'Prompt';
                      });
                      if (!(promptRow instanceof HTMLElement)) return false;
                      const value = promptRow.querySelector('.ui-kv-value');
                      const promptText = value instanceof HTMLElement ? (value.textContent || '').trim() : '';
                      return promptText.includes('beta prompt')
                        && !promptText.includes('alpha prompt')
                        && !(section.textContent || '').includes('Loading metadata…');
                    }""",
                    timeout=browser_timeout_ms,
                )
            except playwright_timeout_error as exc:
                raise SmokeFailure(
                    "Timed out waiting for quick-view to settle on latest selection without stale hydration."
                ) from exc
            quick_one_loaded = _snapshot_quick_view_section(page)
            page.wait_for_timeout(120)

            _select_grid_path(page, quick_three_path, browser_timeout_ms)
            pending_quick = _snapshot_quick_view_section(page)
            try:
                page.wait_for_function(
                    """() => {
                      const section = document.querySelector('[data-inspector-section-id="quickView"]');
                      if (!(section instanceof HTMLElement)) return false;
                      if ((section.textContent || '').includes('Loading metadata…')) return false;
                      const promptRow = Array.from(section.querySelectorAll('.ui-kv-row')).find((row) => {
                        const label = row.querySelector('.ui-kv-label');
                        return label instanceof HTMLElement && (label.textContent || '').trim() === 'Prompt';
                      });
                      if (!(promptRow instanceof HTMLElement)) return false;
                      const value = promptRow.querySelector('.ui-kv-value');
                      const promptText = value instanceof HTMLElement ? (value.textContent || '').trim() : '';
                      return promptText.includes('gamma prompt');
                    }""",
                    timeout=browser_timeout_ms,
                )
            except playwright_timeout_error as exc:
                raise SmokeFailure("Timed out waiting for quick-view quick->quick hydration.") from exc
            quick_three_loaded = _snapshot_quick_view_section(page)
            page.wait_for_timeout(120)

            _select_grid_path(page, plain_path, browser_timeout_ms)
            pending_plain = _snapshot_quick_view_section(page)
            try:
                page.wait_for_function(
                    """() => !document.querySelector('[data-inspector-section-id="quickView"]')""",
                    timeout=browser_timeout_ms,
                )
            except playwright_timeout_error as exc:
                raise SmokeFailure("Timed out waiting for Quick View reservation to clear for plain metadata.") from exc
            plain_resolved = _snapshot_quick_view_section(page)

            context.close()
            browser.close()
    except playwright_timeout_error as exc:
        raise SmokeFailure(f"playwright timeout: {exc}") from exc
    except playwright_error as exc:
        raise SmokeFailure(f"playwright probe failed: {exc}") from exc

    quick_view_deltas = {
        "quick_to_quick_pending_delta": _quick_view_delta(quick_one_loaded, pending_quick),
        "quick_to_quick_loaded_delta": _quick_view_delta(quick_one_loaded, quick_three_loaded),
        "quick_to_plain_pending_delta": _quick_view_delta(quick_three_loaded, pending_plain),
    }
    max_inspector_delta = max(quick_view_deltas.values(), default=0.0)

    violations: list[str] = []
    if max_inspector_delta > max_delta_px:
        violations.append(
            f"inspector delta {max_inspector_delta:.3f}px exceeded threshold {max_delta_px:.3f}px"
        )
    if not bool(pending_quick.get("present")):
        violations.append("quick->quick pending: expected Quick View section to remain mounted")
    if not bool(pending_plain.get("present")):
        violations.append("quick->plain pending: expected Quick View section to remain mounted")
    if bool(plain_resolved.get("present")):
        violations.append("quick->plain resolved: expected Quick View section to unmount after metadata settles")
    prompt_value = str(quick_one_loaded.get("promptValue") or "")
    if "beta prompt" not in prompt_value or "alpha prompt" in prompt_value:
        violations.append("stale protection: expected quick-view prompt to match latest selection")

    checks: dict[str, Any] = {
        "quick_view_deltas_px": quick_view_deltas,
        "quick_one_loaded_snapshot": quick_one_loaded,
        "pending_quick_snapshot": pending_quick,
        "quick_three_loaded_snapshot": quick_three_loaded,
        "pending_plain_snapshot": pending_plain,
        "plain_resolved_snapshot": plain_resolved,
        "violations": violations,
    }

    if violations:
        raise SmokeFailure("; ".join(violations))

    return ProbeResult(
        scenario="inspector",
        max_delta_px=max_delta_px,
        max_inspector_delta_px=max_inspector_delta,
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
    ]
    process = subprocess.Popen(command, cwd=str(Path(__file__).resolve().parents[1]), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    summary: dict[str, Any]
    try:
        wait_for_health(base_url, args.server_timeout_seconds)
        if process.poll() is not None:
            raise SmokeFailure(f"Lenslet exited unexpectedly with code {process.returncode}.")

        if args.scenario == "toolbar":
            result = run_toolbar_probe(base_url, args.max_delta_px, args.browser_timeout_ms)
        elif args.scenario == "grid":
            result = run_grid_probe(
                base_url,
                args.max_delta_px,
                args.browser_timeout_ms,
                expected_metric_key=args.expected_metric_key,
                forbidden_metric_keys=list(args.forbid_metric_key),
                metric_filter_min=args.metric_filter_min,
                metric_filter_max=args.metric_filter_max,
            )
        else:
            result = run_inspector_probe(base_url, args.max_delta_px, args.browser_timeout_ms)

        summary = {
            "status": "passed",
            "base_url": base_url,
            "dataset_dir": str(dataset_dir),
            "scenario": result.scenario,
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
