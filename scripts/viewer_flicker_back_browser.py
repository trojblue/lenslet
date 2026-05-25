#!/usr/bin/env python3
"""Browser evidence for viewer flicker, pan, click, and Back hit testing."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from PIL import Image, ImageDraw

from smoke_harness import (
    SmokeFailure,
    choose_port,
    import_playwright,
    stop_process,
    wait_for_health,
)


class ViewerProbeFailure(SmokeFailure):
    """Raised when the viewer flicker/Back browser probe cannot collect evidence."""


@dataclass(frozen=True)
class Viewport:
    width: int
    height: int
    name: str


BACK_SWEEP_VIEWPORTS = [
    Viewport(899, 760, "899x760"),
    Viewport(900, 760, "900x760"),
    Viewport(901, 760, "901x760"),
    Viewport(960, 760, "960x760"),
    Viewport(1024, 760, "1024x760"),
    Viewport(1100, 760, "1100x760"),
    Viewport(1179, 760, "1179x760"),
    Viewport(1180, 760, "1180x760"),
    Viewport(1181, 760, "1181x760"),
    Viewport(1240, 760, "1240x760"),
    Viewport(1280, 760, "1280x760"),
    Viewport(1360, 760, "1360x760"),
    Viewport(1440, 760, "1440x760"),
    Viewport(1600, 760, "1600x760"),
    Viewport(1650, 760, "1650x760"),
    Viewport(1650, 1194, "1650x1194"),
    Viewport(1700, 760, "1700x760"),
]

BACK_SAMPLE_X_FRACS = (0.08, 0.27, 0.5, 0.73, 0.92)
BACK_SAMPLE_Y_FRACS = (0.18, 0.5, 0.82)
BACK_CLICK_POINTS = (
    ("top-center", 0.5, 0.18),
    ("center", 0.5, 0.5),
    ("bottom-center", 0.5, 0.82),
)
VIEWER_LOADER_DELAY_MS = 150
DEFAULT_DRAGS = (
    ("default-left", -160, 0),
    ("default-right", 160, 0),
    ("default-up", 0, -160),
    ("default-down", 0, 160),
)
EDGE_DRAGS = (
    ("zoom-left-edge", -260, 0),
    ("zoom-right-edge", 260, 0),
    ("zoom-up-edge", 0, -260),
    ("zoom-down-edge", 0, 260),
)


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
        default=Path("/tmp/lenslet-viewer-flicker-back.json"),
        help="Path for machine-readable probe evidence.",
    )
    return parser.parse_args()


def build_fixture_dataset(root: Path) -> None:
    specs = [
        ("alpha/alpha_00_wide.jpg", (1800, 1200), (48, 90, 140)),
        ("alpha/alpha_01_tall.jpg", (900, 1600), (122, 74, 150)),
        ("alpha/alpha_02_square.jpg", (1200, 1200), (65, 128, 104)),
        ("beta/beta_00_wide.jpg", (1600, 900), (154, 91, 62)),
        ("beta/beta_01_tall.jpg", (800, 1400), (70, 118, 165)),
        ("beta/beta_02_square.jpg", (1000, 1000), (143, 116, 50)),
    ]
    for index, (relative, size, color) in enumerate(specs):
        write_fixture_image(root / relative, size=size, color=color, label=str(index))


def write_fixture_image(path: Path, *, size: tuple[int, int], color: tuple[int, int, int], label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, color=color)
    draw = ImageDraw.Draw(image)
    accent = tuple(min(255, channel + 55) for channel in color)
    draw.rectangle((24, 24, min(size[0] - 24, 420), min(size[1] - 24, 180)), outline=accent, width=8)
    draw.text((48, 52), f"Lenslet probe {label}", fill=(245, 245, 245))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=88)
    path.write_bytes(buffer.getvalue())


def seed_storage_script() -> str:
    values = {
        "leftOpen": "1",
        "rightOpen": "1",
        "leftW.folders": "240",
        "rightW": "220",
        "viewMode": "grid",
        "gridItemSize": "220",
    }
    return f"""{{
      localStorage.clear();
      const values = {json.dumps(values)};
      for (const [key, value] of Object.entries(values)) {{
        localStorage.setItem(key, value);
      }}
    }}"""


def launch_lenslet_with_log(
    source_path: Path,
    *,
    host: str,
    port: int,
    log_path: Path,
) -> subprocess.Popen[Any]:
    command = [
        sys.executable,
        "-m",
        "lenslet.cli",
        str(source_path),
        "--host",
        host,
        "--port",
        str(port),
        "--verbose",
        "--no-skip-indexing",
    ]
    return subprocess.Popen(
        command,
        cwd=str(Path(__file__).resolve().parents[1]),
        stdout=log_path.open("w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        text=True,
    )


def wait_for_shell(page: Any, timeout_ms: float) -> None:
    page.locator(".app-shell").wait_for(state="visible", timeout=timeout_ms)
    page.locator('[role="grid"][aria-label="Gallery"]').wait_for(state="visible", timeout=timeout_ms)
    wait_for_visible_grid_cell_ids(page, 1, timeout_ms)


def visible_grid_cell_ids(page: Any) -> list[str]:
    raw = page.evaluate(
        """() => {
          const cells = Array.from(document.querySelectorAll('[role="gridcell"][id^="cell-"]'))
            .map((el) => {
              const rect = el.getBoundingClientRect();
              return { id: el.id, top: rect.top, left: rect.left, bottom: rect.bottom, right: rect.right };
            })
            .filter((entry) => entry.id && entry.bottom > 0 && entry.right > 0 &&
              entry.top < window.innerHeight && entry.left < window.innerWidth);
          cells.sort((a, b) => (a.top - b.top) || (a.left - b.left));
          return cells.map((entry) => entry.id);
        }"""
    )
    if not isinstance(raw, list):
        raise ViewerProbeFailure("Failed to read visible grid cells.")
    return [item for item in raw if isinstance(item, str) and item.startswith("cell-")]


def wait_for_visible_grid_cell_ids(page: Any, minimum_count: int, timeout_ms: float) -> list[str]:
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    latest: list[str] = []
    while time.monotonic() < deadline:
        latest = visible_grid_cell_ids(page)
        if len(latest) >= minimum_count:
            return latest
        page.wait_for_timeout(120)
    raise ViewerProbeFailure(
        f"Timed out waiting for {minimum_count} visible grid cells. Last visible ids: {latest!r}."
    )


def path_from_cell_id(cell_id: str) -> str:
    if not cell_id.startswith("cell-"):
        raise ViewerProbeFailure(f"Unexpected grid cell id: {cell_id!r}.")
    return unquote(cell_id[5:])


def open_first_viewer(page: Any, timeout_ms: float, *, wait_for_dialog: bool = True) -> tuple[str, str]:
    first_cell_id = wait_for_visible_grid_cell_ids(page, 1, timeout_ms)[0]
    page.locator(f"[id='{first_cell_id}']").dblclick(timeout=timeout_ms)
    if wait_for_dialog:
        page.locator('[role="dialog"][aria-label="Image viewer"]').wait_for(
            state="visible",
            timeout=timeout_ms,
        )
    return path_from_cell_id(first_cell_id), first_cell_id


def wait_for_viewer_ready(page: Any, expected_path: str, timeout_ms: float) -> None:
    page.wait_for_function(
        """(expectedPath) => {
          const dialog = document.querySelector('[role="dialog"][aria-label="Image viewer"]');
          const img = dialog?.querySelector('img[alt="viewer"]');
          if (!(dialog instanceof HTMLElement) || !(img instanceof HTMLImageElement)) return false;
          const style = getComputedStyle(img);
          return dialog.getAttribute('data-current-path') === expectedPath
            && img.getAttribute('data-current-path') === expectedPath
            && img.complete
            && img.naturalWidth > 0
            && Number(style.opacity || '0') > 0.5;
        }""",
        arg=expected_path,
        timeout=timeout_ms,
    )


def wait_for_viewer_path(page: Any, expected_path: str, timeout_ms: float) -> None:
    page.wait_for_function(
        """(expectedPath) => {
          const dialog = document.querySelector('[role="dialog"][aria-label="Image viewer"]');
          return dialog instanceof HTMLElement
            && dialog.getAttribute('data-current-path') === expectedPath;
        }""",
        arg=expected_path,
        timeout=timeout_ms,
    )


def wait_for_back_button(page: Any, timeout_ms: float) -> None:
    page.wait_for_function(
        """() => {
          const button = document.querySelector('[data-toolbar-control="back"]');
          return button instanceof HTMLButtonElement
            && !button.disabled
            && button.getAttribute('aria-hidden') !== 'true';
        }""",
        timeout=timeout_ms,
    )


def close_viewer(page: Any, timeout_ms: float) -> None:
    try:
        if page.locator('[data-toolbar-control="back"]').count() > 0:
            page.locator('[data-toolbar-control="back"]').click(timeout=min(timeout_ms, 5_000))
        else:
            page.keyboard.press("Escape")
        page.locator('[role="dialog"][aria-label="Image viewer"]').wait_for(
            state="detached",
            timeout=min(timeout_ms, 5_000),
        )
    except Exception:
        page.keyboard.press("Escape")
        page.locator('[role="dialog"][aria-label="Image viewer"]').wait_for(
            state="detached",
            timeout=timeout_ms,
        )


def collect_viewer_open_samples(
    page: Any,
    *,
    name: str,
    frames: int,
    interval_ms: int,
) -> dict[str, Any]:
    return page.evaluate(
        """async ({ name, frames, intervalMs }) => {
          const sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));
          const rectPayload = (rect) => ({
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
            left: rect.left,
            right: rect.right,
            top: rect.top,
            bottom: rect.bottom,
          });
          const describeElement = (el) => {
            if (!(el instanceof HTMLElement)) return null;
            const rect = el.getBoundingClientRect();
            const style = getComputedStyle(el);
            return {
              tag: el.tagName,
              id: el.id || null,
              className: typeof el.className === 'string' ? el.className : null,
              ariaLabel: el.getAttribute('aria-label'),
              text: (el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 120),
              opacity: Number(style.opacity || '0'),
              display: style.display,
              visibility: style.visibility,
              pointerEvents: style.pointerEvents,
              transitionDuration: style.transitionDuration,
              transitionProperty: style.transitionProperty,
              rect: rectPayload(rect),
            };
          };
          const elementPayloadVisible = (payload) => (
            payload
            && payload.display !== 'none'
            && payload.visibility !== 'hidden'
            && payload.opacity > 0.01
            && payload.rect.width > 0
            && payload.rect.height > 0
          );
          const imagePayload = (el) => {
            if (!(el instanceof HTMLImageElement)) return null;
            const rect = el.getBoundingClientRect();
            const style = getComputedStyle(el);
            return {
              tag: el.tagName,
              alt: el.getAttribute('alt'),
              src: el.currentSrc || el.src || null,
              currentPath: el.getAttribute('data-current-path'),
              complete: el.complete,
              naturalWidth: el.naturalWidth,
              naturalHeight: el.naturalHeight,
              opacity: Number(style.opacity || '0'),
              display: style.display,
              visibility: style.visibility,
              pointerEvents: style.pointerEvents,
              transform: style.transform,
              transitionDuration: style.transitionDuration,
              transitionProperty: style.transitionProperty,
              rect: rectPayload(rect),
            };
          };
          const backgroundPayloads = (dialog) => {
            if (!(dialog instanceof HTMLElement)) return [];
            return Array.from(dialog.querySelectorAll('*')).flatMap((el) => {
              if (!(el instanceof HTMLElement)) return [];
              const style = getComputedStyle(el);
              if (!style.backgroundImage || style.backgroundImage === 'none') return [];
              const rect = el.getBoundingClientRect();
              if (rect.width <= 0 || rect.height <= 0) return [];
              return [{
                tag: el.tagName,
                className: typeof el.className === 'string' ? el.className : null,
                backgroundImage: style.backgroundImage.slice(0, 120),
                opacity: Number(style.opacity || '0'),
                rect: rectPayload(rect),
              }];
            });
          };
          const read = (frame, startedAt) => {
            const dialog = document.querySelector('[role="dialog"][aria-label="Image viewer"]');
            const images = dialog
              ? Array.from(dialog.querySelectorAll('img')).map(imagePayload).filter(Boolean)
              : [];
            const neutralLoader = describeElement(dialog?.querySelector('[data-viewer-loader="neutral"]'));
            const visibleImages = images.filter((image) => (
              image.display !== 'none'
              && image.visibility !== 'hidden'
              && image.opacity > 0.01
              && image.rect.width > 0
              && image.rect.height > 0
            ));
            const canvases = dialog
              ? Array.from(dialog.querySelectorAll('canvas')).map(describeElement).filter(Boolean)
              : [];
            const pictures = dialog
              ? Array.from(dialog.querySelectorAll('picture')).map(describeElement).filter(Boolean)
              : [];
            const fallback = dialog instanceof HTMLElement
              && (dialog.textContent || '').includes('Loading viewer')
              ? describeElement(dialog)
              : null;
            return {
              frame,
              elapsedMs: Math.round(performance.now() - startedAt),
              dialog: describeElement(dialog),
              dialogCount: document.querySelectorAll('[role="dialog"][aria-label="Image viewer"]').length,
              currentPath: dialog instanceof HTMLElement ? dialog.getAttribute('data-current-path') : null,
              loadingState: dialog instanceof HTMLElement
                ? dialog.getAttribute('data-viewer-loading-state')
                : null,
              neutralLoader,
              neutralLoaderVisible: elementPayloadVisible(neutralLoader),
              fallback,
              thumb: imagePayload(dialog?.querySelector('img[alt="thumb"]')),
              viewer: imagePayload(dialog?.querySelector('img[alt="viewer"]')),
              images,
              visibleImageCount: visibleImages.length,
              visibleImages,
              imageLikeElements: {
                imgCount: images.length,
                canvasCount: canvases.length,
                pictureCount: pictures.length,
                backgroundImages: backgroundPayloads(dialog),
              },
            };
          };
          const startedAt = performance.now();
          const samples = [];
          for (let frame = 0; frame < frames; frame += 1) {
            samples.push(read(frame, startedAt));
            if (frame !== frames - 1) await sleep(intervalMs);
          }
          return { name, frames, intervalMs, samples };
        }""",
        {"name": name, "frames": frames, "intervalMs": interval_ms},
    )


def install_file_delay_route(page: Any, delayed_ms: int) -> None:
    if delayed_ms <= 0:
        return
    page.add_init_script(
        f"""(() => {{
          if (window.__lensletFileDelayInstalled) return;
          window.__lensletFileDelayInstalled = true;
          const delayedMs = {int(delayed_ms)};
          const originalFetch = window.fetch.bind(window);
          window.fetch = (input, init) => {{
            const rawUrl = typeof input === 'string' ? input : input?.url;
            let pathname = '';
            try {{
              pathname = new URL(rawUrl, window.location.href).pathname;
            }} catch {{}}
            if (pathname !== '/file') return originalFetch(input, init);
            return new Promise((resolve) => {{
              window.setTimeout(resolve, delayedMs);
            }}).then(() => originalFetch(input, init));
          }};
        }})()"""
    )


def run_viewer_open_probe(
    context: Any,
    base_url: str,
    *,
    timeout_ms: float,
    frames: int,
    interval_ms: int,
    delayed_file_route_ms: int,
) -> list[dict[str, Any]]:
    scenarios = [
        ("delayed-file-load", delayed_file_route_ms),
        ("normal-fast-load", 0),
    ]
    results: list[dict[str, Any]] = []
    for name, delay_ms in scenarios:
        page = context.new_page()
        page.set_default_timeout(timeout_ms)
        requests: list[str] = []
        page.on(
            "request",
            lambda request: requests.append(request.url)
            if urlparse(request.url).path in ("/file", "/thumb")
            else None,
        )
        install_file_delay_route(page, delay_ms)
        page.add_init_script(seed_storage_script())
        page.set_viewport_size({"width": 1200, "height": 820})
        page.goto(base_url, wait_until="domcontentloaded")
        wait_for_shell(page, timeout_ms)
        opened_path, opened_cell_id = open_first_viewer(page, timeout_ms, wait_for_dialog=False)
        samples = collect_viewer_open_samples(
            page,
            name=name,
            frames=frames,
            interval_ms=interval_ms,
        )
        try:
            wait_for_viewer_ready(page, opened_path, timeout_ms)
        except Exception:
            pass
        settled = read_viewer_state(page)
        results.append(
            {
                "name": name,
                "delayedFileRouteMs": delay_ms,
                "loaderExpected": delay_ms > 0,
                "loaderForbidden": False,
                "openedPath": opened_path,
                "openedCellId": opened_cell_id,
                "samples": samples,
                "settled": settled,
                "requests": requests,
                "riskSummary": summarize_open_samples(samples),
            }
        )
        if is_viewer_open(page):
            close_viewer(page, timeout_ms)
        page.close()
    results.extend(
        run_rapid_navigation_probe(
            context,
            base_url,
            timeout_ms=timeout_ms,
            frames=frames,
            interval_ms=interval_ms,
            delayed_file_route_ms=delayed_file_route_ms,
        )
    )
    return results


def run_rapid_navigation_probe(
    context: Any,
    base_url: str,
    *,
    timeout_ms: float,
    frames: int,
    interval_ms: int,
    delayed_file_route_ms: int,
) -> list[dict[str, Any]]:
    page = context.new_page()
    page.set_default_timeout(timeout_ms)
    requests: list[str] = []
    page.on(
        "request",
        lambda request: requests.append(request.url)
        if urlparse(request.url).path in ("/file", "/thumb")
        else None,
    )
    page.add_init_script(seed_storage_script())
    page.set_viewport_size({"width": 1200, "height": 820})
    install_file_delay_route(page, delayed_file_route_ms)
    page.goto(base_url, wait_until="domcontentloaded")
    wait_for_shell(page, timeout_ms)
    cell_ids = wait_for_visible_grid_cell_ids(page, 4, timeout_ms)
    paths = [path_from_cell_id(cell_id) for cell_id in cell_ids[:4]]
    opened_path, _ = open_first_viewer(page, timeout_ms)
    wait_for_viewer_ready(page, opened_path, timeout_ms)

    results: list[dict[str, Any]] = []
    page.keyboard.press("ArrowRight")
    wait_for_viewer_path(page, paths[1], timeout_ms)
    page.keyboard.press("ArrowRight")
    wait_for_viewer_path(page, paths[2], timeout_ms)
    page.keyboard.press("ArrowRight")
    results.append(
        collect_navigation_samples(
            page,
            name="rapid-next-delayed-file-load",
            expected_path=paths[3],
            opened_cell_id=cell_ids[3],
            timeout_ms=timeout_ms,
            frames=frames,
            interval_ms=interval_ms,
            requests=requests,
            loader_expected=True,
            loader_forbidden=False,
            navigation={
                "from": opened_path,
                "via": [paths[1], paths[2]],
                "to": paths[3],
                "direction": "next",
            },
        )
    )
    page.keyboard.press("ArrowLeft")
    results.append(
        collect_navigation_samples(
            page,
            name="rapid-prev-delayed-file-load",
            expected_path=paths[2],
            opened_cell_id=cell_ids[2],
            timeout_ms=timeout_ms,
            frames=frames,
            interval_ms=interval_ms,
            requests=requests,
            loader_expected=False,
            loader_forbidden=True,
            navigation={
                "from": paths[3],
                "to": paths[2],
                "direction": "previous",
            },
        )
    )
    if is_viewer_open(page):
        close_viewer(page, timeout_ms)
    page.close()
    return results


def collect_navigation_samples(
    page: Any,
    *,
    name: str,
    expected_path: str,
    opened_cell_id: str,
    timeout_ms: float,
    frames: int,
    interval_ms: int,
    requests: list[str],
    loader_expected: bool,
    loader_forbidden: bool,
    navigation: dict[str, Any],
) -> dict[str, Any]:
    wait_for_viewer_path(page, expected_path, timeout_ms)
    samples = collect_viewer_open_samples(
        page,
        name=name,
        frames=frames,
        interval_ms=interval_ms,
    )
    try:
        wait_for_viewer_ready(page, expected_path, timeout_ms)
    except Exception:
        pass
    settled = read_viewer_state(page)
    return {
        "name": name,
        "delayedFileRouteMs": None,
        "loaderExpected": loader_expected,
        "loaderForbidden": loader_forbidden,
        "openedPath": expected_path,
        "openedCellId": opened_cell_id,
        "samples": samples,
        "settled": settled,
        "requests": list(requests),
        "navigation": navigation,
        "riskSummary": summarize_open_samples(samples),
    }


def summarize_open_samples(samples: dict[str, Any]) -> dict[str, Any]:
    frames = samples.get("samples")
    if not isinstance(frames, list):
        return {}
    thumb_observed = False
    fallback_observed = False
    crossfade_observed = False
    duplicate_visible_observed = False
    invisible_full_image_observed = False
    open_fade_class_observed = False
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        thumb = frame.get("thumb")
        viewer = frame.get("viewer")
        dialog = frame.get("dialog")
        if isinstance(thumb, dict):
            thumb_observed = True
            if float(thumb.get("opacity") or 0) > 0.01:
                duplicate_visible_observed = duplicate_visible_observed or frame.get("visibleImageCount", 0) > 1
        if isinstance(frame.get("fallback"), dict):
            fallback_observed = True
        if isinstance(viewer, dict):
            opacity = float(viewer.get("opacity") or 0)
            if 0 < opacity < 0.99:
                crossfade_observed = True
            if opacity <= 0.01:
                invisible_full_image_observed = True
        if isinstance(dialog, dict):
            class_name = str(dialog.get("className") or "")
            open_fade_class_observed = open_fade_class_observed or "transition-opacity" in class_name
    return {
        "thumbObserved": thumb_observed,
        "fallbackObserved": fallback_observed,
        "fullImageCrossfadeObserved": crossfade_observed,
        "duplicateVisibleImageObserved": duplicate_visible_observed,
        "invisibleFullImageObserved": invisible_full_image_observed,
        "openFadeClassObserved": open_fade_class_observed,
    }


def is_viewer_open(page: Any) -> bool:
    return bool(
        page.evaluate(
            """() => Boolean(document.querySelector('[role="dialog"][aria-label="Image viewer"]'))"""
        )
    )


def sample_back_button(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """({ xFracs, yFracs }) => {
          const rectPayload = (rect) => ({
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
            left: rect.left,
            right: rect.right,
            top: rect.top,
            bottom: rect.bottom,
          });
          const stylePayload = (el) => {
            if (!(el instanceof HTMLElement)) return null;
            const style = getComputedStyle(el);
            return {
              pointerEvents: style.pointerEvents,
              zIndex: style.zIndex,
              position: style.position,
              opacity: Number(style.opacity || '0'),
              visibility: style.visibility,
              display: style.display,
            };
          };
          const describe = (el) => {
            if (!(el instanceof HTMLElement)) return null;
            return {
              tag: el.tagName,
              id: el.id || null,
              className: typeof el.className === 'string' ? el.className : null,
              ariaLabel: el.getAttribute('aria-label'),
              dataToolbarControl: el.getAttribute('data-toolbar-control'),
              dataToolbarSlot: el.getAttribute('data-toolbar-slot'),
              role: el.getAttribute('role'),
              text: (el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 80),
              rect: rectPayload(el.getBoundingClientRect()),
              style: stylePayload(el),
            };
          };
          const nearest = (el, selector) => (
            el instanceof HTMLElement ? describe(el.closest(selector)) : null
          );
          const back = document.querySelector('[data-toolbar-control="back"]');
          if (!(back instanceof HTMLElement)) {
            return { missing: true, roleButtonCountByName: 0, points: [] };
          }
          const backRect = back.getBoundingClientRect();
          const backStyle = getComputedStyle(back);
          const points = [];
          for (const yFrac of yFracs) {
            for (const xFrac of xFracs) {
              const x = backRect.left + backRect.width * xFrac;
              const y = backRect.top + backRect.height * yFrac;
              const hit = document.elementFromPoint(x, y);
              points.push({
                xFrac,
                yFrac,
                x,
                y,
                hit: describe(hit),
                resolvesToBack: Boolean(hit && (hit === back || back.contains(hit))),
                nearest: {
                  toolbarControl: nearest(hit, '[data-toolbar-control]'),
                  toolbarSlot: nearest(hit, '[data-toolbar-slot]'),
                  toolbarShell: nearest(hit, '.toolbar-shell'),
                  toolbarLeft: nearest(hit, '.toolbar-left'),
                  toolbarCenter: nearest(hit, '.toolbar-center'),
                  toolbarRight: nearest(hit, '.toolbar-right'),
                  viewerOrDialog: nearest(hit, '[role="dialog"], .z-viewer'),
                },
                backRect: rectPayload(backRect),
                backStyle: {
                  pointerEvents: backStyle.pointerEvents,
                  zIndex: backStyle.zIndex,
                  position: backStyle.position,
                  opacity: Number(backStyle.opacity || '0'),
                  visibility: backStyle.visibility,
                  display: backStyle.display,
                },
              });
            }
          }
          return {
            missing: false,
            rect: rectPayload(backRect),
            ariaLabel: back.getAttribute('aria-label'),
            title: back.getAttribute('title'),
            disabled: Boolean(back.disabled),
            ariaHidden: back.getAttribute('aria-hidden'),
            tabIndex: back.tabIndex,
            display: backStyle.display,
            visibility: backStyle.visibility,
            pointerEvents: backStyle.pointerEvents,
            roleButtonCountByName: Array.from(document.querySelectorAll('button'))
              .filter((el) => el.getAttribute('aria-label') === 'Back to grid').length,
            points,
          };
        }""",
        {"xFracs": list(BACK_SAMPLE_X_FRACS), "yFracs": list(BACK_SAMPLE_Y_FRACS)},
    )


def click_back_point(page: Any, sample: dict[str, Any], label: str, x_frac: float, y_frac: float) -> dict[str, Any]:
    rect = sample.get("rect")
    if not isinstance(rect, dict):
        return {"label": label, "closed": False, "error": "missing back rect"}
    x = float(rect["left"]) + float(rect["width"]) * x_frac
    y = float(rect["top"]) + float(rect["height"]) * y_frac
    page.mouse.click(x, y)
    closed = wait_for_viewer_closed(page, 1_500)
    return {"label": label, "x": x, "y": y, "closed": closed}


def wait_for_viewer_closed(page: Any, timeout_ms: float) -> bool:
    try:
        page.locator('[role="dialog"][aria-label="Image viewer"]').wait_for(
            state="detached",
            timeout=timeout_ms,
        )
        return True
    except Exception:
        return False


def run_back_probe(context: Any, base_url: str, *, timeout_ms: float) -> list[dict[str, Any]]:
    page = context.new_page()
    page.set_default_timeout(timeout_ms)
    page.add_init_script(seed_storage_script())
    results: list[dict[str, Any]] = []
    for viewport in BACK_SWEEP_VIEWPORTS:
        page.set_viewport_size({"width": viewport.width, "height": viewport.height})
        page.goto(base_url, wait_until="domcontentloaded")
        wait_for_shell(page, timeout_ms)
        opened_path, _ = open_first_viewer(page, timeout_ms)
        wait_for_back_button(page, timeout_ms)
        sample = sample_back_button(page)
        click_results: list[dict[str, Any]] = []
        for index, (label, x_frac, y_frac) in enumerate(BACK_CLICK_POINTS):
            if not is_viewer_open(page):
                open_first_viewer(page, timeout_ms)
                wait_for_back_button(page, timeout_ms)
            current_sample = sample_back_button(page)
            click_result = click_back_point(page, current_sample, label, x_frac, y_frac)
            click_results.append(click_result)
            if not click_result.get("closed"):
                page.keyboard.press("Escape")
                wait_for_viewer_closed(page, timeout_ms)
            if index != len(BACK_CLICK_POINTS) - 1:
                wait_for_shell(page, timeout_ms)
        failed_points = [
            point
            for point in sample.get("points", [])
            if isinstance(point, dict) and not point.get("resolvesToBack")
        ]
        results.append(
            {
                "name": viewport.name,
                "width": viewport.width,
                "height": viewport.height,
                "openedPath": opened_path,
                "sample": sample,
                "clicks": click_results,
                "failedPointCount": len(failed_points),
                "failedPoints": failed_points,
            }
        )
    page.close()
    return results


def read_viewer_state(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const rectPayload = (rect) => ({
            x: rect.x,
            y: rect.y,
            width: rect.width,
            height: rect.height,
            left: rect.left,
            right: rect.right,
            top: rect.top,
            bottom: rect.bottom,
          });
          const dialog = document.querySelector('[role="dialog"][aria-label="Image viewer"]');
          const image = dialog?.querySelector('img[alt="viewer"]');
          if (!(dialog instanceof HTMLElement) || !(image instanceof HTMLImageElement)) {
            return { missing: true };
          }
          const loader = dialog.querySelector('[data-viewer-loader="neutral"]');
          const loaderStyle = loader instanceof HTMLElement ? getComputedStyle(loader) : null;
          const style = getComputedStyle(image);
          let matrix = null;
          try {
            const parsed = new DOMMatrixReadOnly(style.transform === 'none' ? undefined : style.transform);
            matrix = { a: parsed.a, b: parsed.b, c: parsed.c, d: parsed.d, e: parsed.e, f: parsed.f };
          } catch {}
          return {
            missing: false,
            dialogPath: dialog.getAttribute('data-current-path'),
            loadingState: dialog.getAttribute('data-viewer-loading-state'),
            imagePath: image.getAttribute('data-current-path'),
            complete: image.complete,
            naturalWidth: image.naturalWidth,
            naturalHeight: image.naturalHeight,
            opacity: Number(style.opacity || '0'),
            neutralLoaderVisible: Boolean(loader instanceof HTMLElement
              && loaderStyle
              && loaderStyle.display !== 'none'
              && loaderStyle.visibility !== 'hidden'
              && Number(loaderStyle.opacity || '0') > 0.01
              && loader.getBoundingClientRect().width > 0
              && loader.getBoundingClientRect().height > 0),
            transform: style.transform,
            matrix,
            dialogRect: rectPayload(dialog.getBoundingClientRect()),
            imageRect: rectPayload(image.getBoundingClientRect()),
          };
        }"""
    )


