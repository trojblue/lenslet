"""Painted-frame evidence for decoded hover-preview presentation."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from scripts.browser.gui_jitter.shared import wait_for_grid

GRID_STORAGE_SCRIPT = """() => {
  localStorage.setItem('leftOpen', '1');
  localStorage.setItem('rightOpen', '1');
  localStorage.setItem('viewMode', 'grid');
}"""


def hover_preview_case_violations(
    name: str,
    frames: list[dict[str, Any]],
    *,
    expected_path: str,
    expected_rgb: list[int] | None = None,
    outcome: str = "ready",
) -> list[str]:
    visible = [frame for frame in frames if frame.get("surfaceVisible")]
    if outcome == "cancelled":
        retained = [
            frame for frame in frames
            if frame.get("path") is not None
            or frame.get("state") is not None
            or frame.get("image") is not None
        ]
        return [f"hover {name}: orphan preview node remained"] if retained else []
    if not visible:
        return [f"hover {name}: no terminal preview became visible"]

    violations: list[str] = []
    for frame in visible:
        if frame.get("path") != expected_path:
            violations.append(f"hover {name}: visible preview belonged to {frame.get('path')!r}")
        if outcome == "error":
            if frame.get("state") != "error":
                violations.append(f"hover {name}: invalid resource became visible before terminal error")
            if frame.get("image") is not None:
                violations.append(f"hover {name}: terminal error retained a media node")
            continue
        image = frame.get("image")
        if (
            frame.get("state") != "ready"
            or not isinstance(image, dict)
            or not image.get("complete")
            or int(image.get("naturalWidth") or 0) <= 0
            or not image.get("visible")
            or not isinstance(image.get("rgb"), list)
        ):
            violations.append(f"hover {name}: visible portal did not own decoded target pixels")
        elif expected_rgb is None or not _rgb_matches(image["rgb"], expected_rgb):
            violations.append(f"hover {name}: visible pixels did not match {expected_path!r}")
    if outcome == "error" and not _is_terminal_error_frame(frames[-1]):
        violations.append(f"hover {name}: corrupt target did not remain a terminal error")
    return list(dict.fromkeys(violations))


def _is_terminal_error_frame(frame: dict[str, Any]) -> bool:
    return bool(
        frame.get("surfaceVisible")
        and frame.get("state") == "error"
        and frame.get("image") is None
    )


def _rgb_matches(actual: list[Any], expected: list[int], tolerance: int = 3) -> bool:
    return len(actual) == 3 and all(
        isinstance(value, (int, float)) and abs(float(value) - target) <= tolerance
        for value, target in zip(actual, expected)
    )


def fixture_rgb(path: str) -> list[int] | None:
    name = path.rsplit("/", 1)[-1]
    png_colors = {
        "quick_00_meta.png": [72, 36, 120],
        "quick_01_meta.png": [36, 126, 74],
        "quick_02_plain.png": [148, 72, 34],
        "quick_03_meta.png": [38, 96, 154],
    }
    if name in png_colors:
        return png_colors[name]
    if name.startswith("scope_") and name.endswith(".jpg"):
        try:
            index = int(name.removeprefix("scope_").removesuffix(".jpg"))
        except ValueError:
            return None
        return [160 + index * 30, 64, 48 + index * 40]
    if name.startswith("sample_") and name.endswith(".jpg"):
        try:
            index = int(name.removeprefix("sample_").removesuffix(".jpg"))
        except ValueError:
            return None
        return [32 + index * 12, 72 + index * 5, 144 - index * 4]
    return None


def _cell_id(path: str) -> str:
    return f"cell-{quote(path, safe='')}"


def _visible_paths(page: Any, count: int) -> list[str]:
    page.wait_for_function(
        "count => document.querySelectorAll('[role=gridcell][id^=cell-]').length >= count",
        arg=count,
    )
    raw = page.locator('[role="gridcell"][id^="cell-"]').evaluate_all(
        "nodes => nodes.slice(0, 6).map(node => decodeURIComponent(node.id.slice(5)))"
    )
    return [value for value in raw if isinstance(value, str)][:count]


def _hover(page: Any, path: str) -> None:
    page.locator(f"[id='{_cell_id(path)}'] .grid-item-preview-hotspot").hover()


def _leave_preview(page: Any) -> None:
    page.locator('button[aria-label="Sort and layout"]').hover()


def _collect_frames(page: Any, duration_ms: int) -> list[dict[str, Any]]:
    raw = page.evaluate(
        """async durationMs => {
          const frames = [];
          const startedAt = performance.now();
          const samplePixel = image => {
            if (!(image instanceof HTMLImageElement) || !image.complete || image.naturalWidth <= 0) return null;
            try {
              const canvas = document.createElement('canvas');
              canvas.width = 1;
              canvas.height = 1;
              const context = canvas.getContext('2d', { willReadFrequently: true });
              context?.drawImage(image, image.naturalWidth / 2, image.naturalHeight / 2, 1, 1, 0, 0, 1, 1);
              const pixel = context?.getImageData(0, 0, 1, 1).data;
              return pixel ? [pixel[0], pixel[1], pixel[2]] : null;
            } catch {
              return null;
            }
          };
          const elementVisible = element => {
            if (!(element instanceof HTMLElement)) return false;
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden'
              && Number(style.opacity || '0') > 0.01 && rect.width > 0 && rect.height > 0;
          };
          while (performance.now() - startedAt <= durationMs) {
            const surface = document.querySelector('.grid-hover-preview');
            const image = surface?.querySelector('img');
            const imageStyle = image instanceof HTMLImageElement ? getComputedStyle(image) : null;
            frames.push({
              elapsedMs: Math.round(performance.now() - startedAt),
              path: surface?.getAttribute('data-preview-path') || null,
              state: surface?.getAttribute('data-media-state') || null,
              surfaceVisible: elementVisible(surface),
              image: image instanceof HTMLImageElement ? {
                complete: image.complete,
                naturalWidth: image.naturalWidth,
                naturalHeight: image.naturalHeight,
                visible: elementVisible(image),
                opacity: Number(imageStyle?.opacity || '0'),
                transitionDuration: imageStyle?.transitionDuration || null,
                rgb: samplePixel(image),
              } : null,
            });
            await new Promise(resolve => requestAnimationFrame(resolve));
          }
          return frames;
        }""",
        duration_ms,
    )
    return raw if isinstance(raw, list) else []


def _configure_page(page: Any, base_url: str, timeout_ms: float, *, corrupt_path: list[str | None]) -> None:
    page.set_default_timeout(timeout_ms)

    def route_file(route: Any) -> None:
        url = route.request.url
        path = parse_qs(urlparse(url).query).get("path", [None])[0]
        if path and path == corrupt_path[0]:
            route.fulfill(status=200, content_type="image/jpeg", body=b"not-an-image")
            return
        page.wait_for_timeout(220)
        route.continue_()

    page.route("**/file?*", route_file)
    page.add_init_script(GRID_STORAGE_SCRIPT)
    page.goto(base_url, wait_until="domcontentloaded")
    wait_for_grid(page, timeout_ms)


def _exercise_context(
    browser: Any,
    base_url: str,
    timeout_ms: float,
    *,
    reduced_motion: bool,
) -> dict[str, Any]:
    context = browser.new_context(
        viewport={"width": 1280, "height": 840},
        device_scale_factor=1.0,
        reduced_motion="reduce" if reduced_motion else "no-preference",
    )
    page = context.new_page()
    corrupt_path: list[str | None] = [None]
    try:
        _configure_page(page, base_url, timeout_ms, corrupt_path=corrupt_path)
        paths = _visible_paths(page, 3)
        success_path, rapid_path, corrupt = paths
        corrupt_path[0] = corrupt

        _hover(page, success_path)
        success_frames = _collect_frames(page, 950)
        _leave_preview(page)
        page.wait_for_timeout(80)

        _hover(page, success_path)
        page.wait_for_timeout(430)
        _hover(page, rapid_path)
        rapid_frames = _collect_frames(page, 950)
        _leave_preview(page)
        page.wait_for_timeout(80)

        _hover(page, corrupt)
        corrupt_frames = _collect_frames(page, 950)
        _leave_preview(page)
        corrupt_after_leave = _collect_frames(page, 120)

        _hover(page, success_path)
        page.wait_for_timeout(410)
        _leave_preview(page)
        cancelled_frames = _collect_frames(page, 500)

        cases = {
            "success": {"path": success_path, "frames": success_frames},
            "rapid": {"path": rapid_path, "frames": rapid_frames},
            "corrupt": {"path": corrupt, "frames": corrupt_frames},
            "corrupt_after_leave": {"path": corrupt, "frames": corrupt_after_leave},
            "cancelled": {"path": success_path, "frames": cancelled_frames},
        }
        violations: list[str] = []
        violations.extend(hover_preview_case_violations(
            "success", success_frames, expected_path=success_path, expected_rgb=fixture_rgb(success_path),
        ))
        violations.extend(hover_preview_case_violations(
            "rapid", rapid_frames, expected_path=rapid_path, expected_rgb=fixture_rgb(rapid_path),
        ))
        violations.extend(hover_preview_case_violations(
            "corrupt", corrupt_frames, expected_path=corrupt, outcome="error",
        ))
        violations.extend(hover_preview_case_violations(
            "corrupt after leave", corrupt_after_leave, expected_path=corrupt, outcome="cancelled",
        ))
        violations.extend(hover_preview_case_violations(
            "cancelled", cancelled_frames, expected_path=success_path, outcome="cancelled",
        ))
        return {
            "reduced_motion": reduced_motion,
            "cases": cases,
            "violations": violations,
        }
    finally:
        context.close()


def _exercise_direct_context(browser: Any, base_url: str, timeout_ms: float) -> dict[str, Any]:
    context = browser.new_context(
        viewport={"width": 1280, "height": 840},
        device_scale_factor=1.0,
    )
    page = context.new_page()
    direct_requests: list[str] = []
    proxy_paths: list[str] = []

    def route_query(route: Any) -> None:
        response = route.fetch()
        payload = response.json()
        items = payload.get("items") if isinstance(payload, dict) else None
        if isinstance(items, list):
            for index, mode in enumerate(("ready", "corrupt")):
                if index >= len(items) or not isinstance(items[index], dict):
                    continue
                path = items[index].get("path")
                if not isinstance(path, str):
                    continue
                direct_url = f"{base_url}/file?path={quote(path, safe='')}&hover_direct={mode}"
                items[index]["url"] = direct_url
                items[index]["source"] = direct_url
                items[index]["original_media"] = {
                    "mode": "browser_direct_preferred_with_proxy_fallback",
                    "source_kind": "http",
                    "proxy_available": True,
                    "direct_allowed_reason": "Sprint 4 direct hover fixture",
                    "warnings": [],
                }
        route.fulfill(
            status=response.status,
            headers={"content-type": "application/json"},
            body=json.dumps(payload),
        )

    def route_file(route: Any) -> None:
        parsed = urlparse(route.request.url)
        query = parse_qs(parsed.query)
        mode = query.get("hover_direct", [None])[0]
        path = query.get("path", [None])[0]
        if mode:
            direct_requests.append(mode)
        elif path:
            proxy_paths.append(path)
        page.wait_for_timeout(220)
        if mode == "corrupt":
            route.fulfill(status=200, content_type="image/jpeg", body=b"not-an-image")
            return
        route.continue_()

    try:
        page.set_default_timeout(timeout_ms)
        page.route("**/folders/query", route_query)
        page.route("**/file?*", route_file)
        page.add_init_script(GRID_STORAGE_SCRIPT)
        page.goto(base_url, wait_until="domcontentloaded")
        wait_for_grid(page, timeout_ms)
        ready_path, fallback_path = _visible_paths(page, 2)

        _hover(page, ready_path)
        ready_frames = _collect_frames(page, 950)
        _leave_preview(page)
        page.wait_for_timeout(80)

        _hover(page, fallback_path)
        fallback_frames = _collect_frames(page, 1_250)
        _leave_preview(page)

        violations = hover_preview_case_violations(
            "direct", ready_frames, expected_path=ready_path, expected_rgb=fixture_rgb(ready_path),
        )
        violations.extend(hover_preview_case_violations(
            "direct fallback",
            fallback_frames,
            expected_path=fallback_path,
            expected_rgb=fixture_rgb(fallback_path),
        ))
        if "ready" not in direct_requests or "corrupt" not in direct_requests:
            violations.append(f"hover direct fixture did not exercise both direct resources: {direct_requests!r}")
        if fallback_path not in proxy_paths:
            violations.append("hover corrupt direct resource did not fall back through the proxy")
        return {
            "ready": {"path": ready_path, "frames": ready_frames},
            "fallback": {"path": fallback_path, "frames": fallback_frames},
            "direct_requests": direct_requests,
            "proxy_paths": proxy_paths,
            "violations": violations,
        }
    finally:
        context.close()


def exercise_hover_preview_continuity(browser: Any, base_url: str, timeout_ms: float) -> dict[str, Any]:
    normal = _exercise_context(browser, base_url, timeout_ms, reduced_motion=False)
    reduced = _exercise_context(browser, base_url, timeout_ms, reduced_motion=True)
    direct = _exercise_direct_context(browser, base_url, timeout_ms)
    return {
        "normal": normal,
        "reduced_motion": reduced,
        "direct": direct,
        "violations": [*normal["violations"], *reduced["violations"], *direct["violations"]],
    }
