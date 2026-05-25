#!/usr/bin/env python3
"""Minimal responsive layout geometry evidence for Lenslet.

Sprint 1 seeds the browser-facing harness with two viewport classes and
layout-debug capture. Later responsive tickets should expand assertions here
instead of creating a parallel browser script.
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from smoke_harness import (
    choose_port,
    import_playwright,
    launch_lenslet,
    stop_process,
    wait_for_health,
)


class ResponsiveGeometryFailure(RuntimeError):
    """Raised when a responsive geometry invariant fails."""


@dataclass(frozen=True)
class Scenario:
    name: str
    width: int
    height: int
    storage: dict[str, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Lenslet responsive layout geometry checks.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7070)
    parser.add_argument("--dataset-dir", type=Path, default=None)
    parser.add_argument("--keep-dataset", action="store_true")
    parser.add_argument("--server-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--browser-timeout-ms", type=float, default=30_000)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("/tmp/lenslet-responsive-geometry.json"),
        help="Path for machine-readable responsive geometry evidence.",
    )
    parser.add_argument(
        "--screenshot-dir",
        type=Path,
        default=Path("/tmp/lenslet-responsive-geometry-screenshots"),
        help="Directory for screenshots captured on scenario failure.",
    )
    return parser.parse_args()


def build_fixture_dataset(root: Path) -> None:
    payload = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAABgAAAASCAYAAABFGc6JAAAAGklEQVR4nGNkYGBg+M+ABzAx"
        "VAlGtWAIBgAEcwEem4pV9wAAAABJRU5ErkJggg=="
    )
    for folder in ("alpha", "beta"):
        for idx in range(4):
            path = root / folder / f"{folder}_{idx:02d}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)


def scenario_storage() -> dict[str, str]:
    return {
        "leftOpen": "1",
        "rightOpen": "1",
        "leftW.folders": "760",
        "leftW.metrics": "760",
        "rightW": "900",
    }


def seed_storage_script(storage: dict[str, str]) -> str:
    return f"""{{
      localStorage.clear();
      const values = {json.dumps(storage)};
      for (const [key, value] of Object.entries(values)) {{
        localStorage.setItem(key, value);
      }}
    }}"""


def collect_snapshot(page: Any, name: str) -> dict[str, Any]:
    snapshot = page.evaluate(
        """(name) => {
          const shell = document.querySelector('.app-shell');
          if (!shell) return { name, missingShell: true };
          const shellStyle = getComputedStyle(shell);
          const doc = document.documentElement;
          const rectFor = (selector) => {
            const el = document.querySelector(selector);
            if (!el) return null;
            const rect = el.getBoundingClientRect();
            return {
              x: rect.x,
              y: rect.y,
              width: rect.width,
              height: rect.height,
              left: rect.left,
              right: rect.right,
              top: rect.top,
              bottom: rect.bottom,
            };
          };
          const toolbarControls = Array.from(document.querySelectorAll('[data-toolbar-control]'))
            .map((el) => {
              const rect = el.getBoundingClientRect();
              const style = getComputedStyle(el);
              return {
                name: el.getAttribute('data-toolbar-control') || el.getAttribute('aria-label') || '',
                ariaHidden: el.getAttribute('aria-hidden'),
                disabled: Boolean(el.disabled),
                visible: style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0,
                rect: {
                  x: rect.x,
                  y: rect.y,
                  width: rect.width,
                  height: rect.height,
                  left: rect.left,
                  right: rect.right,
                  top: rect.top,
                  bottom: rect.bottom,
                },
              };
            });
          return {
            name,
            viewport: { width: window.innerWidth, height: window.innerHeight },
            layout: {
              mode: shell.getAttribute('data-layout-mode'),
              shortHeight: shell.getAttribute('data-short-height'),
              leftSuppressionReason: shell.getAttribute('data-left-suppression-reason'),
              rightSuppressionReason: shell.getAttribute('data-right-suppression-reason'),
              inspectorSuppressionReason: shell.getAttribute('data-inspector-suppression-reason'),
              overlayMode: shell.getAttribute('data-overlay-mode'),
              effectiveLeftWidth: shell.getAttribute('data-effective-left-width'),
              effectiveRightWidth: shell.getAttribute('data-effective-right-width'),
            },
            cssVars: {
              gridLeft: shellStyle.getPropertyValue('--grid-left').trim(),
              gridRight: shellStyle.getPropertyValue('--grid-right').trim(),
              overlayLeft: shellStyle.getPropertyValue('--overlay-left').trim(),
              overlayRight: shellStyle.getPropertyValue('--overlay-right').trim(),
              toolbarHeight: shellStyle.getPropertyValue('--toolbar-h').trim(),
              mobileDrawerHeight: shellStyle.getPropertyValue('--mobile-drawer-h').trim(),
            },
            scroll: {
              scrollWidth: doc.scrollWidth,
              clientWidth: doc.clientWidth,
            },
            rects: {
              shell: rectFor('.app-shell'),
              toolbar: rectFor('.toolbar-shell'),
              leftSidebar: rectFor('.app-left-panel'),
              rightSidebar: rectFor('.app-right-panel'),
              gridShell: rectFor('.grid-shell'),
              overlay: rectFor('[role="dialog"], .z-viewer'),
            },
            toolbarControls,
            storage: {
              leftOpen: localStorage.getItem('leftOpen'),
              rightOpen: localStorage.getItem('rightOpen'),
              leftFoldersWidth: localStorage.getItem('leftW.folders'),
              rightWidth: localStorage.getItem('rightW'),
            },
          };
        }""",
        name,
    )
    if not isinstance(snapshot, dict) or snapshot.get("missingShell"):
        raise ResponsiveGeometryFailure(f"App shell was not available for scenario {name!r}.")
    return snapshot


def assert_no_document_overflow(snapshot: dict[str, Any]) -> None:
    scroll = snapshot.get("scroll")
    if not isinstance(scroll, dict):
        raise ResponsiveGeometryFailure(f"Missing scroll evidence for {snapshot.get('name')!r}.")
    scroll_width = float(scroll.get("scrollWidth", 0))
    client_width = float(scroll.get("clientWidth", 0))
    if scroll_width > client_width + 1:
        raise ResponsiveGeometryFailure(
            f"Document overflow in {snapshot.get('name')}: scrollWidth={scroll_width}, clientWidth={client_width}."
        )


def wait_for_shell(page: Any, timeout_ms: float) -> None:
    page.locator(".app-shell").wait_for(state="visible", timeout=timeout_ms)
    page.locator("[role='grid']").wait_for(state="visible", timeout=timeout_ms)


def run_scenario(page: Any, base_url: str, scenario: Scenario, timeout_ms: float) -> dict[str, Any]:
    page.set_viewport_size({"width": scenario.width, "height": scenario.height})
    page.add_init_script(seed_storage_script(scenario.storage))
    page.goto(base_url, wait_until="domcontentloaded")
    wait_for_shell(page, timeout_ms)
    page.wait_for_timeout(200)
    snapshot = collect_snapshot(page, scenario.name)
    assert_no_document_overflow(snapshot)
    return snapshot


def run_resize_persistence_scenario(page: Any, base_url: str, timeout_ms: float) -> dict[str, Any]:
    page.set_viewport_size({"width": 1440, "height": 900})
    page.add_init_script(seed_storage_script(scenario_storage()))
    page.goto(base_url, wait_until="domcontentloaded")
    wait_for_shell(page, timeout_ms)
    desktop_before = collect_snapshot(page, "resize-persistence-desktop-before")

    page.set_viewport_size({"width": 320, "height": 700})
    page.wait_for_timeout(300)
    phone = collect_snapshot(page, "resize-persistence-phone")

    page.set_viewport_size({"width": 1440, "height": 900})
    page.wait_for_timeout(300)
    desktop_after = collect_snapshot(page, "resize-persistence-desktop-after")

    for snapshot in (desktop_before, phone, desktop_after):
        assert_no_document_overflow(snapshot)

    for snapshot in (desktop_before, phone, desktop_after):
        storage = snapshot.get("storage", {})
        if storage.get("leftOpen") != "1" or storage.get("rightOpen") != "1":
            raise ResponsiveGeometryFailure(
                "Responsive suppression rewrote persisted sidebar preferences during "
                f"{snapshot.get('name')}: storage={storage!r}."
            )
        if storage.get("leftFoldersWidth") != "760" or storage.get("rightWidth") != "900":
            raise ResponsiveGeometryFailure(
                "Responsive suppression rewrote persisted sidebar widths during "
                f"{snapshot.get('name')}: storage={storage!r}."
            )

    if desktop_after.get("layout", {}).get("mode") != "desktop":
        raise ResponsiveGeometryFailure("Desktop layout mode did not restore after resize-up.")
    if desktop_after.get("layout", {}).get("effectiveRightWidth") == "0":
        raise ResponsiveGeometryFailure("Right sidebar did not restore after resize-up.")

    return {
        "name": "resize-persistence",
        "steps": [desktop_before, phone, desktop_after],
    }


def write_evidence(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    dataset_tmp: Path | None = None
    dataset_dir = args.dataset_dir
    if dataset_dir is None:
        dataset_tmp = Path(tempfile.mkdtemp(prefix="lenslet-responsive-fixture-"))
        dataset_dir = dataset_tmp
        build_fixture_dataset(dataset_dir)

    port = choose_port(args.host, args.port)
    base_url = f"http://{args.host}:{port}"
    process = launch_lenslet(dataset_dir, host=args.host, port=port, cwd=repo_root)
    evidence: dict[str, Any] = {
        "baseUrl": base_url,
        "datasetDir": str(dataset_dir),
        "startedAt": time.time(),
        "scenarios": [],
        "failures": [],
    }

    _, _, sync_playwright = import_playwright()
    try:
        wait_for_health(base_url, args.server_timeout_seconds)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                scenarios = [
                    Scenario("desktop-open-oversized", 1440, 900, scenario_storage()),
                    Scenario("phone-open-oversized", 320, 700, scenario_storage()),
                ]
                for scenario in scenarios:
                    context = browser.new_context(viewport={"width": scenario.width, "height": scenario.height})
                    page = context.new_page()
                    try:
                        evidence["scenarios"].append(
                            run_scenario(page, base_url, scenario, args.browser_timeout_ms)
                        )
                    except Exception as exc:
                        args.screenshot_dir.mkdir(parents=True, exist_ok=True)
                        screenshot = args.screenshot_dir / f"{scenario.name}.png"
                        page.screenshot(path=str(screenshot), full_page=True)
                        evidence["failures"].append({
                            "scenario": scenario.name,
                            "error": str(exc),
                            "screenshot": str(screenshot),
                        })
                        raise
                    finally:
                        context.close()

                context = browser.new_context(viewport={"width": 1440, "height": 900})
                page = context.new_page()
                try:
                    evidence["scenarios"].append(
                        run_resize_persistence_scenario(page, base_url, args.browser_timeout_ms)
                    )
                except Exception as exc:
                    args.screenshot_dir.mkdir(parents=True, exist_ok=True)
                    screenshot = args.screenshot_dir / "resize-persistence.png"
                    page.screenshot(path=str(screenshot), full_page=True)
                    evidence["failures"].append({
                        "scenario": "resize-persistence",
                        "error": str(exc),
                        "screenshot": str(screenshot),
                    })
                    raise
                finally:
                    context.close()
            finally:
                browser.close()
    except Exception as exc:
        evidence["error"] = str(exc)
        write_evidence(args.output_json, evidence)
        raise SystemExit(1) from exc
    finally:
        stop_process(process)
        if dataset_tmp is not None and not args.keep_dataset:
            shutil.rmtree(dataset_tmp, ignore_errors=True)

    write_evidence(args.output_json, evidence)
    print(f"Wrote responsive geometry evidence to {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