def drag_viewer_image(page: Any, dx: int, dy: int) -> dict[str, Any]:
    before = read_viewer_state(page)
    if before.get("missing"):
        return {"before": before, "after": before, "changed": False, "error": "missing viewer image"}
    image_rect = before["imageRect"]
    dialog_rect = before["dialogRect"]
    start_x = min(
        max(float(image_rect["left"]) + float(image_rect["width"]) / 2, float(dialog_rect["left"]) + 8),
        float(dialog_rect["right"]) - 8,
    )
    start_y = min(
        max(float(image_rect["top"]) + float(image_rect["height"]) / 2, float(dialog_rect["top"]) + 8),
        float(dialog_rect["bottom"]) - 8,
    )
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(start_x + dx, start_y + dy, steps=10)
    page.mouse.up()
    page.wait_for_timeout(80)
    after = read_viewer_state(page)
    changed = transform_changed(before, after)
    return {
        "dx": dx,
        "dy": dy,
        "start": {"x": start_x, "y": start_y},
        "before": before,
        "after": after,
        "changed": changed,
    }


def transform_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    before_matrix = before.get("matrix")
    after_matrix = after.get("matrix")
    if not isinstance(before_matrix, dict) or not isinstance(after_matrix, dict):
        return before.get("transform") != after.get("transform")
    return (
        abs(float(before_matrix.get("e", 0)) - float(after_matrix.get("e", 0))) > 0.5
        or abs(float(before_matrix.get("f", 0)) - float(after_matrix.get("f", 0))) > 0.5
        or abs(float(before_matrix.get("a", 0)) - float(after_matrix.get("a", 0))) > 0.001
        or abs(float(before_matrix.get("d", 0)) - float(after_matrix.get("d", 0))) > 0.001
    )


