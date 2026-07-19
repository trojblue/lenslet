from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse

from scripts.browser.viewer_probe.config import ViewerProbeFailure
from scripts.browser.viewer_probe.open_checks import summarize_open_samples
from scripts.browser.viewer_probe.page import (
    close_viewer,
    is_viewer_open,
    open_first_viewer,
    path_from_cell_id,
    read_viewer_state,
    seed_storage_script,
    wait_for_shell,
    wait_for_viewer_path,
    wait_for_viewer_ready,
    wait_for_visible_grid_cell_ids,
)

try:
    from playwright.sync_api import Error as PlaywrightError
except ImportError:  # pragma: no cover - optional runtime dependency guard
    PlaywrightError = RuntimeError


@dataclass(frozen=True)
class ViewerOpenProbeConfig:
    timeout_ms: float
    frames: int
    interval_ms: int
    delayed_file_route_ms: int
    viewport_width: int = 1200
    viewport_height: int = 820

    def viewport_size(self) -> dict[str, int]:
        return {"width": self.viewport_width, "height": self.viewport_height}


@dataclass(frozen=True)
class ViewerNavigationTrace:
    from_path: str
    to_path: str
    direction: str
    via_paths: tuple[str, ...] = ()
    retained_transform: str | None = None

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "from": self.from_path,
            "to": self.to_path,
            "direction": self.direction,
        }
        if self.via_paths:
            payload["via"] = list(self.via_paths)
        if self.retained_transform:
            payload["retainedTransform"] = self.retained_transform
        return payload


@dataclass(frozen=True)
class ViewerNavigationSample:
    name: str
    expected_path: str
    opened_cell_id: str
    loader_expected: bool
    loader_forbidden: bool
    trace: ViewerNavigationTrace


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
          const imageTokens = new WeakMap();
          let nextImageToken = 1;
          const imageToken = image => {
            let token = imageTokens.get(image);
            if (!token) {
              token = `viewer-image-${nextImageToken}`;
              nextImageToken += 1;
              imageTokens.set(image, token);
            }
            return token;
          };
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
          const imagePayload = (el) => {
            if (!(el instanceof HTMLImageElement)) return null;
            const rect = el.getBoundingClientRect();
            const style = getComputedStyle(el);
            return {
              tag: el.tagName,
              token: imageToken(el),
              alt: el.getAttribute('alt'),
              viewerImage: el.getAttribute('data-viewer-image'),
              src: el.currentSrc || el.src || null,
              currentPath: el.getAttribute('data-current-path'),
              complete: el.complete,
              naturalWidth: el.naturalWidth,
              naturalHeight: el.naturalHeight,
              rgb: samplePixel(el),
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
              viewer: imagePayload(dialog?.querySelector('img[data-viewer-image="full"]')),
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


def _tracked_media_requests(page: Any) -> list[str]:
    requests: list[str] = []
    page.on(
        "request",
        lambda request: requests.append(request.url)
        if urlparse(request.url).path in ("/file", "/thumb")
        else None,
    )
    return requests


def _new_probe_page(
    context: Any,
    base_url: str,
    config: ViewerOpenProbeConfig,
    *,
    file_delay_ms: int,
    corrupt_path: str | None = None,
) -> tuple[Any, list[str]]:
    page = context.new_page()
    page.set_default_timeout(config.timeout_ms)
    requests = _tracked_media_requests(page)
    if corrupt_path:
        def corrupt_file(route: Any) -> None:
            path = parse_qs(urlparse(route.request.url).query).get("path", [None])[0]
            if path == corrupt_path:
                route.fulfill(status=200, content_type="image/jpeg", body=b"not-an-image")
                return
            route.continue_()

        page.route("**/file?*", corrupt_file)
    install_file_delay_route(page, file_delay_ms)
    page.add_init_script(seed_storage_script())
    page.set_viewport_size(config.viewport_size())
    page.goto(base_url, wait_until="domcontentloaded")
    wait_for_shell(page, config.timeout_ms)
    return page, requests


def run_viewer_open_probe(
    context: Any,
    base_url: str,
    *,
    config: ViewerOpenProbeConfig,
) -> list[dict[str, Any]]:
    scenarios = [
        ("delayed-file-load", config.delayed_file_route_ms),
        ("normal-fast-load", 0),
    ]
    results: list[dict[str, Any]] = []
    for name, delay_ms in scenarios:
        page, requests = _new_probe_page(context, base_url, config, file_delay_ms=delay_ms)
        opened_path, opened_cell_id = open_first_viewer(page, config.timeout_ms, wait_for_dialog=False)
        samples = collect_viewer_open_samples(
            page,
            name=name,
            frames=config.frames,
            interval_ms=config.interval_ms,
        )
        ready_wait_error = viewer_ready_wait_error(page, opened_path, config.timeout_ms)
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
                "readyWaitError": ready_wait_error,
                "riskSummary": summarize_open_samples(samples),
            }
        )
        if is_viewer_open(page):
            close_viewer(page, config.timeout_ms)
        page.close()
    results.extend(
        run_rapid_navigation_probe(
            context,
            base_url,
            config=config,
        )
    )
    results.extend(run_reduced_motion_probe(context, base_url, config=config))
    results.append(run_corrupt_navigation_probe(context, base_url, config=config))
    return results


