"""Browser init scripts for Sprint 6 media and boot stability evidence."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote, urlparse

from scripts.browser.gui_jitter.fixtures import jpeg_payload
from scripts.browser.gui_jitter.shared import wait_for_grid

COMPARE_EXPECTED_RGB = {
    "/quick_00_meta.png": (72, 36, 120),
    "/quick_01_meta.png": (36, 126, 74),
    "/sample_001.jpg": (44, 77, 140),
}
RANKING_EXPECTED_RGB = {
    "0": (48, 92, 156),
    "1": (168, 62, 52),
}
PIXEL_TOLERANCE = 24

MEDIA_DELAY_INIT_SCRIPT = r"""
(() => {
  window.__lensletMediaDelays = window.__lensletMediaDelays || {};
  window.__lensletMediaFailures = window.__lensletMediaFailures || {};
  window.__lensletMediaFailureDeliveries = window.__lensletMediaFailureDeliveries || [];
  const originalFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const raw = typeof input === 'string' ? input : input.url;
    const url = new URL(raw, window.location.href);
    const path = url.searchParams.get('path') || '';
    const identity = `${url.pathname}\u0000${path}`;
    const delay = Number(window.__lensletMediaDelays[identity] || 0);
    const response = await originalFetch(input, init);
    if (delay > 0) await new Promise(resolve => window.setTimeout(resolve, delay));
    if (window.__lensletMediaFailures[identity]) {
      window.__lensletMediaFailureDeliveries.push(identity);
      return new Response(new Uint8Array([0, 1, 2, 3]), {
        status: 200,
        headers: { 'Content-Type': 'image/jpeg' },
      });
    }
    return response;
  };
})();
"""

BOOT_FRAME_INIT_SCRIPT = r"""
(() => {
  window.__lensletBootFrames = [];
  window.__lensletBootTraceRunning = true;
  const sample = () => {
    if (!window.__lensletBootTraceRunning) return;
    const shell = document.querySelector('[data-boot-shell]');
    const root = document.querySelector('.ranking-root');
    const tray = document.querySelector('.ranking-unranked-tray');
    const workspace = document.querySelector('.ranking-workspace');
    window.__lensletBootFrames.push({
      now: performance.now(),
      shell: Boolean(shell),
      copyVisible: shell?.getAttribute('data-loading-copy-visible') === 'true',
      text: document.body?.innerText || '',
      rankingReady: Boolean(root),
      trayHeight: tray?.getBoundingClientRect().height ?? null,
      workspaceHeight: workspace?.getBoundingClientRect().height ?? null,
      shellRect: shell ? {
        width: shell.getBoundingClientRect().width,
        height: shell.getBoundingClientRect().height,
      } : null,
    });
    requestAnimationFrame(sample);
  };
  requestAnimationFrame(sample);
})();
"""

RANKING_DECODE_DELAY_INIT_SCRIPT = r"""
(() => {
  const originalDecode = HTMLImageElement.prototype.decode;
  HTMLImageElement.prototype.decode = function() {
    const decode = () => originalDecode.call(this);
    if (!this.src.includes('probe_id=1')) return decode();
    return new Promise((resolve, reject) => {
      window.setTimeout(() => decode().then(resolve, reject), 1200);
    });
  };
})();
"""


def _rgb_matches(pixel: Any, expected: tuple[int, int, int]) -> bool:
    if not isinstance(pixel, list) or len(pixel) < 3:
        return False
    return max(abs(int(pixel[index]) - expected[index]) for index in range(3)) <= PIXEL_TOLERANCE


def _compare_pixel_mismatch(frame: dict[str, Any]) -> bool:
    paths = [frame.get("presentedA"), frame.get("presentedB")]
    pixels = frame.get("pixels")
    if not isinstance(pixels, list) or len(pixels) != 2:
        return any(paths)
    for path, pixel in zip(paths, pixels, strict=True):
        if path is None:
            continue
        expected = COMPARE_EXPECTED_RGB.get(str(path))
        if expected is None or not _rgb_matches(pixel, expected):
            return True
    return False


def _ranking_pixel_mismatch(frame: dict[str, Any]) -> bool:
    presented = frame.get("presented")
    if presented is None:
        return False
    expected = RANKING_EXPECTED_RGB.get(str(presented))
    return expected is None or not _rgb_matches(frame.get("pixel"), expected)


def _exercise_cold_thumbnail(
    browser: Any,
    base_url: str,
    browser_timeout_ms: float,
) -> dict[str, Any]:
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    context.add_init_script(
        MEDIA_DELAY_INIT_SCRIPT
        + "\nwindow.__lensletMediaDelays['/thumb\\u0000/sample_000.jpg'] = 700;"
    )
    try:
        page = context.new_page()
        page.set_default_timeout(browser_timeout_ms)
        page.goto(base_url, wait_until="domcontentloaded")
        wait_for_grid(page, browser_timeout_ms)
        scroll_root = page.locator('[role="grid"][aria-label="Gallery"]').first
        scroll_root.evaluate("element => { element.scrollTop = element.scrollHeight; }")
        cold_cell = page.locator(f'[id="cell-{quote("/sample_000.jpg", safe="")}"]').first
        cold_cell.wait_for(state="visible", timeout=browser_timeout_ms)
        page.wait_for_timeout(60)

        def snapshot() -> dict[str, Any]:
            return cold_cell.evaluate(
                """cell => {
                  const image = cell.querySelector('img[data-thumbnail-reveal]');
                  const rect = cell.getBoundingClientRect();
                  return {
                    reveal: image?.getAttribute('data-thumbnail-reveal') || null,
                    opacity: image ? Number(getComputedStyle(image).opacity) : 0,
                    width: rect.width,
                    height: rect.height,
                  };
                }"""
            )

        pending = snapshot()
        cold_cell.locator('img[data-thumbnail-reveal="decoded"]').wait_for(
            state="visible",
            timeout=browser_timeout_ms,
        )
        page.wait_for_timeout(200)
        return {"pending": pending, "decoded": snapshot()}
    finally:
        context.close()


def _exercise_compare_media(
    browser: Any,
    base_url: str,
    browser_timeout_ms: float,
) -> dict[str, Any]:
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    context.add_init_script(
        MEDIA_DELAY_INIT_SCRIPT
        + "\nlocalStorage.setItem('compareOrderMode', 'selection');"
        + "\nwindow.__lensletMediaDelays['/file\\u0000/quick_01_meta.png'] = 600;"
        + "\nwindow.__lensletMediaFailures['/file\\u0000/quick_01_meta.png'] = true;"
        + "\nwindow.__lensletMediaDelays['/thumb\\u0000/sample_001.jpg'] = 1800;"
        + "\nwindow.__lensletMediaDelays['/file\\u0000/sample_001.jpg'] = 1800;"
    )
    try:
        page = context.new_page()
        page.set_default_timeout(browser_timeout_ms)
        page.goto(base_url, wait_until="domcontentloaded")
        wait_for_grid(page, browser_timeout_ms)
        scroll_root = page.locator('[role="grid"][aria-label="Gallery"]').first

        def select_path(path: str) -> None:
            cell = page.locator(f'[id="cell-{quote(path, safe="")}"]').first
            if cell.count() == 0:
                at_top = path in {"/quick_00_meta.png", "/quick_01_meta.png"}
                scroll_root.evaluate(
                    "element => { element.scrollTop = 0; }"
                    if at_top
                    else "element => { element.scrollTop = element.scrollHeight; }"
                )
                cell.wait_for(state="visible", timeout=browser_timeout_ms)
            cell.click(modifiers=["Control"])

        for path in ("/quick_01_meta.png", "/quick_00_meta.png", "/sample_001.jpg"):
            select_path(path)
        page.wait_for_function(
            """() => JSON.parse(document.querySelector('[data-browse-shell]')?.getAttribute('data-selected-paths') || '[]').length === 3""",
            timeout=browser_timeout_ms,
        )
        selected_paths = page.evaluate(
            """() => JSON.parse(document.querySelector('[data-browse-shell]')?.getAttribute('data-selected-paths') || '[]')"""
        )
        failure_identity = "/file\u0000/quick_01_meta.png"
        page.get_by_label("Compare selected images").first.click()
        dialog = page.locator('[role="dialog"][aria-label="Compare images"]').first
        dialog.wait_for(state="visible", timeout=browser_timeout_ms)
        page.wait_for_function(
            """() => Boolean(document.querySelector('[aria-label="Compare images"]')?.getAttribute('data-compare-presented-pair'))""",
            timeout=browser_timeout_ms,
        )
        initial_pair = dialog.evaluate(
            """node => ({
              a: node.getAttribute('data-compare-a-path'),
              b: node.getAttribute('data-compare-b-path'),
            })"""
        )
        page.evaluate(
            """() => {
              const samplePixel = image => {
                if (!image?.complete || image.naturalWidth <= 0) return null;
                try {
                  const canvas = document.createElement('canvas');
                  canvas.width = 1;
                  canvas.height = 1;
                  const context = canvas.getContext('2d', { willReadFrequently: true });
                  context.drawImage(
                    image,
                    Math.floor(image.naturalWidth / 2),
                    Math.floor(image.naturalHeight / 2),
                    1,
                    1,
                    0,
                    0,
                    1,
                    1,
                  );
                  return Array.from(context.getImageData(0, 0, 1, 1).data.slice(0, 3));
                } catch {
                  return null;
                }
              };
              window.__lensletCompareMediaFrames = [];
              window.__lensletCompareMediaTraceRunning = true;
              const sample = () => {
                if (!window.__lensletCompareMediaTraceRunning) return;
                const dialog = document.querySelector('[aria-label="Compare images"]');
                if (dialog) {
                  const imageNodes = Array.from(dialog.querySelectorAll('img[data-compare-image]'));
                  window.__lensletCompareMediaFrames.push({
                    now: performance.now(),
                    targetA: dialog.getAttribute('data-compare-target-a-path'),
                    targetB: dialog.getAttribute('data-compare-target-b-path'),
                    presentedA: dialog.getAttribute('data-compare-a-path'),
                    presentedB: dialog.getAttribute('data-compare-b-path'),
                    labels: Array.from(dialog.querySelectorAll('.compare-label [title]'))
                      .map(node => node.getAttribute('title')),
                    images: imageNodes.map(node => node.getAttribute('data-current-path')),
                    pixels: imageNodes.map(samplePixel),
                    errorCount: dialog.querySelectorAll('.media-error-overlay').length,
                    failureDeliveryCount: window.__lensletMediaFailureDeliveries.length,
                  });
                }
                requestAnimationFrame(sample);
              };
              requestAnimationFrame(sample);
            }"""
        )
        dialog.get_by_text("Next", exact=True).click()
        page.wait_for_function(
            """() => {
              const dialog = document.querySelector('[aria-label="Compare images"]');
              return dialog
                && dialog.getAttribute('data-compare-target-a-path') === dialog.getAttribute('data-compare-a-path')
                && dialog.getAttribute('data-compare-target-b-path') === dialog.getAttribute('data-compare-b-path');
            }""",
            timeout=browser_timeout_ms,
        )
        page.wait_for_function(
            "identity => window.__lensletMediaFailureDeliveries.includes(identity)",
            arg=failure_identity,
            timeout=browser_timeout_ms,
        )
        page.wait_for_timeout(80)
        frames = page.evaluate(
            """() => {
              window.__lensletCompareMediaTraceRunning = false;
              return window.__lensletCompareMediaFrames || [];
            }"""
        )
        final_pair = dialog.evaluate(
            """node => ({
              targetA: node.getAttribute('data-compare-target-a-path'),
              targetB: node.getAttribute('data-compare-target-b-path'),
              presentedA: node.getAttribute('data-compare-a-path'),
              presentedB: node.getAttribute('data-compare-b-path'),
            })"""
        )
        identity_mixed = [
            frame
            for frame in frames
            if frame.get("labels") != [frame.get("presentedA"), frame.get("presentedB")]
            or frame.get("images") != [frame.get("presentedA"), frame.get("presentedB")]
            or int(frame.get("errorCount", 0)) > 0
        ]
        pixel_mixed = [frame for frame in frames if _compare_pixel_mismatch(frame)]
        retained = [
            frame
            for frame in frames
            if (frame.get("targetA"), frame.get("targetB"))
            != (frame.get("presentedA"), frame.get("presentedB"))
        ]
        failure_delivery_frames = [
            frame for frame in frames if int(frame.get("failureDeliveryCount", 0)) > 0
        ]
        return {
            "initial_pair": initial_pair,
            "selected_paths": selected_paths,
            "final_pair": final_pair,
            "frame_count": len(frames),
            "retained_frame_count": len(retained),
            "mixed_identity_frame_count": len(identity_mixed),
            "mixed_pixel_frame_count": len(pixel_mixed),
            "mixed_identity_samples": identity_mixed[:3],
            "mixed_pixel_samples": pixel_mixed[:3],
            "superseded_failure_frame_count": len(failure_delivery_frames),
        }
    finally:
        context.close()


def exercise_sprint6_browse_media(
    browser: Any,
    base_url: str,
    browser_timeout_ms: float,
) -> dict[str, Any]:
    cold = _exercise_cold_thumbnail(browser, base_url, browser_timeout_ms)
    compare = _exercise_compare_media(browser, base_url, browser_timeout_ms)
    pending = cold["pending"]
    decoded = cold["decoded"]
    final_pair = compare["final_pair"]
    violations: list[str] = []
    if pending["opacity"] > 0 or pending["reveal"] == "decoded":
        violations.append("cold thumbnail became visible before its delayed decode completed")
    if decoded["reveal"] != "decoded" or decoded["opacity"] < 0.99:
        violations.append("cold thumbnail did not reveal after decode")
    if abs(float(pending["width"]) - float(decoded["width"])) > 1.0 or abs(
        float(pending["height"]) - float(decoded["height"])
    ) > 1.0:
        violations.append("cold thumbnail shell changed geometry across decode")
    if compare["mixed_identity_frame_count"]:
        violations.append("Compare mixed presentation identity")
    if compare["mixed_pixel_frame_count"]:
        violations.append("Compare painted wrong or blank pixels")
    if compare["retained_frame_count"] < 10:
        violations.append("Compare slow success did not retain a prior decoded pair long enough")
    if compare["superseded_failure_frame_count"] == 0:
        violations.append("Compare trace did not observe the superseded corrupt resource delivery")
    if (final_pair["targetA"], final_pair["targetB"]) != (
        final_pair["presentedA"],
        final_pair["presentedB"],
    ):
        violations.append("Compare did not atomically settle the delayed target pair")
    return {"cold_thumbnail": cold, "compare": compare, "violations": violations}


def install_ranking_probe_routes(context: Any) -> None:
    dataset = {
        "dataset_path": "/probe/ranking.json",
        "instance_count": 1,
        "instances": [
            {
                "instance_id": "probe-instance",
                "instance_index": 0,
                "max_ranks": 2,
                "images": [
                    {
                        "image_id": str(index),
                        "source_path": f"probe_{index}.jpg",
                        "url": f"/rank/image?probe_id={index}",
                    }
                    for index in range(3)
                ],
            }
        ],
    }
    image_payloads = {
        "0": jpeg_payload((48, 92, 156)),
        "1": jpeg_payload((168, 62, 52)),
        "2": b"not-an-image",
    }

    def handle(route: Any) -> None:
        url = urlparse(route.request.url)
        if url.path == "/health":
            route.fulfill(
                json={
                    "ok": True,
                    "mode": "ranking",
                    "can_write": True,
                    "dataset_path": "/probe/ranking.json",
                    "results_path": "/probe/results.jsonl",
                    "instance_count": 1,
                }
            )
        elif url.path == "/rank/dataset":
            route.fulfill(json=dataset)
        elif url.path == "/rank/progress":
            route.fulfill(
                json={
                    "completed_instance_ids": [],
                    "last_completed_instance_index": None,
                    "resume_instance_index": 0,
                    "total_instances": 1,
                }
            )
        elif url.path == "/rank/export":
            route.fulfill(
                json={
                    "dataset_path": "/probe/ranking.json",
                    "results_path": "/probe/results.jsonl",
                    "count": 0,
                    "results": [],
                }
            )
        elif url.path == "/rank/save":
            route.fulfill(status=500, json={"detail": "forced ranking save failure"})
        elif url.path == "/rank/image":
            probe_id = url.query.rsplit("=", 1)[-1]
            route.fulfill(body=image_payloads[probe_id], content_type="image/jpeg")
        else:
            route.continue_()

    context.route("**/*", handle)


def _stop_boot_trace(page: Any) -> list[dict[str, Any]]:
    return page.evaluate(
        """() => {
          window.__lensletBootTraceRunning = false;
          return window.__lensletBootFrames || [];
        }"""
    )


def _ranking_layout(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const rect = element => element?.getBoundingClientRect() || null;
          return {
            tray: rect(document.querySelector('.ranking-unranked-tray')),
            workspace: rect(document.querySelector('.ranking-workspace')),
            header: rect(document.querySelector('.ranking-header')),
            exportButton: rect(document.querySelector('.ranking-export-button')),
            nextButton: rect(document.querySelector('.ranking-button-primary')),
          };
        }"""
    )