def zoom_viewer_with_wheel(page: Any) -> dict[str, Any]:
    before = read_viewer_state(page)
    if before.get("missing"):
        return {"before": before, "after": before, "steps": 0}
    rect = before["imageRect"]
    x = float(rect["left"]) + float(rect["width"]) / 2
    y = float(rect["top"]) + float(rect["height"]) / 2
    page.mouse.move(x, y)
    for _ in range(5):
        page.mouse.wheel(0, -420)
        page.wait_for_timeout(40)
    return {"before": before, "after": read_viewer_state(page), "steps": 5}


def run_default_pan_probe(page: Any, base_url: str, timeout_ms: float) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for name, dx, dy in DEFAULT_DRAGS:
        page.goto(base_url, wait_until="domcontentloaded")
        wait_for_shell(page, timeout_ms)
        opened_path, _ = open_first_viewer(page, timeout_ms)
        wait_for_viewer_ready(page, opened_path, timeout_ms)
        drag = drag_viewer_image(page, dx, dy)
        results.append({"name": name, "openedPath": opened_path, "drag": drag})
        close_viewer(page, timeout_ms)
    return results


def run_zoom_edge_probe(page: Any, base_url: str, timeout_ms: float) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for name, dx, dy in EDGE_DRAGS:
        page.goto(base_url, wait_until="domcontentloaded")
        wait_for_shell(page, timeout_ms)
        opened_path, _ = open_first_viewer(page, timeout_ms)
        wait_for_viewer_ready(page, opened_path, timeout_ms)
        zoom = zoom_viewer_with_wheel(page)
        approach_drags = [drag_viewer_image(page, dx, dy) for _ in range(5)]
        before_additional = read_viewer_state(page)
        additional = drag_viewer_image(page, dx, dy)
        results.append(
            {
                "name": name,
                "openedPath": opened_path,
                "zoom": zoom,
                "approachDrags": approach_drags,
                "beforeAdditional": before_additional,
                "additionalDrag": additional,
                "changedBeyondOldClamp": bool(additional.get("changed")),
            }
        )
        close_viewer(page, timeout_ms)
    return results