def zoom_presented_viewer(page: Any) -> str | None:
    dialog = page.locator('[role="dialog"][aria-label="Image viewer"]')
    box = dialog.bounding_box()
    if not box:
        return None
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.wheel(0, -700)
    page.wait_for_timeout(80)
    transform = read_viewer_state(page).get("transform")
    return transform if isinstance(transform, str) else None


def run_rapid_navigation_probe(
    context: Any,
    base_url: str,
    *,
    config: ViewerOpenProbeConfig,
) -> list[dict[str, Any]]:
    page, requests = _new_probe_page(
        context,
        base_url,
        config,
        file_delay_ms=config.delayed_file_route_ms,
    )
    cell_ids = wait_for_visible_grid_cell_ids(page, 4, config.timeout_ms)
    paths = [path_from_cell_id(cell_id) for cell_id in cell_ids[:4]]
    opened_path, _ = open_first_viewer(page, config.timeout_ms)
    wait_for_viewer_ready(page, opened_path, config.timeout_ms)
    retained_transform = zoom_presented_viewer(page)

    results: list[dict[str, Any]] = []
    page.keyboard.press("ArrowRight")
    wait_for_viewer_path(page, paths[1], config.timeout_ms)
    page.keyboard.press("ArrowRight")
    wait_for_viewer_path(page, paths[2], config.timeout_ms)
    page.keyboard.press("ArrowRight")
    results.append(
        collect_navigation_samples(
            page,
            ViewerNavigationSample(
                name="rapid-next-delayed-file-load",
                expected_path=paths[3],
                opened_cell_id=cell_ids[3],
                loader_expected=True,
                loader_forbidden=False,
                trace=ViewerNavigationTrace(
                    from_path=opened_path,
                    via_paths=(paths[1], paths[2]),
                    to_path=paths[3],
                    direction="next",
                    retained_transform=retained_transform,
                ),
            ),
            config=config,
            requests=requests,
        )
    )
    retained_transform = zoom_presented_viewer(page)
    page.keyboard.press("ArrowLeft")
    results.append(
        collect_navigation_samples(
            page,
            ViewerNavigationSample(
                name="rapid-prev-delayed-file-load",
                expected_path=paths[2],
                opened_cell_id=cell_ids[2],
                loader_expected=False,
                loader_forbidden=True,
                trace=ViewerNavigationTrace(
                    from_path=paths[3],
                    to_path=paths[2],
                    direction="previous",
                    retained_transform=retained_transform,
                ),
            ),
            config=config,
            requests=requests,
        )
    )
    if is_viewer_open(page):
        close_viewer(page, config.timeout_ms)
    page.close()
    return results


def run_reduced_motion_probe(
    context: Any,
    base_url: str,
    *,
    config: ViewerOpenProbeConfig,
) -> list[dict[str, Any]]:
    page, requests = _new_probe_page(
        context,
        base_url,
        config,
        file_delay_ms=config.delayed_file_route_ms,
    )
    page.emulate_media(reduced_motion="reduce")
    cell_ids = wait_for_visible_grid_cell_ids(page, 2, config.timeout_ms)
    paths = [path_from_cell_id(cell_id) for cell_id in cell_ids[:2]]
    opened_path, _ = open_first_viewer(page, config.timeout_ms)
    wait_for_viewer_ready(page, opened_path, config.timeout_ms)
    page.keyboard.press("ArrowRight")
    result = collect_navigation_samples(
        page,
        ViewerNavigationSample(
            name="reduced-motion-next",
            expected_path=paths[1],
            opened_cell_id=cell_ids[1],
            loader_expected=False,
            loader_forbidden=False,
            trace=ViewerNavigationTrace(
                from_path=opened_path,
                to_path=paths[1],
                direction="next",
            ),
        ),
        config=config,
        requests=requests,
    )
    result["reducedMotion"] = True
    if is_viewer_open(page):
        close_viewer(page, config.timeout_ms)
    page.close()
    return [result]


