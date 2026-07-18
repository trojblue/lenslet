"""Toolbar jitter probe scenario."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scripts.browser.gui_jitter.shared import ProbeResult, state_delta, wait_for_grid
from scripts.smoke_harness import SmokeFailure, import_playwright
from scripts.browser.viewer_probe.page import wait_for_back_button


@dataclass(slots=True)
class ToolbarSnapshots:
    desktop_browse: dict[str, Any]
    desktop_viewer: dict[str, Any]
    desktop_restored: dict[str, Any]
    narrow_closed: dict[str, Any]
    narrow_open: dict[str, Any]
    narrow_restored: dict[str, Any]
    cold_first_frames: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    surface_stability: dict[str, Any] = field(default_factory=dict)


COLD_FIRST_FRAME_INIT_SCRIPT = """(() => {
  const settings = {
    viewMode: 'grid',
    gridItemSize: '300',
    leftOpen: '0',
    rightOpen: '0',
    autoloadImageMetadata: '0',
    compareOrderMode: 'selection',
    proxyHttpOriginals: '1',
    viewState: JSON.stringify({
      sort: { kind: 'builtin', key: 'random', dir: 'desc' },
      filters: { and: [{ starsIn: { values: [5] } }] },
    }),
    sortSpec: JSON.stringify({ kind: 'builtin', key: 'random', dir: 'desc' }),
    filterAst: JSON.stringify({ and: [{ starsIn: { values: [5] } }] }),
  };
  for (const [key, value] of Object.entries(settings)) localStorage.setItem(key, value);

  const state = { frames: [], running: true };
  window.__lensletColdFirstFrameTrace = state;
  const visible = node => {
    if (!(node instanceof HTMLElement)) return false;
    const rect = node.getBoundingClientRect();
    const style = getComputedStyle(node);
    return rect.width > 0 && rect.height > 0
      && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const capture = now => {
    const shell = document.querySelector('.app-shell');
    const toolbar = document.querySelector('.toolbar-shell');
    if (shell instanceof HTMLElement && toolbar instanceof HTMLElement) {
      state.frames.push({
        now,
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
        layoutMode: shell.getAttribute('data-layout-mode'),
        viewMode: shell.getAttribute('data-view-mode'),
        gridItemSize: Number(shell.getAttribute('data-grid-item-size')),
        userLeftOpen: shell.getAttribute('data-user-left-open'),
        userRightOpen: shell.getAttribute('data-user-right-open'),
        autoloadImageMetadata: shell.getAttribute('data-autoload-image-metadata'),
        compareOrderMode: shell.getAttribute('data-compare-order-mode'),
        proxyHttpOriginals: shell.getAttribute('data-proxy-http-originals'),
        query: shell.getAttribute('data-query'),
        sortKind: shell.getAttribute('data-sort-kind'),
        sortKey: shell.getAttribute('data-sort-key'),
        sortDir: shell.getAttribute('data-sort-dir'),
        desktopSearchVisible: visible(document.querySelector('[data-toolbar-control="search-desktop"]')),
        searchToggleVisible: visible(document.querySelector('[data-toolbar-control="search-toggle"]')),
        mobileDrawerVisible: visible(document.querySelector('.mobile-drawer')),
      });
    }
    if (state.running) requestAnimationFrame(capture);
  };
  requestAnimationFrame(capture);
})()"""


SURFACE_STABILITY_INIT_SCRIPT = """(() => {
  try {
    localStorage.setItem('lenslet.inspector.sections', JSON.stringify({
      quickView: true,
      overview: true,
      compare: true,
      metadata: true,
      basics: true,
      notes: true,
    }));
  } catch {}
  const nativeFetch = window.fetch.bind(window);
  const controller = { folderDelays: {}, similaritySearchDelayMs: 0, similaritySearchCount: 0 };
  window.__lensletSurfaceController = controller;
  window.fetch = async (input, init) => {
    const raw = typeof input === 'string' ? input : input instanceof Request ? input.url : String(input);
    const url = new URL(raw, window.location.origin);
    const method = String(init?.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
    if (url.pathname === '/embeddings/search' && method === 'POST') {
      controller.similaritySearchCount += 1;
      const delayMs = Number(controller.similaritySearchDelayMs || 0);
      if (delayMs > 0) await new Promise(resolve => setTimeout(resolve, delayMs));
      return new Response(JSON.stringify({ embedding: 'probe', items: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.pathname === '/folders') {
      const path = url.searchParams.get('path') || '/';
      const recursive = url.searchParams.get('recursive') === 'true';
      const key = `${path}|${recursive ? 'recursive' : 'direct'}`;
      const delayMs = Number(controller.folderDelays[key] || 0);
      if (delayMs > 0) await new Promise(resolve => setTimeout(resolve, delayMs));
    }
    return nativeFetch(input, init);
  };
})()"""


def _rect(page: Any, selector: str) -> dict[str, float]:
    value = page.evaluate(
        """selector => {
          const node = document.querySelector(selector);
          if (!(node instanceof HTMLElement)) return null;
          const rect = node.getBoundingClientRect();
          return {
            left: rect.left,
            top: rect.top,
            right: rect.right,
            bottom: rect.bottom,
            width: rect.width,
            height: rect.height,
          };
        }""",
        selector,
    )
    if not isinstance(value, dict):
        raise SmokeFailure(f"Missing geometry target: {selector}")
    return {key: float(raw) for key, raw in value.items()}


def _rect_delta(lhs: dict[str, float], rhs: dict[str, float], *keys: str) -> float:
    return max((abs(lhs[key] - rhs[key]) for key in keys), default=0.0)


def _start_utility_paint_trace(page: Any, selector: str) -> None:
    page.evaluate(
        """selector => {
          const samples = [];
          const capture = (node, phase) => {
            if (!(node instanceof HTMLElement) || !node.matches(selector)) return;
            const style = getComputedStyle(node);
            const rect = node.getBoundingClientRect();
            const viewport = window.visualViewport;
            const viewportLeft = viewport?.offsetLeft || 0;
            const viewportTop = viewport?.offsetTop || 0;
            const viewportWidth = viewport?.width || window.innerWidth;
            const viewportHeight = viewport?.height || window.innerHeight;
            samples.push({
              phase,
              opacity: Number(style.opacity),
              transform: style.transform,
              animationName: style.animationName,
              visibility: style.visibility,
              left: rect.left,
              top: rect.top,
              right: rect.right,
              bottom: rect.bottom,
              width: rect.width,
              height: rect.height,
              viewportLeft,
              viewportTop,
              viewportRight: viewportLeft + viewportWidth,
              viewportBottom: viewportTop + viewportHeight,
              viewportWidth,
              viewportHeight,
            });
          };
          const observer = new MutationObserver(records => {
            for (const record of records) {
              for (const added of record.addedNodes) {
                if (!(added instanceof HTMLElement)) continue;
                const node = added.matches(selector) ? added : added.querySelector(selector);
                if (!(node instanceof HTMLElement)) continue;
                capture(node, 'mount');
                requestAnimationFrame(() => {
                  capture(node, 'raf-1');
                  requestAnimationFrame(() => capture(node, 'raf-2'));
                });
              }
            }
          });
          observer.observe(document.body, { childList: true, subtree: true });
          window.__lensletUtilityPaint = { selector, samples, observer };
        }""",
        selector,
    )


def _stop_utility_paint_trace(page: Any) -> list[dict[str, Any]]:
    page.wait_for_timeout(60)
    samples = page.evaluate(
        """() => {
          const trace = window.__lensletUtilityPaint;
          trace?.observer?.disconnect();
          return trace?.samples || [];
        }"""
    )
    return [sample for sample in samples if isinstance(sample, dict)] if isinstance(samples, list) else []


def _first_paint_violations(name: str, samples: list[dict[str, Any]]) -> list[str]:
    violations: list[str] = []
    visible = [
        sample
        for sample in samples
        if sample.get("visibility") != "hidden"
        and float(sample.get("width", 0)) > 0
        and float(sample.get("height", 0)) > 0
    ]
    if not visible:
        return [f"{name} had no visible first-paint sample"]
    for sample in visible:
        if abs(float(sample.get("opacity", 0)) - 1.0) > 0.001:
            violations.append(f"{name} painted with opacity {sample.get('opacity')!r}")
        if sample.get("transform") not in {"none", "matrix(1, 0, 0, 1, 0, 0)"}:
            violations.append(f"{name} painted with transform {sample.get('transform')!r}")
        if sample.get("animationName") not in {"none", ""}:
            violations.append(f"{name} retained animation {sample.get('animationName')!r}")
        if (
            float(sample.get("left", -1)) < float(sample.get("viewportLeft", 0)) - 0.5
            or float(sample.get("top", -1)) < float(sample.get("viewportTop", 0)) - 0.5
            or float(sample.get("right", 1e9)) > float(sample.get("viewportRight", 0)) + 0.5
            or float(sample.get("bottom", 1e9)) > float(sample.get("viewportBottom", 0)) + 0.5
        ):
            violations.append(f"{name} painted outside the viewport: {sample!r}")
    return violations


def snapshot_toolbar(page: Any) -> dict[str, Any]:
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


def capture_cold_first_frames(
    browser: Any,
    *,
    base_url: str,
    browser_timeout_ms: float,
) -> dict[str, list[dict[str, Any]]]:
    viewports = {
        "phone": {"width": 390, "height": 844},
        "narrow": {"width": 820, "height": 900},
        "desktop": {"width": 1440, "height": 920},
    }
    traces: dict[str, list[dict[str, Any]]] = {}
    for name, viewport in viewports.items():
        context = browser.new_context(viewport=viewport)
        context.add_init_script(COLD_FIRST_FRAME_INIT_SCRIPT)
        page = context.new_page()
        page.set_default_timeout(browser_timeout_ms)
        page.goto(
            f"{base_url}?sort=builtin:name:asc&q=sample",
            wait_until="domcontentloaded",
        )
        wait_for_grid(page, browser_timeout_ms)
        frames = page.evaluate(
            """() => new Promise(resolve => requestAnimationFrame(() => {
              const state = window.__lensletColdFirstFrameTrace;
              if (state) state.running = false;
              requestAnimationFrame(() => resolve(state?.frames || []));
            }))"""
        )
        if not isinstance(frames, list):
            raise SmokeFailure(f"Failed to capture cold first frames for {name}.")
        traces[name] = [frame for frame in frames if isinstance(frame, dict)]
        context.close()
    return traces


def anchor_delta(lhs: dict[str, Any], rhs: dict[str, Any], slot: str) -> float | None:
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


def assert_hidden_control_state(
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


def cold_first_frame_violations(
    traces: dict[str, list[dict[str, Any]]],
) -> list[str]:
    violations: list[str] = []
    expected_layouts = {"phone": "phone", "narrow": "narrow", "desktop": "desktop"}
    expected_settings = {
        "viewMode": "grid",
        "gridItemSize": 300,
        "userLeftOpen": "false",
        "userRightOpen": "false",
        "autoloadImageMetadata": "false",
        "compareOrderMode": "selection",
        "proxyHttpOriginals": "true",
        "query": "sample",
        "sortKind": "builtin",
        "sortKey": "name",
        "sortDir": "asc",
    }
    for name, expected_layout in expected_layouts.items():
        frames = traces.get(name, [])
        if not frames:
            violations.append(f"{name} cold load captured no AppShell frames")
            continue
        for frame in frames:
            if frame.get("layoutMode") != expected_layout:
                violations.append(f"{name} cold load painted layout {frame.get('layoutMode')!r}")
                break
            expected_narrow = name != "desktop"
            if bool(frame.get("desktopSearchVisible")) == expected_narrow:
                violations.append(
                    f"{name} cold load painted contradictory desktop search structure: {frame!r}"
                )
                break
            if bool(frame.get("searchToggleVisible")) != expected_narrow:
                violations.append(
                    f"{name} cold load painted contradictory narrow search structure: {frame!r}"
                )
                break
            mismatches = {
                key: {"expected": value, "actual": frame.get(key)}
                for key, value in expected_settings.items()
                if frame.get(key) != value
            }
            if mismatches:
                violations.append(
                    f"{name} cold load painted default or precedence-violating settings: {mismatches!r}"
                )
                break
    return violations


def is_viewer_open(page: Any) -> bool:
    raw = page.evaluate(
        """() => {
          const viewer = document.querySelector('[role="dialog"][aria-label="Image viewer"]');
          if (!(viewer instanceof HTMLElement)) return false;
          const rect = viewer.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0;
        }"""
    )
    return bool(raw)


def open_viewer_with_fallback(
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
        if is_viewer_open(page):
            return
        try:
            attempt()
        except playwright_error:
            if is_viewer_open(page):
                return
            continue
        if is_viewer_open(page):
            return
        try:
            wait_for_back_button(page, min(5_000, browser_timeout_ms))
            return
        except playwright_timeout_error:
            if is_viewer_open(page):
                return
            continue
    raise SmokeFailure("Timed out waiting for viewer back button to become interactive.")


def close_viewer(page: Any, browser_timeout_ms: float) -> None:
    back_button = page.locator('[data-toolbar-control="back"]').first
    if back_button.count() > 0 and back_button.is_enabled():
        back_button.click()
    else:
        page.keyboard.press("Escape")
    wait_for_grid(page, browser_timeout_ms)


def wait_for_mobile_search(page: Any, *, disabled: bool, browser_timeout_ms: float) -> None:
    page.wait_for_function(
        """(expectedDisabled) => {
          const input = document.querySelector('[data-toolbar-control="search-mobile"]');
          return input instanceof HTMLInputElement && input.disabled === expectedDisabled;
        }""",
        arg=disabled,
        timeout=browser_timeout_ms,
    )


def _capture_dropdown_surface(page: Any, timeout_ms: float) -> dict[str, Any]:
    trigger = page.get_by_label("Sort and layout").first
    trigger_rect = _rect(page, 'button[aria-label="Sort and layout"]')
    _start_utility_paint_trace(page, '.dropdown-panel[aria-label="Sort and layout"]')
    trigger.click()
    panel = page.locator('.dropdown-panel[aria-label="Sort and layout"]').first
    panel.wait_for(state="visible", timeout=timeout_ms)
    samples = _stop_utility_paint_trace(page)
    geometry = page.evaluate(
        """() => {
          const panel = document.querySelector('.dropdown-panel[aria-label="Sort and layout"]');
          const trigger = document.querySelector('button[aria-label="Sort and layout"]');
          if (!(panel instanceof HTMLElement) || !(trigger instanceof HTMLElement)) return null;
          const panelRect = panel.getBoundingClientRect();
          const triggerRect = trigger.getBoundingClientRect();
          const checks = Array.from(panel.querySelectorAll('.dropdown-item-check'));
          const items = Array.from(panel.querySelectorAll('.dropdown-item'));
          return {
            side: panelRect.bottom <= triggerRect.top ? 'above' : 'below',
            panel: {
              left: panelRect.left,
              top: panelRect.top,
              right: panelRect.right,
              bottom: panelRect.bottom,
            },
            checkCount: checks.length,
            itemCount: items.length,
            checkWidths: checks.map(node => node.getBoundingClientRect().width),
          };
        }"""
    )
    page.keyboard.press("Escape")
    page.evaluate(
        """() => {
          const trigger = document.querySelector('button[aria-label="Sort and layout"]');
          const container = trigger?.closest('.relative');
          if (!(container instanceof HTMLElement)) throw new Error('Missing Dropdown container');
          container.setAttribute('data-dropdown-growth-probe', 'true');
          Object.assign(container.style, {
            position: 'fixed',
            left: '100px',
            bottom: '8px',
            width: '160px',
            zIndex: '1000',
          });
        }"""
    )
    page.set_viewport_size({"width": 1440, "height": 240})
    trigger.click()
    panel.wait_for(state="visible", timeout=timeout_ms)
    above_before = page.evaluate(
        """() => {
          const panel = document.querySelector('.dropdown-panel[aria-label="Sort and layout"]');
          const trigger = document.querySelector('button[aria-label="Sort and layout"]');
          if (!(panel instanceof HTMLElement) || !(trigger instanceof HTMLElement)) return null;
          const panelRect = panel.getBoundingClientRect();
          const triggerRect = trigger.getBoundingClientRect();
          return {
            panel: { top: panelRect.top, bottom: panelRect.bottom, height: panelRect.height },
            trigger: { top: triggerRect.top, bottom: triggerRect.bottom },
            scrollHeight: panel.scrollHeight,
          };
        }"""
    )
    page.set_viewport_size({"width": 1440, "height": 500})
    page.wait_for_function(
        """() => {
          const panel = document.querySelector('.dropdown-panel[aria-label="Sort and layout"]');
          const trigger = document.querySelector('button[aria-label="Sort and layout"]');
          if (!(panel instanceof HTMLElement) || !(trigger instanceof HTMLElement)) return false;
          const panelRect = panel.getBoundingClientRect();
          const triggerRect = trigger.getBoundingClientRect();
          return panelRect.height >= panel.scrollHeight - 1 && panelRect.bottom <= triggerRect.top - 5;
        }""",
        timeout=timeout_ms,
    )
    above_after = page.evaluate(
        """() => {
          const panel = document.querySelector('.dropdown-panel[aria-label="Sort and layout"]');
          const trigger = document.querySelector('button[aria-label="Sort and layout"]');
          if (!(panel instanceof HTMLElement) || !(trigger instanceof HTMLElement)) return null;
          const panelRect = panel.getBoundingClientRect();
          const triggerRect = trigger.getBoundingClientRect();
          return {
            panel: { top: panelRect.top, bottom: panelRect.bottom, height: panelRect.height },
            trigger: { top: triggerRect.top, bottom: triggerRect.bottom },
            scrollHeight: panel.scrollHeight,
          };
        }"""
    )
    page.keyboard.press("Escape")
    page.evaluate(
        """() => {
          const container = document.querySelector('[data-dropdown-growth-probe="true"]');
          if (container instanceof HTMLElement) {
            container.removeAttribute('data-dropdown-growth-probe');
            container.removeAttribute('style');
          }
        }"""
    )
    page.set_viewport_size({"width": 1440, "height": 920})
    if not isinstance(geometry, dict):
        raise SmokeFailure("Failed to capture Dropdown surface geometry.")
    if not isinstance(above_before, dict) or not isinstance(above_after, dict):
        raise SmokeFailure("Failed to capture constrained above-side Dropdown growth.")
    violations = _first_paint_violations("Dropdown", samples)
    if geometry.get("checkCount") != geometry.get("itemCount"):
        violations.append(f"Dropdown check slots were not reserved for every item: {geometry!r}")
    if any(abs(float(width) - 14.0) > 0.5 for width in geometry.get("checkWidths", [])):
        violations.append(f"Dropdown check slots lost fixed width: {geometry.get('checkWidths')!r}")
    if geometry.get("side") == "below" and float(geometry["panel"]["top"]) < trigger_rect["bottom"] - 0.5:
        violations.append(f"Dropdown below placement overlapped its trigger: {geometry!r}")
    growth_overlap = max(
        0.0,
        float(above_before["panel"]["bottom"]) - float(above_before["trigger"]["top"]),
        float(above_after["panel"]["bottom"]) - float(above_after["trigger"]["top"]),
    )
    if growth_overlap > 1.0:
        violations.append(f"Above-side Dropdown overlapped its trigger while growing: {growth_overlap:.3f}px")
    if float(above_after["panel"]["height"]) <= float(above_before["panel"]["height"]) + 1.0:
        violations.append(f"Above-side Dropdown did not exercise constrained growth: {above_before!r}; {above_after!r}")
    return {
        "samples": samples,
        "geometry": geometry,
        "above_growth": {"before": above_before, "after": above_after, "overlap_px": growth_overlap},
        "violations": violations,
    }


def _capture_theme_surface(page: Any, timeout_ms: float) -> dict[str, Any]:
    trigger = page.locator(".theme-settings-menu-trigger-sidebar").first
    _start_utility_paint_trace(page, ".theme-settings-menu-panel")
    trigger.click()
    panel = page.locator(".theme-settings-menu-panel").first
    panel.wait_for(state="visible", timeout=timeout_ms)
    samples = _stop_utility_paint_trace(page)
    before = _rect(page, ".theme-settings-menu-panel")
    page.add_style_tag(content='[data-probe-grow="true"] { padding-bottom: 260px !important; }')
    panel.evaluate("node => node.setAttribute('data-probe-grow', 'true')")
    page.wait_for_timeout(100)
    after = _rect(page, ".theme-settings-menu-panel")
    overflow = page.evaluate(
        """() => {
          const panel = document.querySelector('.theme-settings-menu-panel');
          return panel instanceof HTMLElement ? {
            clientHeight: panel.clientHeight,
            scrollHeight: panel.scrollHeight,
            overflowY: getComputedStyle(panel).overflowY,
          } : null;
        }"""
    )
    page.keyboard.press("Escape")
    anchor_delta = _rect_delta(before, after, "right", "bottom")
    violations = _first_paint_violations("Theme Settings", samples)
    if anchor_delta > 1.0:
        violations.append(
            f"Theme Settings lost its anchored edges while growing: {anchor_delta:.3f}px; "
            f"before={before!r}; after={after!r}"
        )
    if not isinstance(overflow, dict) or overflow.get("overflowY") not in {"auto", "scroll"}:
        violations.append(f"Theme Settings did not retain bounded internal scrolling: {overflow!r}")
    return {
        "samples": samples,
        "before": before,
        "after": after,
        "anchored_edge_delta_px": anchor_delta,
        "overflow": overflow,
        "violations": violations,
    }


def _capture_count_and_sync_slots(page: Any, timeout_ms: float) -> dict[str, Any]:
    expected_initial_count = "18 items"
    expected_filtered_count = "1 / 18 items"
    page.wait_for_function(
        "expected => (document.querySelector('.toolbar-count')?.textContent || '').trim() === expected",
        arg=expected_initial_count,
        timeout=timeout_ms,
    )
    count_before = _rect(page, ".toolbar-count")
    sort_before = _rect(page, ".toolbar-sort")
    count_before_text = page.locator(".toolbar-count").inner_text().strip()
    search = page.get_by_label("Search filename, tags, notes").first
    search.fill("quick_00")
    try:
        page.wait_for_function(
            "expected => (document.querySelector('.toolbar-count')?.textContent || '').trim() === expected",
            arg=expected_filtered_count,
            timeout=timeout_ms,
        )
    except Exception as exc:
        text = page.locator(".toolbar-count").inner_text()
        raise SmokeFailure(f"toolbar count never settled after search; text={text!r}") from exc
    count_after = _rect(page, ".toolbar-count")
    sort_after = _rect(page, ".toolbar-sort")
    count_after_text = page.locator(".toolbar-count").inner_text().strip()
    search.fill("")
    try:
        page.wait_for_function(
            "expected => (document.querySelector('.toolbar-count')?.textContent || '').trim() === expected",
            arg=expected_initial_count,
            timeout=timeout_ms,
        )
    except Exception as exc:
        text = page.locator(".toolbar-count").inner_text()
        raise SmokeFailure(f"toolbar count never restored after search; text={text!r}") from exc

    page.reload(wait_until="domcontentloaded")
    wait_for_grid(page, timeout_ms)
    first_cell = page.locator('[role="gridcell"][id^="cell-"]').first
    first_cell.click()
    notes = page.locator('textarea[aria-label="Notes"]').first
    notes.wait_for(state="visible", timeout=timeout_ms)
    sync_before = _rect(page, ".sync-indicator-button")
    notes.fill("surface stability note")
    try:
        page.wait_for_function(
            """() => document.querySelector('.sync-indicator-local')?.getAttribute('data-active') === 'true'""",
            timeout=min(timeout_ms, 3_000),
        )
    except Exception as exc:
        state = page.evaluate(
            """() => ({
              viewport: [window.innerWidth, window.innerHeight],
              local: document.querySelector('.sync-indicator-local')?.outerHTML || null,
              notes: document.querySelector('textarea[aria-label="Notes"]')?.value || null,
              active: document.activeElement?.getAttribute('aria-label') || null,
            })"""
        )
        raise SmokeFailure(f"Sync typing slot never became active: {state!r}") from exc
    sync_typing = _rect(page, ".sync-indicator-button")
    notes.blur()
    try:
        page.wait_for_function(
            """() => document.querySelector('.sync-indicator-local')?.getAttribute('data-active') === 'false'""",
            timeout=timeout_ms,
        )
    except Exception as exc:
        raise SmokeFailure("Sync typing slot never became inactive") from exc
    sync_after = _rect(page, ".sync-indicator-button")

    _start_utility_paint_trace(page, ".sync-indicator-card")
    page.get_by_label("Sync status").click()
    card = page.locator(".sync-indicator-card").first
    card.wait_for(state="visible", timeout=timeout_ms)
    sync_samples = _stop_utility_paint_trace(page)
    try:
        page.wait_for_function(
            """() => document.querySelector('.sync-indicator-item-name') instanceof HTMLElement""",
            timeout=timeout_ms,
        )
    except Exception as exc:
        card_text = card.inner_text()
        raise SmokeFailure(f"Sync recent touch did not arrive; card={card_text!r}") from exc
    item_before = _rect(page, ".sync-indicator-item-name")
    time_before = _rect(page, ".sync-indicator-item-time")
    page.locator(".sync-indicator-item-name").first.click()
    try:
        page.wait_for_function(
            """() => (document.querySelector('.sync-indicator-item-time')?.textContent || '').trim() === 'Copied'""",
            timeout=timeout_ms,
        )
    except Exception as exc:
        value = page.locator(".sync-indicator-item-time").first.inner_text()
        raise SmokeFailure(f"Sync copy feedback did not paint; value={value!r}") from exc
    item_after = _rect(page, ".sync-indicator-item-name")
    time_after = _rect(page, ".sync-indicator-item-time")
    page.keyboard.press("Escape")

    count_delta = _rect_delta(count_before, count_after, "left", "top", "width", "height")
    sort_delta = _rect_delta(sort_before, sort_after, "left", "top", "width", "height")
    typing_delta = max(
        _rect_delta(sync_before, sync_typing, "left", "top", "width", "height"),
        _rect_delta(sync_before, sync_after, "left", "top", "width", "height"),
    )
    copy_delta = max(
        _rect_delta(item_before, item_after, "left", "top", "width", "height"),
        _rect_delta(time_before, time_after, "left", "top", "width", "height"),
    )
    violations = _first_paint_violations("Sync status", sync_samples)
    for name, delta in {
        "toolbar count": count_delta,
        "toolbar sort anchor": sort_delta,
        "Sync typing": typing_delta,
        "Sync copy": copy_delta,
    }.items():
        if delta > 1.0:
            violations.append(f"{name} slot moved {delta:.3f}px")
    return {
        "count_text": {
            "before": count_before_text,
            "filtered": count_after_text,
            "restored": page.locator(".toolbar-count").inner_text().strip(),
        },
        "count_delta_px": count_delta,
        "sort_anchor_delta_px": sort_delta,
        "typing_delta_px": typing_delta,
        "copy_delta_px": copy_delta,
        "sync_samples": sync_samples,
        "violations": violations,
    }


def _capture_folder_and_context_surfaces(page: Any, timeout_ms: float) -> dict[str, Any]:
    row = page.locator('.tree-row', has=page.locator('span[title="scope_a"]')).first
    row.wait_for(state="visible", timeout=timeout_ms)
    label = row.locator('span[title="scope_a"]')
    count = row.locator(".tree-row-count")
    action = row.locator(".tree-row-action-btn")
    before = {
        "label": _rect(page, '.tree-row span[title="scope_a"]'),
        "count": count.evaluate("node => { const r = node.getBoundingClientRect(); return {left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height}; }")
    }
    before["action"] = action.evaluate(
        "node => { const r = node.getBoundingClientRect(); return {left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height}; }"
    )
    page.evaluate(
        """() => { window.__lensletSurfaceController.folderDelays['/scope_a|direct'] = 350; }"""
    )
    row.get_by_role("button", name="Expand scope_a").click()
    page.locator(".tree-child-state", has_text="Loading folders").wait_for(state="visible", timeout=timeout_ms)
    pending = {
        "label": label.evaluate("node => { const r = node.getBoundingClientRect(); return {left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height}; }"),
        "count": count.evaluate("node => { const r = node.getBoundingClientRect(); return {left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height}; }"),
        "action": action.evaluate("node => { const r = node.getBoundingClientRect(); return {left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height}; }"),
    }
    page.locator(".tree-child-state").wait_for(state="detached", timeout=timeout_ms)
    terminal = {
        "label": label.evaluate("node => { const r = node.getBoundingClientRect(); return {left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height}; }"),
        "count": count.evaluate("node => { const r = node.getBoundingClientRect(); return {left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height}; }"),
        "action": action.evaluate("node => { const r = node.getBoundingClientRect(); return {left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height}; }"),
    }
    folder_delta = max(
        abs(float(before[name][key]) - float(state[name][key]))
        for state in (pending, terminal)
        for name in ("label", "count", "action")
        for key in ("left", "top", "width", "height")
    )

    page.evaluate(
        """() => { window.__lensletSurfaceController.folderDelays['/scope_a|recursive'] = 500; }"""
    )
    _start_utility_paint_trace(page, ".context-menu-panel")
    row.evaluate(
        """node => node.dispatchEvent(new MouseEvent('contextmenu', {
          bubbles: true,
          cancelable: true,
          clientX: window.innerWidth - 2,
          clientY: window.innerHeight - 2,
        }))"""
    )
    menu = page.locator(".context-menu-panel").first
    menu.wait_for(state="visible", timeout=timeout_ms)
    context_samples = _stop_utility_paint_trace(page)
    menu_before = _rect(page, ".context-menu-panel")
    menu.get_by_role("menuitem", name="Export metadata (CSV)").click()
    menu.get_by_role("menuitem", name="Exporting CSV…").wait_for(state="visible", timeout=timeout_ms)
    menu_after = _rect(page, ".context-menu-panel")
    context_delta = _rect_delta(menu_before, menu_after, "left", "top", "width", "height")
    page.set_viewport_size({"width": 160, "height": 920})
    page.wait_for_timeout(100)
    narrow_menu = _rect(page, ".context-menu-panel")
    narrow_overflow = max(
        0.0,
        8.0 - float(narrow_menu["left"]),
        float(narrow_menu["right"]) - 152.0,
    )
    page.set_viewport_size({"width": 800, "height": 920})
    page.wait_for_timeout(100)
    cdp_session = page.context.new_cdp_session(page)
    try:
        cdp_session.send("Emulation.setPageScaleFactor", {"pageScaleFactor": 4})
        page.wait_for_function(
            """() => {
              const menu = document.querySelector('.context-menu-panel');
              const viewport = window.visualViewport;
              if (!(menu instanceof HTMLElement) || !viewport) return false;
              const rect = menu.getBoundingClientRect();
              const left = viewport.offsetLeft;
              const top = viewport.offsetTop;
              return rect.left >= left + 7
                && rect.top >= top + 7
                && rect.right <= left + viewport.width - 7
                && rect.bottom <= top + viewport.height - 7;
            }""",
            timeout=timeout_ms,
        )
        visual_menu = _rect(page, ".context-menu-panel")
        visual_bounds = page.evaluate(
            """() => {
              const viewport = window.visualViewport;
              const left = viewport?.offsetLeft || 0;
              const top = viewport?.offsetTop || 0;
              const width = viewport?.width || window.innerWidth;
              const height = viewport?.height || window.innerHeight;
              return { left, top, right: left + width, bottom: top + height, width, height };
            }"""
        )
    finally:
        cdp_session.send("Emulation.setPageScaleFactor", {"pageScaleFactor": 1})
        cdp_session.detach()
    page.set_viewport_size({"width": 1440, "height": 920})
    page.wait_for_timeout(100)
    page.keyboard.press("Escape")
    visual_overflow = max(
        0.0,
        float(visual_bounds["left"]) + 8.0 - float(visual_menu["left"]),
        float(visual_menu["right"]) - (float(visual_bounds["right"]) - 8.0),
        float(visual_bounds["top"]) + 8.0 - float(visual_menu["top"]),
        float(visual_menu["bottom"]) - (float(visual_bounds["bottom"]) - 8.0),
    )
    violations = _first_paint_violations("ContextMenu", context_samples)
    if folder_delta > 1.0:
        violations.append(f"FolderTree parent anchors moved {folder_delta:.3f}px during hydration")
    if context_delta > 1.0:
        violations.append(f"ContextMenu moved {context_delta:.3f}px for busy copy")
    if narrow_overflow > 1.0:
        violations.append(
            f"ContextMenu overflowed a 160px viewport by {narrow_overflow:.3f}px: {narrow_menu!r}"
        )
    if visual_overflow > 1.0:
        violations.append(
            f"ContextMenu overflowed the zoomed visual viewport by {visual_overflow:.3f}px: "
            f"menu={visual_menu!r}; viewport={visual_bounds!r}"
        )
    return {
        "folder_delta_px": folder_delta,
        "context_delta_px": context_delta,
        "context_narrow": narrow_menu,
        "context_narrow_overflow_px": narrow_overflow,
        "context_visual_viewport": visual_bounds,
        "context_visual_menu": visual_menu,
        "context_visual_overflow_px": visual_overflow,
        "context_samples": context_samples,
        "violations": violations,
    }


def _capture_similarity_surface(page: Any, timeout_ms: float) -> dict[str, Any]:
    first_cell = page.locator('[role="gridcell"][id^="cell-"]').first
    first_cell.click()
    button = page.get_by_role("button", name="Find similar").first
    button.wait_for(state="visible", timeout=timeout_ms)
    page.wait_for_function(
        """() => !document.querySelector('button[title="Find similar"]')?.disabled""",
        timeout=timeout_ms,
    )
    _start_utility_paint_trace(page, '[role="dialog"][aria-label="Find similar"]')
    button.click()
    dialog = page.get_by_role("dialog", name="Find similar")
    dialog.wait_for(state="visible", timeout=timeout_ms)
    samples = _stop_utility_paint_trace(page)
    initial = {
        "shell": _rect(page, ".similarity-modal-shell"),
        "header": _rect(page, ".similarity-modal-header"),
        "footer": _rect(page, ".similarity-modal-footer"),
    }
    dialog.get_by_role("button", name="Vector input").click()
    dialog.get_by_text("Vector (base64 float32)").wait_for(state="visible", timeout=timeout_ms)
    vector = {
        "shell": _rect(page, ".similarity-modal-shell"),
        "header": _rect(page, ".similarity-modal-header"),
        "footer": _rect(page, ".similarity-modal-footer"),
    }
    dialog.get_by_role("button", name="Find similar").click()
    dialog.get_by_role("alert").wait_for(state="visible", timeout=timeout_ms)
    error = {
        "shell": _rect(page, ".similarity-modal-shell"),
        "header": _rect(page, ".similarity-modal-header"),
        "footer": _rect(page, ".similarity-modal-footer"),
    }
    modal_delta = max(
        abs(float(initial[name][key]) - float(state[name][key]))
        for state in (vector, error)
        for name in ("shell", "header", "footer")
        for key in ("left", "top", "width", "height")
    )
    body = page.evaluate(
        """() => {
          const body = document.querySelector('.similarity-modal-body');
          return body instanceof HTMLElement ? {
            clientHeight: body.clientHeight,
            scrollHeight: body.scrollHeight,
            overflowY: getComputedStyle(body).overflowY,
          } : null;
        }"""
    )
    dialog.get_by_role("button", name="Selected image").click()
    page.evaluate("() => { window.__lensletSurfaceController.similaritySearchDelayMs = 450; }")
    dialog.get_by_role("button", name="Find similar").click()
    dialog.get_by_role("button", name="Searching...").wait_for(state="visible", timeout=timeout_ms)
    page.wait_for_function(
        "() => window.__lensletSurfaceController.similaritySearchCount === 1",
        timeout=timeout_ms,
    )
    dialog.get_by_role("button", name="Close").click()
    dialog.wait_for(state="detached", timeout=timeout_ms)
    button.click()
    reopened = page.get_by_role("dialog", name="Find similar")
    reopened.wait_for(state="visible", timeout=timeout_ms)
    page.wait_for_timeout(550)
    stale_lifetime = page.evaluate(
        """() => {
          const dialog = document.querySelector('[role="dialog"][aria-label="Find similar"]');
          const useSelected = dialog?.querySelector('button[title="Use selected image"]');
          return {
            dialogVisible: dialog instanceof HTMLElement,
            selectedPathStillAvailable: useSelected instanceof HTMLButtonElement && !useSelected.disabled,
            requestCount: window.__lensletSurfaceController.similaritySearchCount,
          };
        }"""
    )
    reopened.get_by_role("button", name="Close").click()
    violations = _first_paint_violations("Similarity dialog", samples)
    if modal_delta > 1.0:
        violations.append(f"Similarity outer anchors moved {modal_delta:.3f}px")
    if not isinstance(body, dict) or body.get("overflowY") not in {"auto", "scroll"}:
        violations.append(f"Similarity body was not the bounded scroll owner: {body!r}")
    if not isinstance(stale_lifetime, dict) or not stale_lifetime.get("dialogVisible"):
        violations.append(f"A stale Similarity completion closed the reopened dialog: {stale_lifetime!r}")
    if not isinstance(stale_lifetime, dict) or not stale_lifetime.get("selectedPathStillAvailable"):
        violations.append(f"A stale Similarity completion replaced the reopened target: {stale_lifetime!r}")
    return {
        "samples": samples,
        "modal_delta_px": modal_delta,
        "body": body,
        "stale_lifetime": stale_lifetime,
        "violations": violations,
    }


def exercise_surface_stability(page: Any, *, base_url: str, timeout_ms: float) -> dict[str, Any]:
    page.goto(base_url, wait_until="domcontentloaded")
    wait_for_grid(page, timeout_ms)
    checks: dict[str, Any] = {}
    stages = (
        ("dropdown", _capture_dropdown_surface),
        ("theme", _capture_theme_surface),
        ("count_and_sync", _capture_count_and_sync_slots),
        ("folder_and_context", _capture_folder_and_context_surfaces),
        ("similarity", _capture_similarity_surface),
    )
    for name, capture in stages:
        try:
            checks[name] = capture(page, timeout_ms)
        except Exception as exc:
            raise SmokeFailure(f"Sprint 5 surface stage {name} failed: {exc}") from exc
    violations = [
        violation
        for check in checks.values()
        for violation in check.get("violations", [])
    ]
    checks["violations"] = violations
    checks["max_anchor_delta_px"] = max(
        float(check.get(key, 0.0))
        for check in checks.values()
        if isinstance(check, dict)
        for key in (
            "anchored_edge_delta_px",
            "count_delta_px",
            "sort_anchor_delta_px",
            "typing_delta_px",
            "copy_delta_px",
            "folder_delta_px",
            "context_delta_px",
            "modal_delta_px",
        )
    )
    return checks


def exercise_toolbar_probe(
    page: Any,
    *,
    base_url: str,
    browser_timeout_ms: float,
    playwright_timeout_error: type[BaseException],
    playwright_error: type[BaseException],
) -> ToolbarSnapshots:
    page.goto(base_url, wait_until="domcontentloaded")
    wait_for_grid(page, browser_timeout_ms)
    desktop_browse = snapshot_toolbar(page)

    open_viewer_with_fallback(page, browser_timeout_ms, playwright_timeout_error, playwright_error)
    desktop_viewer = snapshot_toolbar(page)
    close_viewer(page, browser_timeout_ms)
    desktop_restored = snapshot_toolbar(page)

    page.set_viewport_size({"width": 760, "height": 840})
    page.reload(wait_until="domcontentloaded")
    wait_for_grid(page, browser_timeout_ms)
    narrow_closed = snapshot_toolbar(page)

    toggle_button = page.locator('[data-toolbar-control="search-toggle"]').first
    toggle_button.click()
    wait_for_mobile_search(page, disabled=False, browser_timeout_ms=browser_timeout_ms)
    narrow_open = snapshot_toolbar(page)

    toggle_button.click()
    wait_for_mobile_search(page, disabled=True, browser_timeout_ms=browser_timeout_ms)
    narrow_restored = snapshot_toolbar(page)

    return ToolbarSnapshots(
        desktop_browse=desktop_browse,
        desktop_viewer=desktop_viewer,
        desktop_restored=desktop_restored,
        narrow_closed=narrow_closed,
        narrow_open=narrow_open,
        narrow_restored=narrow_restored,
    )


def toolbar_slot_deltas(snapshots: ToolbarSnapshots) -> dict[str, float]:
    slot_deltas: dict[str, float] = {}
    for slot_name in ("back", "refresh", "nav", "upload", "search-desktop", "search-toggle"):
        comparisons = [
            delta
            for delta in (
                anchor_delta(snapshots.desktop_browse, snapshots.desktop_restored, slot_name),
                anchor_delta(snapshots.narrow_closed, snapshots.narrow_open, slot_name),
                anchor_delta(snapshots.narrow_closed, snapshots.narrow_restored, slot_name),
            )
            if delta is not None
        ]
        if comparisons:
            slot_deltas[slot_name] = max(comparisons)
    return slot_deltas


def toolbar_size_deltas(snapshots: ToolbarSnapshots) -> dict[str, float]:
    return {
        "desktop_browse_round_trip_height_delta": state_delta(
            snapshots.desktop_browse,
            snapshots.desktop_restored,
            "toolbarHeight",
        ),
        "desktop_browse_round_trip_var_delta": state_delta(
            snapshots.desktop_browse,
            snapshots.desktop_restored,
            "toolbarVarPx",
        ),
        "narrow_search_round_trip_height_delta": state_delta(
            snapshots.narrow_closed,
            snapshots.narrow_restored,
            "toolbarHeight",
        ),
        "narrow_search_round_trip_var_delta": state_delta(
            snapshots.narrow_closed,
            snapshots.narrow_restored,
            "toolbarVarPx",
        ),
    }


def intentional_toolbar_size_changes(snapshots: ToolbarSnapshots) -> dict[str, float]:
    return {
        "narrow_search_open_height_delta": state_delta(
            snapshots.narrow_closed,
            snapshots.narrow_open,
            "toolbarHeight",
        ),
        "narrow_search_open_var_delta": state_delta(
            snapshots.narrow_closed,
            snapshots.narrow_open,
            "toolbarVarPx",
        ),
    }


def toolbar_violations(
    snapshots: ToolbarSnapshots,
    *,
    max_anchor_delta: float,
    max_toolbar_delta: float,
    max_delta_px: float,
) -> list[str]:
    violations: list[str] = []
    if max_anchor_delta > max_delta_px:
        violations.append(
            f"anchor delta {max_anchor_delta:.3f}px exceeded threshold {max_delta_px:.3f}px: "
            f"{toolbar_slot_deltas(snapshots)!r}"
        )
    if max_toolbar_delta > max_delta_px:
        violations.append(
            f"toolbar delta {max_toolbar_delta:.3f}px exceeded threshold {max_delta_px:.3f}px: "
            f"{toolbar_size_deltas(snapshots)!r}"
        )

    assert_hidden_control_state(snapshots.desktop_browse, "back", "desktop browse state", violations)
    assert_hidden_control_state(snapshots.desktop_viewer, "refresh", "desktop viewer state", violations)
    assert_hidden_control_state(snapshots.desktop_viewer, "upload", "desktop viewer state", violations)
    assert_hidden_control_state(snapshots.desktop_viewer, "search-desktop", "desktop viewer state", violations)
    assert_hidden_control_state(snapshots.narrow_closed, "search-mobile", "narrow browse closed state", violations)
    if snapshots.narrow_closed.get("searchRowPointerEvents") != "none":
        violations.append("narrow browse closed state: expected search-row pointer-events=none")
    if snapshots.narrow_open.get("searchRowPointerEvents") == "none":
        violations.append("narrow browse open state: expected search-row pointer-events to be interactive")
    intentional_changes = intentional_toolbar_size_changes(snapshots)
    if intentional_changes != {
        "narrow_search_open_height_delta": 48.0,
        "narrow_search_open_var_delta": 48.0,
    }:
        violations.append(
            f"narrow search did not use its declared 48px reserve: {intentional_changes!r}"
        )
    violations.extend(cold_first_frame_violations(snapshots.cold_first_frames))
    violations.extend(snapshots.surface_stability.get("violations", []))
    return violations


def toolbar_result(snapshots: ToolbarSnapshots, max_delta_px: float) -> ProbeResult:
    slot_deltas = toolbar_slot_deltas(snapshots)
    toolbar_deltas = toolbar_size_deltas(snapshots)
    max_anchor_delta = max(
        max(slot_deltas.values(), default=0.0),
        float(snapshots.surface_stability.get("max_anchor_delta_px", 0.0)),
    )
    max_toolbar_delta = max(toolbar_deltas.values(), default=0.0)
    violations = toolbar_violations(
        snapshots,
        max_anchor_delta=max_anchor_delta,
        max_toolbar_delta=max_toolbar_delta,
        max_delta_px=max_delta_px,
    )
    if violations:
        raise SmokeFailure("; ".join(violations))
    return ProbeResult(
        scenario="toolbar",
        max_delta_px=max_delta_px,
        max_anchor_delta_px=max_anchor_delta,
        max_toolbar_delta_px=max_toolbar_delta,
        checks={
            "slot_deltas_px": slot_deltas,
            "toolbar_deltas_px": toolbar_deltas,
            "intentional_toolbar_changes_px": intentional_toolbar_size_changes(snapshots),
            "desktop_browse_snapshot": snapshots.desktop_browse,
            "desktop_viewer_snapshot": snapshots.desktop_viewer,
            "desktop_restored_snapshot": snapshots.desktop_restored,
            "narrow_closed_snapshot": snapshots.narrow_closed,
            "narrow_open_snapshot": snapshots.narrow_open,
            "narrow_restored_snapshot": snapshots.narrow_restored,
            "cold_first_frames": snapshots.cold_first_frames,
            "surface_stability": snapshots.surface_stability,
            "violations": violations,
        },
    )


def run_toolbar_probe(base_url: str, max_delta_px: float, browser_timeout_ms: float) -> ProbeResult:
    playwright_error, playwright_timeout_error, sync_playwright = import_playwright()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            cold_first_frames = capture_cold_first_frames(
                browser,
                base_url=base_url,
                browser_timeout_ms=browser_timeout_ms,
            )
            context = browser.new_context(viewport={"width": 1120, "height": 840})
            page = context.new_page()
            page.set_default_timeout(browser_timeout_ms)
            snapshots = exercise_toolbar_probe(
                page,
                base_url=base_url,
                browser_timeout_ms=browser_timeout_ms,
                playwright_timeout_error=playwright_timeout_error,
                playwright_error=playwright_error,
            )
            snapshots.cold_first_frames = cold_first_frames
            context.close()
            surface_context = browser.new_context(viewport={"width": 1440, "height": 920})
            surface_context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base_url)
            surface_context.add_init_script(SURFACE_STABILITY_INIT_SCRIPT)
            surface_context.route(
                "**/embeddings",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"embeddings":[{"name":"probe","dimension":4,"dtype":"float32","metric":"cosine"}],"rejected":[]}',
                ),
            )
            surface_page = surface_context.new_page()
            surface_page.set_default_timeout(browser_timeout_ms)
            snapshots.surface_stability = exercise_surface_stability(
                surface_page,
                base_url=base_url,
                timeout_ms=browser_timeout_ms,
            )
            surface_context.close()
            browser.close()
    except playwright_timeout_error as exc:
        raise SmokeFailure(f"playwright timeout: {exc}") from exc
    except playwright_error as exc:
        raise SmokeFailure(f"playwright probe failed: {exc}") from exc
    return toolbar_result(snapshots, max_delta_px)