def choose_background_point(page: Any) -> dict[str, float]:
    point = page.evaluate(
        """() => {
          const dialog = document.querySelector('[role="dialog"][aria-label="Image viewer"]');
          const image = dialog?.querySelector('img[alt="viewer"]');
          if (!(dialog instanceof HTMLElement)) return null;
          const d = dialog.getBoundingClientRect();
          const candidates = [
            { x: d.left + 18, y: d.top + 18 },
            { x: d.right - 18, y: d.top + 18 },
            { x: d.left + 18, y: d.bottom - 18 },
            { x: d.right - 18, y: d.bottom - 18 },
            { x: d.left + d.width / 2, y: d.bottom - 22 },
          ];
          const inImage = (candidate) => {
            if (!(image instanceof HTMLImageElement)) return false;
            const r = image.getBoundingClientRect();
            return candidate.x >= r.left && candidate.x <= r.right &&
              candidate.y >= r.top && candidate.y <= r.bottom;
          };
          return candidates.find((candidate) => !inImage(candidate)) || candidates[0];
        }"""
    )
    if not isinstance(point, dict):
        raise ViewerProbeFailure("Could not choose a viewer background point.")
    return {"x": float(point["x"]), "y": float(point["y"])}


def choose_image_point(page: Any) -> dict[str, float]:
    point = page.evaluate(
        """() => {
          const image = document.querySelector('[role="dialog"][aria-label="Image viewer"] img[alt="viewer"]');
          if (!(image instanceof HTMLImageElement)) return null;
          const rect = image.getBoundingClientRect();
          return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
        }"""
    )
    if not isinstance(point, dict):
        raise ViewerProbeFailure("Could not choose a viewer image point.")
    return {"x": float(point["x"]), "y": float(point["y"])}