def run_corrupt_navigation_probe(
    context: Any,
    base_url: str,
    *,
    config: ViewerOpenProbeConfig,
) -> dict[str, Any]:
    corrupt_path = "/alpha/alpha_00_wide.jpg"
    page, requests = _new_probe_page(
        context,
        base_url,
        config,
        file_delay_ms=config.delayed_file_route_ms,
        corrupt_path=corrupt_path,
    )
    cell_ids = wait_for_visible_grid_cell_ids(page, 6, config.timeout_ms)
    paths = [path_from_cell_id(cell_id) for cell_id in cell_ids]
    if corrupt_path not in paths:
        raise ViewerProbeFailure(f"Corrupt Viewer target was not visible: {paths!r}")
    opened_path, _ = open_first_viewer(page, config.timeout_ms)
    wait_for_viewer_ready(page, opened_path, config.timeout_ms)
    corrupt_index = paths.index(corrupt_path)
    for _ in range(corrupt_index):
        page.keyboard.press("ArrowRight")
    wait_for_viewer_path(page, corrupt_path, config.timeout_ms)
    samples = collect_viewer_open_samples(
        page,
        name="corrupt-target",
        frames=config.frames,
        interval_ms=config.interval_ms,
    )
    page.wait_for_function(
        """() => document.querySelector('[role="dialog"][aria-label="Image viewer"]')
          ?.getAttribute('data-viewer-loading-state') === 'error'""",
        timeout=config.timeout_ms,
    )
    settled = page.evaluate(
        """() => {
          const dialog = document.querySelector('[role="dialog"][aria-label="Image viewer"]');
          return {
            missing: !(dialog instanceof HTMLElement),
            dialogPath: dialog?.getAttribute('data-current-path') || null,
            imagePath: dialog?.querySelector('img[data-viewer-image="full"]')?.getAttribute('data-current-path') || null,
            imageCount: dialog?.querySelectorAll('img').length || 0,
            loadingState: dialog?.getAttribute('data-viewer-loading-state') || null,
            neutralLoaderVisible: Boolean(dialog?.querySelector('[data-viewer-loader="neutral"]')),
          };
        }"""
    )
    result = {
        "name": "corrupt-target",
        "openedPath": corrupt_path,
        "openedCellId": cell_ids[corrupt_index],
        "loaderExpected": True,
        "loaderForbidden": False,
        "terminalExpected": "error",
        "samples": samples,
        "settled": settled,
        "requests": requests,
        "navigation": ViewerNavigationTrace(
            from_path=opened_path,
            via_paths=tuple(paths[1:corrupt_index]),
            to_path=corrupt_path,
            direction="next",
        ).as_payload(),
        "riskSummary": summarize_open_samples(samples),
    }
    if is_viewer_open(page):
        close_viewer(page, config.timeout_ms)
    page.close()
    return result


def collect_navigation_samples(
    page: Any,
    sample: ViewerNavigationSample,
    *,
    config: ViewerOpenProbeConfig,
    requests: list[str],
) -> dict[str, Any]:
    wait_for_viewer_path(page, sample.expected_path, config.timeout_ms)
    samples = collect_viewer_open_samples(
        page,
        name=sample.name,
        frames=config.frames,
        interval_ms=config.interval_ms,
    )
    ready_wait_error = viewer_ready_wait_error(page, sample.expected_path, config.timeout_ms)
    settled = read_viewer_state(page)
    return {
        "name": sample.name,
        "delayedFileRouteMs": None,
        "loaderExpected": sample.loader_expected,
        "loaderForbidden": sample.loader_forbidden,
        "openedPath": sample.expected_path,
        "openedCellId": sample.opened_cell_id,
        "samples": samples,
        "settled": settled,
        "requests": list(requests),
        "readyWaitError": ready_wait_error,
        "navigation": sample.trace.as_payload(),
        "riskSummary": summarize_open_samples(samples),
    }


def viewer_ready_wait_error(page: Any, expected_path: str, timeout_ms: float) -> str | None:
    try:
        wait_for_viewer_ready(page, expected_path, timeout_ms)
    except (PlaywrightError, TimeoutError, ViewerProbeFailure) as exc:
        return str(exc)
    return None
