from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import unquote

from scripts.browser.viewer_probe.config import ViewerProbeFailure

MS_PER_SECOND = 1000.0
VIEWER_DIALOG_SELECTOR = '[role="dialog"][aria-label="Image viewer"]'


def _playwright_error_types() -> tuple[type[BaseException], ...]:
    try:
        from playwright.sync_api import Error as PlaywrightError
    except ImportError:
        return (TimeoutError, RuntimeError)
    return (PlaywrightError, RuntimeError)


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
    deadline = time.monotonic() + (timeout_ms / MS_PER_SECOND)
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
        dialog = page.locator(VIEWER_DIALOG_SELECTOR)
        dialog.wait_for(
            state="visible",
            timeout=timeout_ms,
        )
        dialog.focus()
    return path_from_cell_id(first_cell_id), first_cell_id


def wait_for_viewer_ready(page: Any, expected_path: str, timeout_ms: float) -> None:
    page.wait_for_function(
        """(expectedPath) => {
          const dialog = document.querySelector('[role="dialog"][aria-label="Image viewer"]');
          const img = dialog?.querySelector('img[data-viewer-image="full"]');
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
    error_types = _playwright_error_types()
    try:
        if page.locator('[data-toolbar-control="back"]').count() > 0:
            page.locator('[data-toolbar-control="back"]').click(timeout=min(timeout_ms, 5_000))
        else:
            page.keyboard.press("Escape")
        page.locator(VIEWER_DIALOG_SELECTOR).wait_for(
            state="detached",
            timeout=min(timeout_ms, 5_000),
        )
    except error_types:
        page.keyboard.press("Escape")
        page.locator(VIEWER_DIALOG_SELECTOR).wait_for(
            state="detached",
            timeout=timeout_ms,
        )


def is_viewer_open(page: Any) -> bool:
    return bool(
        page.evaluate(
            """() => Boolean(document.querySelector('[role="dialog"][aria-label="Image viewer"]'))"""
        )
    )


def wait_for_viewer_closed(page: Any, timeout_ms: float) -> bool:
    try:
        page.locator(VIEWER_DIALOG_SELECTOR).wait_for(
            state="detached",
            timeout=timeout_ms,
        )
        return True
    except _playwright_error_types():
        return False


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
          const image = dialog?.querySelector('img[data-viewer-image="full"]');
          if (!(dialog instanceof HTMLElement) || !(image instanceof HTMLImageElement)) {
            return { missing: true };
          }
          const dialogRect = dialog.getBoundingClientRect();
          const imageRect = image.getBoundingClientRect();
          const axisBounds = (containerSize, renderedSize) => {
            const slack = Math.min(96, Math.max(48, containerSize * 0.10), renderedSize * 0.25);
            if (renderedSize <= containerSize) {
              const centered = (containerSize - renderedSize) / 2;
              return {
                strictMin: centered,
                strictMax: centered,
                slackMin: centered - slack,
                slackMax: centered + slack,
                slack,
              };
            }
            const strictMin = containerSize - renderedSize;
            const strictMax = 0;
            return {
              strictMin,
              strictMax,
              slackMin: strictMin - slack,
              slackMax: strictMax + slack,
              slack,
            };
          };
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
            transformBounds: {
              x: axisBounds(dialogRect.width, imageRect.width),
              y: axisBounds(dialogRect.height, imageRect.height),
            },
            dialogRect: rectPayload(dialogRect),
            imageRect: rectPayload(imageRect),
          };
        }"""
    )