def run_click_probe(page: Any, base_url: str, timeout_ms: float) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for name, point_fn, click_count in (
        ("singleClickImage", choose_image_point, 1),
        ("singleClickBackground", choose_background_point, 1),
        ("doubleClickImage", choose_image_point, 2),
        ("doubleClickBackground", choose_background_point, 2),
    ):
        page.goto(base_url, wait_until="domcontentloaded")
        wait_for_shell(page, timeout_ms)
        opened_path, _ = open_first_viewer(page, timeout_ms)
        wait_for_viewer_ready(page, opened_path, timeout_ms)
        point = point_fn(page)
        if click_count == 1:
            page.mouse.click(point["x"], point["y"])
        else:
            page.mouse.dblclick(point["x"], point["y"])
        closed = wait_for_viewer_closed(page, 900)
        results[name] = {
            "openedPath": opened_path,
            "point": point,
            "closed": closed,
        }
        if not closed:
            close_viewer(page, timeout_ms)
    return results


def run_interactions_probe(context: Any, base_url: str, *, timeout_ms: float) -> dict[str, Any]:
    page = context.new_page()
    page.set_default_timeout(timeout_ms)
    page.add_init_script(seed_storage_script())
    page.set_viewport_size({"width": 1200, "height": 820})
    result = {
        "defaultFitPan": run_default_pan_probe(page, base_url, timeout_ms),
        "zoomEdgePan": run_zoom_edge_probe(page, base_url, timeout_ms),
        "clicks": run_click_probe(page, base_url, timeout_ms),
    }
    page.close()
    return result


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
                    timeout_ms=args.browser_timeout_ms,
                    frames=args.open_sample_frames,
                    interval_ms=args.open_sample_interval_ms,
                    delayed_file_route_ms=args.delayed_file_route_ms,
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