def exercise_sprint6_ranking(
    browser: Any,
    base_url: str,
    browser_timeout_ms: float,
) -> dict[str, Any]:
    fast_context = browser.new_context(viewport={"width": 1280, "height": 840})
    fast_context.add_init_script(BOOT_FRAME_INIT_SCRIPT)
    install_ranking_probe_routes(fast_context)
    try:
        fast_page = fast_context.new_page()
        fast_page.set_default_timeout(browser_timeout_ms)
        fast_page.goto(base_url, wait_until="domcontentloaded")
        fast_page.locator(".ranking-root").wait_for(state="visible", timeout=browser_timeout_ms)
        fast_page.wait_for_timeout(80)
        fast_frames = _stop_boot_trace(fast_page)
    finally:
        fast_context.close()

    context = browser.new_context(viewport={"width": 1280, "height": 840})
    context.add_init_script(
        MEDIA_DELAY_INIT_SCRIPT
        + "\nwindow.__lensletMediaDelays['/rank/dataset\\u0000'] = 1200;"
        + "\nlocalStorage.setItem('lenslet.ranking.unranked_height_px.v1', '5000');"
    )
    context.add_init_script(BOOT_FRAME_INIT_SCRIPT)
    context.add_init_script(RANKING_DECODE_DELAY_INIT_SCRIPT)
    install_ranking_probe_routes(context)
    try:
        page = context.new_page()
        page.set_default_timeout(browser_timeout_ms)
        page.goto(base_url, wait_until="domcontentloaded")
        page.locator(".ranking-root").first.wait_for(state="visible", timeout=browser_timeout_ms)
        page.wait_for_timeout(80)
        slow_frames = _stop_boot_trace(page)
        layout = _ranking_layout(page)

        page.get_by_label("Open probe_0.jpg fullscreen").click()
        fullscreen = page.locator(".ranking-fullscreen").first
        fullscreen.wait_for(state="visible", timeout=browser_timeout_ms)
        page.wait_for_function(
            """() => document.querySelector('.ranking-fullscreen')?.getAttribute('data-fullscreen-presented-id') === '0'""",
            timeout=browser_timeout_ms,
        )
        page.evaluate(
            """() => {
              const samplePixel = image => {
                if (!image?.complete || image.naturalWidth <= 0) return null;
                try {
                  const canvas = document.createElement('canvas');
                  canvas.width = 1;
                  canvas.height = 1;
                  const context = canvas.getContext('2d', { willReadFrequently: true });
                  context.drawImage(
                    image,
                    Math.floor(image.naturalWidth / 2),
                    Math.floor(image.naturalHeight / 2),
                    1,
                    1,
                    0,
                    0,
                    1,
                    1,
                  );
                  return Array.from(context.getImageData(0, 0, 1, 1).data.slice(0, 3));
                } catch {
                  return null;
                }
              };
              window.__lensletRankingMediaFrames = [];
              window.__lensletRankingMediaTraceRunning = true;
              const sample = () => {
                if (!window.__lensletRankingMediaTraceRunning) return;
                const dialog = document.querySelector('.ranking-fullscreen');
                if (dialog) {
                  const image = dialog.querySelector('[data-fullscreen-image-id]');
                  window.__lensletRankingMediaFrames.push({
                    now: performance.now(),
                    target: dialog.getAttribute('data-fullscreen-target-id'),
                    presented: dialog.getAttribute('data-fullscreen-presented-id') || null,
                    error: dialog.getAttribute('data-fullscreen-error-id') || null,
                    image: image?.getAttribute('data-fullscreen-image-id') || null,
                    label: dialog.querySelector('.ranking-fullscreen-meta span')?.textContent || null,
                    pixel: samplePixel(image),
                  });
                }
                requestAnimationFrame(sample);
              };
              requestAnimationFrame(sample);
            }"""
        )
        page.keyboard.press("d")
        page.wait_for_function(
            """() => document.querySelector('.ranking-fullscreen')?.getAttribute('data-fullscreen-presented-id') === '1'""",
            timeout=browser_timeout_ms,
        )
        page.keyboard.press("d")
        page.wait_for_function(
            """() => document.querySelector('.ranking-fullscreen')?.getAttribute('data-fullscreen-error-id') === '2'""",
            timeout=browser_timeout_ms,
        )
        page.wait_for_timeout(80)
        media_frames = page.evaluate(
            """() => {
              window.__lensletRankingMediaTraceRunning = false;
              return window.__lensletRankingMediaFrames || [];
            }"""
        )
        failed_target = fullscreen.evaluate(
            """dialog => ({
              target: dialog.getAttribute('data-fullscreen-target-id'),
              presented: dialog.getAttribute('data-fullscreen-presented-id'),
              error: dialog.getAttribute('data-fullscreen-error-id'),
            })"""
        )
        page.keyboard.press("Escape")
        page.locator(".ranking-fullscreen").wait_for(state="detached", timeout=browser_timeout_ms)
        page.keyboard.press("1")
        page.locator(".ranking-save-error").wait_for(state="visible", timeout=browser_timeout_ms)
        failed_layout = _ranking_layout(page)

        fast_loading = [frame for frame in fast_frames if frame.get("copyVisible")]
        slow_shell = [frame for frame in slow_frames if frame.get("shell")]
        slow_loading = [frame for frame in slow_shell if frame.get("copyVisible")]
        first_shell_ms = min((float(frame["now"]) for frame in slow_shell), default=0.0)
        first_loading_ms = min((float(frame["now"]) for frame in slow_loading), default=0.0)
        first_layout_frame = next(
            (frame for frame in slow_frames if frame.get("rankingReady")),
            None,
        )
        retained = [
            frame for frame in media_frames if frame.get("target") != frame.get("presented")
        ]
        identity_mixed = [
            frame
            for frame in media_frames
            if frame.get("image") != frame.get("presented")
            or (
                frame.get("presented") is not None
                and frame.get("label") != f"probe_{frame.get('presented')}.jpg"
            )
        ]
        pixel_mixed = [frame for frame in media_frames if _ranking_pixel_mismatch(frame)]
        violations: list[str] = []
        if fast_loading:
            violations.append("fast ranking boot painted loading copy")
        if not slow_loading:
            violations.append("slow ranking boot never painted delayed loading copy")
        elif first_loading_ms - first_shell_ms < 780.0:
            violations.append("slow ranking boot painted loading copy before 800ms")
        if any("Loading ranking session" in str(frame.get("text", "")) for frame in slow_frames):
            violations.append("ranking boot replaced the shared shell with a second loader")
        if (
            not first_layout_frame
            or first_layout_frame.get("trayHeight") is None
            or first_layout_frame.get("workspaceHeight") is None
            or float(first_layout_frame["trayHeight"])
            > float(first_layout_frame["workspaceHeight"]) - 179.0
        ):
            violations.append("restored ranking tray height was not clamped on its first frame")
        tray = layout["tray"]
        workspace = layout["workspace"]
        if not tray or not workspace or float(tray["height"]) > float(workspace["height"]) - 179.0:
            violations.append("restored ranking tray height did not remain clamped")
        if not retained:
            violations.append("delayed fullscreen decode did not retain the prior ranking identity")
        if identity_mixed:
            violations.append(f"ranking fullscreen mixed identity in {len(identity_mixed)} frames")
        if pixel_mixed:
            violations.append(f"ranking fullscreen painted wrong/blank pixels in {len(pixel_mixed)} frames")
        if failed_target != {"target": "2", "presented": "1", "error": "2"}:
            violations.append("ranking decode failure did not retain decoded identity under target error")
        for key in ("header", "exportButton", "nextButton"):
            before = layout[key]
            after = failed_layout[key]
            if not before or not after:
                violations.append(f"ranking save-status evidence missed {key}")
                continue
            delta = max(
                abs(float(before[name]) - float(after[name]))
                for name in ("x", "y", "width", "height")
            )
            if delta > 1.0:
                violations.append(f"ranking save failure moved {key}")
        return {
            "boot": {
                "fast_frame_count": len(fast_frames),
                "fast_loading_copy_frames": len(fast_loading),
                "slow_frame_count": len(slow_frames),
                "slow_loading_copy_frames": len(slow_loading),
                "first_loading_copy_offset_ms": first_loading_ms - first_shell_ms,
            },
            "layout": {
                "first_frame": first_layout_frame,
                "settled": layout,
                "save_failed": failed_layout,
            },
            "fullscreen": {
                "frame_count": len(media_frames),
                "retained_frame_count": len(retained),
                "mixed_identity_frame_count": len(identity_mixed),
                "mixed_pixel_frame_count": len(pixel_mixed),
                "failed_target": failed_target,
            },
            "violations": violations,
        }
    finally:
        context.close()