def viewer_acceptance_failures(raw_scenarios: Any) -> list[str]:
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        return ["viewer: missing viewer-open scenarios"]

    failures: list[str] = []
    for scenario in raw_scenarios:
        if not isinstance(scenario, dict):
            failures.append("viewer: malformed viewer-open scenario")
            continue
        name = str(scenario.get("name") or "<unnamed>")
        summary = scenario.get("riskSummary")
        if not isinstance(summary, dict):
            failures.append(f"viewer:{name}: missing risk summary")
            continue
        for key in (
            "thumbObserved",
            "fallbackObserved",
            "fullImageCrossfadeObserved",
            "duplicateVisibleImageObserved",
            "openFadeClassObserved",
        ):
            if summary.get(key):
                failures.append(f"viewer:{name}: {key} is still true")
        if scenario.get("loaderExpected") and not delayed_loader_observed(scenario):
            failures.append(f"viewer:{name}: delayed neutral loader was not observed")
        if scenario.get("loaderForbidden") and loader_observed(scenario):
            failures.append(f"viewer:{name}: neutral loader appeared in loader-forbidden scenario")
        failures.extend(viewer_image_like_failures(name, scenario, scenario.get("openedPath")))

        settled = scenario.get("settled")
        opened_path = scenario.get("openedPath")
        if not isinstance(settled, dict) or settled.get("missing"):
            failures.append(f"viewer:{name}: settled full image is missing")
            continue
        if settled.get("dialogPath") != opened_path or settled.get("imagePath") != opened_path:
            failures.append(
                f"viewer:{name}: settled path mismatch "
                f"dialog={settled.get('dialogPath')!r} image={settled.get('imagePath')!r} "
                f"opened={opened_path!r}"
            )
        if float(settled.get("opacity") or 0) <= 0.5:
            failures.append(f"viewer:{name}: settled full image is not visibly ready")
        if settled.get("loadingState") != "ready":
            failures.append(f"viewer:{name}: settled loading state is not ready")
        if settled.get("neutralLoaderVisible"):
            failures.append(f"viewer:{name}: neutral loader remained visible after readiness")
    return failures


def viewer_image_like_failures(name: str, scenario: dict[str, Any], opened_path: Any) -> list[str]:
    samples = (scenario.get("samples") or {}).get("samples")
    if not isinstance(samples, list) or not samples:
        return [f"viewer:{name}: missing open samples"]

    failures: list[str] = []
    for frame in samples:
        if not isinstance(frame, dict):
            continue
        frame_id = frame.get("frame")
        elapsed_ms = int(frame.get("elapsedMs") or 0)
        if elapsed_ms < VIEWER_LOADER_DELAY_MS - 10 and frame.get("loadingState") == "loading":
            failures.append(
                f"viewer:{name}: frame {frame_id}: neutral loader appeared before delay "
                f"({elapsed_ms}ms)"
            )
        if frame.get("loadingState") == "loading" and not frame.get("neutralLoaderVisible"):
            failures.append(f"viewer:{name}: frame {frame_id}: loading state has no visible neutral loader")
        visible_images = frame.get("visibleImages")
        if not isinstance(visible_images, list):
            failures.append(f"viewer:{name}: frame {frame_id}: missing visible image list")
            continue
        for image in visible_images:
            if not isinstance(image, dict):
                failures.append(f"viewer:{name}: frame {frame_id}: malformed visible image")
                continue
            if image.get("alt") != "viewer" or image.get("currentPath") != opened_path:
                failures.append(
                    f"viewer:{name}: frame {frame_id}: visible non-active image "
                    f"alt={image.get('alt')!r} path={image.get('currentPath')!r}"
                )

        image_like = frame.get("imageLikeElements")
        if not isinstance(image_like, dict):
            failures.append(f"viewer:{name}: frame {frame_id}: missing image-like element scan")
            continue
        for key in ("canvasCount", "pictureCount"):
            if int(image_like.get(key) or 0) > 0:
                failures.append(f"viewer:{name}: frame {frame_id}: {key} is nonzero")
        backgrounds = image_like.get("backgroundImages")
        if isinstance(backgrounds, list):
            visible_backgrounds = [item for item in backgrounds if visible_element_payload(item)]
            if visible_backgrounds:
                failures.append(
                    f"viewer:{name}: frame {frame_id}: visible background-image placeholder count "
                    f"{len(visible_backgrounds)}"
                )
    return failures


def delayed_loader_observed(scenario: dict[str, Any]) -> bool:
    samples = (scenario.get("samples") or {}).get("samples")
    if not isinstance(samples, list):
        return False
    for frame in samples:
        if not isinstance(frame, dict):
            continue
        elapsed_ms = int(frame.get("elapsedMs") or 0)
        if (
            elapsed_ms >= VIEWER_LOADER_DELAY_MS - 10
            and frame.get("loadingState") == "loading"
            and frame.get("neutralLoaderVisible")
        ):
            return True
    return False


def loader_observed(scenario: dict[str, Any]) -> bool:
    samples = (scenario.get("samples") or {}).get("samples")
    if not isinstance(samples, list):
        return False
    return any(
        isinstance(frame, dict)
        and (
            frame.get("loadingState") == "loading"
            or bool(frame.get("neutralLoaderVisible"))
        )
        for frame in samples
    )


def visible_element_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    rect = payload.get("rect")
    return (
        isinstance(rect, dict)
        and float(rect.get("width") or 0) > 0
        and float(rect.get("height") or 0) > 0
        and float(payload.get("opacity") or 0) > 0.01
        and payload.get("display") != "none"
        and payload.get("visibility") != "hidden"
    )


def back_acceptance_failures(raw_scenarios: Any) -> list[str]:
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        return ["back: missing Back hit-target scenarios"]

    failures: list[str] = []
    for scenario in raw_scenarios:
        if not isinstance(scenario, dict):
            failures.append("back: malformed Back scenario")
            continue
        name = str(scenario.get("name") or "<unnamed>")
        sample = scenario.get("sample")
        if not isinstance(sample, dict) or sample.get("missing"):
            failures.append(f"back:{name}: missing Back sample")
            continue
        points = sample.get("points")
        expected_point_count = len(BACK_SAMPLE_X_FRACS) * len(BACK_SAMPLE_Y_FRACS)
        if not isinstance(points, list) or len(points) != expected_point_count:
            failures.append(f"back:{name}: expected {expected_point_count} sampled points")
        else:
            failed_points = [point for point in points if not point.get("resolvesToBack")]
            if failed_points:
                failures.append(
                    f"back:{name}: {len(failed_points)} sampled points do not resolve to Back"
                )

        clicks = scenario.get("clicks")
        expected_click_labels = {label for label, _, _ in BACK_CLICK_POINTS}
        if not isinstance(clicks, list):
            failures.append(f"back:{name}: missing click results")
            continue
        click_labels = {click.get("label") for click in clicks if isinstance(click, dict)}
        missing_clicks = sorted(expected_click_labels - click_labels)
        if missing_clicks:
            failures.append(f"back:{name}: missing click labels {missing_clicks}")
        for click in clicks:
            if not isinstance(click, dict):
                failures.append(f"back:{name}: malformed click result")
            elif not click.get("closed"):
                failures.append(f"back:{name}: click {click.get('label')!r} did not close viewer")
    return failures


def interactions_acceptance_failures(raw_scenarios: Any) -> list[str]:
    if not isinstance(raw_scenarios, dict):
        return ["interactions: missing interaction scenarios"]

    failures: list[str] = []
    failures.extend(
        transform_probe_failures(
            raw_scenarios.get("defaultFitPan"),
            expected_names={name for name, _, _ in DEFAULT_DRAGS},
            context="default-fit drag",
        )
    )
    failures.extend(
        transform_probe_failures(
            raw_scenarios.get("zoomEdgePan"),
            expected_names={name for name, _, _ in EDGE_DRAGS},
            context="edge drag",
            drag_key="additionalDrag",
        )
    )

    clicks = raw_scenarios.get("clicks")
    if not isinstance(clicks, dict):
        failures.append("interactions: missing click scenarios")
        return failures

    for name in ("singleClickImage", "singleClickBackground"):
        if name not in clicks:
            failures.append(f"interactions:{name}: missing click result")
        elif clicks.get(name, {}).get("closed"):
            failures.append(f"interactions:{name}: single click closed viewer")
    for name in ("doubleClickImage", "doubleClickBackground"):
        if name not in clicks:
            failures.append(f"interactions:{name}: missing click result")
        elif not clicks.get(name, {}).get("closed"):
            failures.append(f"interactions:{name}: double click did not close viewer")
    return failures


def transform_probe_failures(
    raw_items: Any,
    *,
    expected_names: set[str],
    context: str,
    drag_key: str = "drag",
) -> list[str]:
    if not isinstance(raw_items, list) or not raw_items:
        return [f"interactions: missing {context} scenarios"]

    failures: list[str] = []
    by_name = {item.get("name"): item for item in raw_items if isinstance(item, dict)}
    missing = sorted(expected_names - set(by_name))
    if missing:
        failures.append(f"interactions: missing {context} scenarios {missing}")

    for name in sorted(expected_names & set(by_name)):
        item = by_name[name]
        drag = item.get(drag_key)
        if not isinstance(drag, dict):
            failures.append(f"interactions:{name}: missing {drag_key} result")
            continue
        failures.extend(drag_acceptance_failures(name, drag, context))
    return failures


def drag_acceptance_failures(name: str, drag: dict[str, Any], context: str) -> list[str]:
    failures: list[str] = []
    if not drag.get("changed"):
        failures.append(f"interactions:{name}: {context} did not move")

    before = drag.get("before")
    after = drag.get("after")
    dx = float(drag.get("dx") or 0)
    dy = float(drag.get("dy") or 0)
    before_matrix = before.get("matrix") if isinstance(before, dict) else None
    after_matrix = after.get("matrix") if isinstance(after, dict) else None
    if not isinstance(before_matrix, dict) or not isinstance(after_matrix, dict):
        failures.append(f"interactions:{name}: missing transform matrices")
        return failures

    delta_x = float(after_matrix.get("e") or 0) - float(before_matrix.get("e") or 0)
    delta_y = float(after_matrix.get("f") or 0) - float(before_matrix.get("f") or 0)
    if abs(dx) >= abs(dy):
        if abs(delta_x) <= 0.5 or (dx < 0 and delta_x >= 0) or (dx > 0 and delta_x <= 0):
            failures.append(f"interactions:{name}: x movement {delta_x:.2f} does not follow drag {dx:.2f}")
    else:
        if abs(delta_y) <= 0.5 or (dy < 0 and delta_y >= 0) or (dy > 0 and delta_y <= 0):
            failures.append(f"interactions:{name}: y movement {delta_y:.2f} does not follow drag {dy:.2f}")

    if not image_still_recoverable(after):
        failures.append(f"interactions:{name}: image moved outside recoverable viewer bounds")
    return failures


def image_still_recoverable(state: Any) -> bool:
    if not isinstance(state, dict):
        return False
    image_rect = state.get("imageRect")
    dialog_rect = state.get("dialogRect")
    if not isinstance(image_rect, dict) or not isinstance(dialog_rect, dict):
        return False
    left = max(float(image_rect.get("left") or 0), float(dialog_rect.get("left") or 0))
    right = min(float(image_rect.get("right") or 0), float(dialog_rect.get("right") or 0))
    top = max(float(image_rect.get("top") or 0), float(dialog_rect.get("top") or 0))
    bottom = min(float(image_rect.get("bottom") or 0), float(dialog_rect.get("bottom") or 0))
    return (right - left) >= 24 and (bottom - top) >= 24


def read_log_tail(path: Path, lines: int = 80) -> str:
    try:
        return "\n".join(path.read_text(encoding="utf-8").splitlines()[-lines:])
    except Exception:
        return "<unavailable>"


def main() -> int:
    args = parse_args()
    cleanup_dataset = False
    if args.dataset_dir is None:
        dataset_dir = Path(tempfile.mkdtemp(prefix="lenslet-viewer-probe-")).resolve()
        build_fixture_dataset(dataset_dir)
        cleanup_dataset = not args.keep_dataset
    else:
        dataset_dir = args.dataset_dir.resolve()
        if not dataset_dir.exists():
            raise SystemExit(f"Dataset directory does not exist: {dataset_dir}")

    port = choose_port(args.host, args.port)
    base_url = f"http://{args.host}:{port}"
    log_file = tempfile.NamedTemporaryFile(prefix="lenslet-viewer-probe-server-", suffix=".log", delete=False)
    log_path = Path(log_file.name)
    log_file.close()

    process = launch_lenslet_with_log(dataset_dir, host=args.host, port=port, log_path=log_path)
    summary: dict[str, Any] = {
        "status": "running",
        "mode": args.mode,
        "baseUrl": base_url,
        "datasetDir": str(dataset_dir),
        "serverLog": str(log_path),
        "backSweepViewports": [
            {"name": item.name, "width": item.width, "height": item.height}
            for item in BACK_SWEEP_VIEWPORTS
        ],
        "delayedFileRouteMs": args.delayed_file_route_ms,
        "scenarios": {},
        "warnings": [],
    }
    try:
        summary["initialHealth"] = wait_for_health(base_url, args.server_timeout_seconds)
        if process.poll() is not None:
            raise ViewerProbeFailure(f"Lenslet exited unexpectedly with code {process.returncode}.")
        summary["scenarios"] = run_browser_checks(base_url, args)
        acceptance_failures = acceptance_failures_for_mode(args.mode, summary["scenarios"])
        summary["acceptance"] = {
            "mode": args.mode,
            "failures": acceptance_failures,
        }
        summary["finalHealth"] = wait_for_health(base_url, args.server_timeout_seconds)
        if acceptance_failures:
            raise ViewerProbeFailure(
                "acceptance checks failed: " + "; ".join(acceptance_failures[:8])
            )
        summary["status"] = "passed"
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0
    except Exception as exc:
        summary["status"] = "failed"
        summary["error"] = str(exc)
        summary["serverLogTail"] = read_log_tail(log_path)
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2), file=sys.stderr)
        return 1
    finally:
        stop_process(process)
        if cleanup_dataset:
            shutil.rmtree(dataset_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
