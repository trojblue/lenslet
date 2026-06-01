from __future__ import annotations

from typing import Any

from scripts.browser.responsive_geometry.errors import ResponsiveGeometryFailure
from scripts.browser.responsive_geometry.types import Scenario


def scenario_state(scenario: Scenario) -> dict[str, Any]:
    return {
        "width": scenario.width,
        "height": scenario.height,
        "storage": dict(scenario.storage),
        "openMobileSearch": scenario.open_mobile_search,
        "hasTouch": scenario.has_touch,
        "selectFirst": scenario.select_first,
        "assertInspector": scenario.assert_inspector,
    }


def _snapshot_shell_layout(page: Any, name: str, state: dict[str, Any]) -> dict[str, Any]:
    return page.evaluate(
        """({ name, state }) => {
          const shell = document.querySelector('.app-shell');
          if (!shell) return { name, missingShell: true };
          const shellStyle = getComputedStyle(shell);
          const doc = document.documentElement;
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
          const rectFor = (selector) => {
            const el = document.querySelector(selector);
            if (!el) return null;
            return rectPayload(el.getBoundingClientRect());
          };
          return {
            name,
            state,
            viewport: { width: window.innerWidth, height: window.innerHeight },
            browser: {
              devicePixelRatio: window.devicePixelRatio,
              visualViewportScale: window.visualViewport?.scale ?? null,
              url: window.location.href,
            },
            media: {
              coarsePointer: window.matchMedia('(pointer: coarse)').matches,
            },
            layout: {
              mode: shell.getAttribute('data-layout-mode'),
              shortHeight: shell.getAttribute('data-short-height'),
              leftSuppressionReason: shell.getAttribute('data-left-suppression-reason'),
              rightSuppressionReason: shell.getAttribute('data-right-suppression-reason'),
              inspectorSuppressionReason: shell.getAttribute('data-inspector-suppression-reason'),
              overlayMode: shell.getAttribute('data-overlay-mode'),
              mobileSearchOpen: shell.getAttribute('data-mobile-search-open'),
              mobileDrawerOpen: shell.getAttribute('data-mobile-drawer-open'),
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
              gridTopStack: rectFor('[data-grid-top-stack]'),
              statusBand: rectFor('[data-grid-top-band="status"]'),
              filtersBand: rectFor('[data-grid-top-band="filters"]'),
              leftSidebar: rectFor('.app-left-panel'),
              rightSidebar: rectFor('.app-right-panel'),
              gridShell: rectFor('.grid-shell'),
              mobileDrawer: rectFor('.mobile-drawer'),
              overlay: rectFor('[role="dialog"][aria-label="Image viewer"], [role="dialog"][aria-label="Compare images"]'),
              overlayStage: rectFor('.compare-stage, [role="dialog"][aria-label="Image viewer"]'),
              viewer: rectFor('[role="dialog"][aria-label="Image viewer"]'),
              compare: rectFor('[role="dialog"][aria-label="Compare images"]'),
              compareStage: rectFor('.compare-stage'),
              themeMenu: rectFor('[role="menu"][aria-label="Theme settings"]'),
              inspectorPreview: rectFor('.inspector-preview-card'),
              inspectorStarRow: rectFor('.inspector-star-row'),
            },
          };
        }""",
        {"name": name, "state": state},
    )


def _snapshot_media_images(page: Any) -> dict[str, Any]:
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
          const imageFor = (selector) => {
            const el = document.querySelector(selector);
            if (!(el instanceof HTMLImageElement)) return null;
            const style = getComputedStyle(el);
            return {
              selector,
              src: el.currentSrc || el.src || null,
              currentPath: el.getAttribute("data-current-path"),
              complete: el.complete,
              naturalWidth: el.naturalWidth,
              naturalHeight: el.naturalHeight,
              opacity: Number(style.opacity || "0"),
              display: style.display,
              visibility: style.visibility,
              rect: rectPayload(el.getBoundingClientRect()),
            };
          };
          return {
            viewer: imageFor('[role="dialog"][aria-label="Image viewer"] img[data-viewer-image="full"]'),
            viewerThumb: imageFor('[role="dialog"][aria-label="Image viewer"] img[alt="thumb"]'),
            compareA: imageFor('[role="dialog"][aria-label="Compare images"] img[data-compare-image="a"]'),
            compareB: imageFor('[role="dialog"][aria-label="Compare images"] img[data-compare-image="b"]'),
            compareThumbA: imageFor('[role="dialog"][aria-label="Compare images"] img[alt="thumb A"]'),
            compareThumbB: imageFor('[role="dialog"][aria-label="Compare images"] img[alt="thumb B"]'),
          };
        }"""
    )


def _snapshot_focus_selection_storage(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """() => {
          const elementText = (el) => el ? (el.textContent || '').replace(/\\s+/g, ' ').trim() : '';
          const describeElement = (el) => {
            if (!el) return null;
            return {
              tag: el.tagName,
              id: el.id || null,
              className: typeof el.className === 'string' ? el.className : null,
              ariaLabel: el.getAttribute('aria-label'),
              dataToolbarControl: el.getAttribute('data-toolbar-control'),
              inBrowseShell: Boolean(el.closest('[data-browse-shell]')),
              inToolbar: Boolean(el.closest('.toolbar-shell')),
              inLeftSidebar: Boolean(el.closest('.app-left-panel')),
              inRightSidebar: Boolean(el.closest('.app-right-panel')),
              inMobileDrawer: Boolean(el.closest('.mobile-drawer')),
              inGrid: Boolean(el.closest('[role="grid"][aria-label="Gallery"]')),
              inOverlayDialog: Boolean(el.closest('[role="dialog"][aria-modal="true"]')),
            };
          };
          return {
            focus: {
              activeElement: describeElement(document.activeElement),
              browseShellInert: document.querySelector('[data-browse-shell]')?.hasAttribute('inert') ?? false,
              browseShellAriaHidden: document.querySelector('[data-browse-shell]')?.getAttribute('aria-hidden') ?? null,
              toolbarInert: document.querySelector('.toolbar-shell')?.hasAttribute('inert') ?? false,
              toolbarAriaHidden: document.querySelector('.toolbar-shell')?.getAttribute('aria-hidden') ?? null,
            },
            selection: {
              ariaSelectedCount: document.querySelectorAll('[role="gridcell"][aria-selected="true"]').length,
              liveText: elementText(document.querySelector('[aria-live="polite"]')),
            },
            themeMenu: {
              labels: Array.from(document.querySelectorAll('[role="menu"][aria-label="Theme settings"] [role^="menuitem"]'))
                .map((el) => elementText(el))
                .filter(Boolean),
            },
            storage: {
              leftOpen: localStorage.getItem('leftOpen'),
              rightOpen: localStorage.getItem('rightOpen'),
              leftFoldersWidth: localStorage.getItem('leftW.folders'),
              leftMetricsWidth: localStorage.getItem('leftW.metrics'),
              rightWidth: localStorage.getItem('rightW'),
            },
          };
        }"""
    )


def _snapshot_side_panels(page: Any) -> dict[str, Any]:
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
          const rectFor = (selector) => {
            const el = document.querySelector(selector);
            if (!el) return null;
            return rectPayload(el.getBoundingClientRect());
          };
          const elementText = (el) => el ? (el.textContent || '').replace(/\\s+/g, ' ').trim() : '';
          const panel = document.querySelector('.app-right-panel');
          const inspectorChecks = panel
            ? Array.from(panel.querySelectorAll([
                '.inspector-preview-card',
                '.inspector-star-row',
                '.inspector-section-header',
                '.ui-kv-row',
                '.inspector-field',
              ].join(','))).map((el) => {
                const rect = el.getBoundingClientRect();
                const panelRect = panel.getBoundingClientRect();
                return {
                  selector: el.className,
                  left: rect.left,
                  right: rect.right,
                  width: rect.width,
                  overflowsPanel: rect.left < panelRect.left - 1 || rect.right > panelRect.right + 1,
                };
              })
            : [];
          const leftPanel = document.querySelector('.app-left-panel');
          const selectedMetricsHeader = leftPanel
            ? Array.from(leftPanel.querySelectorAll('.ui-section-title'))
              .find((el) => elementText(el) === 'Selected metrics')
            : null;
          const selectedMetricsCard = selectedMetricsHeader?.closest('.ui-card') || null;
          const selectedMetricsChecks = leftPanel && selectedMetricsCard
            ? Array.from(selectedMetricsCard.querySelectorAll('*')).map((el) => {
              const rect = el.getBoundingClientRect();
              const panelRect = leftPanel.getBoundingClientRect();
              return {
                className: typeof el.className === 'string' ? el.className : null,
                text: elementText(el).slice(0, 120),
                rect: rectPayload(rect),
                overflowsPanel: rect.left < panelRect.left - 1 || rect.right > panelRect.right + 1,
              };
            })
            : [];
          const leftPanelContentChecks = leftPanel
            ? Array.from(leftPanel.querySelectorAll('*'))
              .filter((el) => !el.closest('.sidebar-resize-handle'))
              .map((el) => {
                const rect = el.getBoundingClientRect();
                const panelRect = leftPanel.getBoundingClientRect();
                return {
                  className: typeof el.className === 'string' ? el.className : null,
                  text: elementText(el).slice(0, 120),
                  rect: rectPayload(rect),
                  overflowsPanel: rect.left < panelRect.left - 1 || rect.right > panelRect.right + 1,
                };
              })
            : [];
          const activeLeftTool = leftPanel
            ? (
              leftPanel.querySelector('button[aria-label="Metrics and Filters"]')?.getAttribute('aria-pressed') === 'true'
                ? 'metrics'
                : leftPanel.querySelector('button[aria-label="Folders"]')?.getAttribute('aria-pressed') === 'true'
                  ? 'folders'
                  : null
            )
            : null;
          return {
            leftPanel: leftPanel ? {
              clientWidth: leftPanel.clientWidth,
              scrollWidth: leftPanel.scrollWidth,
              rect: rectFor('.app-left-panel'),
              contentOpen: leftPanel.getAttribute('data-left-content-open'),
              activeTool: activeLeftTool,
              horizontalOverflow: leftPanel.scrollWidth > leftPanel.clientWidth + 1,
              contentOverflowCount: leftPanelContentChecks.filter((check) => check.overflowsPanel).length,
              contentOverflowExamples: leftPanelContentChecks.filter((check) => check.overflowsPanel).slice(0, 6),
              selectedMetricsCard: selectedMetricsCard ? {
                clientWidth: selectedMetricsCard.clientWidth,
                scrollWidth: selectedMetricsCard.scrollWidth,
                rect: rectPayload(selectedMetricsCard.getBoundingClientRect()),
                text: elementText(selectedMetricsCard).slice(0, 320),
                overflowsPanel: (() => {
                  const rect = selectedMetricsCard.getBoundingClientRect();
                  const panelRect = leftPanel.getBoundingClientRect();
                  return rect.left < panelRect.left - 1 || rect.right > panelRect.right + 1;
                })(),
                childOverflowCount: selectedMetricsChecks.filter((check) => check.overflowsPanel).length,
                checks: selectedMetricsChecks,
              } : null,
            } : null,
            inspector: panel ? {
              clientWidth: panel.clientWidth,
              scrollWidth: panel.scrollWidth,
              rect: rectFor('.app-right-panel'),
              checks: inspectorChecks,
            } : null,
          };
        }"""
    )


def _snapshot_toolbar_controls(page: Any) -> list[dict[str, Any]]:
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
          return Array.from(document.querySelectorAll('[data-toolbar-control]')).map((el) => {
            const rect = el.getBoundingClientRect();
            const style = getComputedStyle(el);
            const centerX = rect.left + rect.width / 2;
            const centerY = rect.top + rect.height / 2;
            const hit = rect.width > 0 && rect.height > 0
              ? document.elementFromPoint(centerX, centerY)
              : null;
            const focusTarget = el.matches('button,input,select,textarea,a,[tabindex]')
              ? el
              : el.querySelector('button,input,select,textarea,a,[tabindex]:not([tabindex="-1"])');
            const focusStyle = focusTarget ? getComputedStyle(focusTarget) : null;
            return {
              name: el.getAttribute('data-toolbar-control') || el.getAttribute('aria-label') || '',
              ariaHidden: el.getAttribute('aria-hidden'),
              disabled: Boolean(el.disabled),
              visible: style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0,
              hitTargetOk: Boolean(hit && (el === hit || el.contains(hit) || hit.closest('[data-toolbar-control]') === el)),
              focusDisabled: Boolean(focusTarget && focusTarget.disabled),
              keyboardFocusable: Boolean(
                focusTarget &&
                !focusTarget.disabled &&
                focusTarget.getAttribute('aria-hidden') !== 'true' &&
                focusTarget.getAttribute('tabindex') !== '-1' &&
                focusStyle &&
                focusStyle.display !== 'none' &&
                focusStyle.visibility !== 'hidden'
              ),
              rect: rectPayload(rect),
            };
          });
        }"""
    )


def collect_snapshot(page: Any, name: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
    snapshot = _snapshot_shell_layout(page, name, state or {})
    if not isinstance(snapshot, dict) or snapshot.get("missingShell"):
        raise ResponsiveGeometryFailure(f"App shell was not available for scenario {name!r}.")
    snapshot["images"] = _snapshot_media_images(page)
    snapshot.update(_snapshot_focus_selection_storage(page))
    snapshot.update(_snapshot_side_panels(page))
    snapshot["toolbarControls"] = _snapshot_toolbar_controls(page)
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


def _rect(control: dict[str, Any]) -> dict[str, float]:
    rect = control.get("rect")
    if not isinstance(rect, dict):
        return {}
    return rect


def _visible_toolbar_controls(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    controls = snapshot.get("toolbarControls")
    if not isinstance(controls, list):
        raise ResponsiveGeometryFailure(f"Missing toolbar control evidence for {snapshot.get('name')!r}.")
    return [
        control for control in controls
        if isinstance(control, dict)
        and control.get("visible")
        and control.get("ariaHidden") != "true"
    ]


def assert_no_visible_control_overlap(snapshot: dict[str, Any]) -> None:
    controls = _visible_toolbar_controls(snapshot)
    for index, left in enumerate(controls):
        left_rect = _rect(left)
        for right in controls[index + 1:]:
            right_rect = _rect(right)
            x_overlap = min(float(left_rect.get("right", 0)), float(right_rect.get("right", 0))) - max(
                float(left_rect.get("left", 0)),
                float(right_rect.get("left", 0)),
            )
            y_overlap = min(float(left_rect.get("bottom", 0)), float(right_rect.get("bottom", 0))) - max(
                float(left_rect.get("top", 0)),
                float(right_rect.get("top", 0)),
            )
            if x_overlap > 1 and y_overlap > 1:
                raise ResponsiveGeometryFailure(
                    "Visible toolbar controls overlap in "
                    f"{snapshot.get('name')}: {left.get('name')} with {right.get('name')}."
                )


def assert_hidden_toolbar_controls_not_interactable(snapshot: dict[str, Any]) -> None:
    controls = snapshot.get("toolbarControls")
    if not isinstance(controls, list):
        raise ResponsiveGeometryFailure(f"Missing toolbar control evidence for {snapshot.get('name')!r}.")
    offenders = [
        str(control.get("name"))
        for control in controls
        if isinstance(control, dict)
        and not control.get("visible")
        and control.get("ariaHidden") != "true"
        and (control.get("hitTargetOk") or control.get("keyboardFocusable"))
    ]
    if offenders:
        raise ResponsiveGeometryFailure(
            f"Hidden toolbar controls are still reachable in {snapshot.get('name')}: "
            f"{', '.join(sorted(offenders))}."
        )


def _parse_px(raw: Any) -> float:
    if not isinstance(raw, str):
        return 0.0
    try:
        return float(raw.strip().removesuffix("px"))
    except ValueError:
        return 0.0


def _parse_float(raw: Any) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def _require_rect(snapshot: dict[str, Any], rect_name: str) -> dict[str, Any]:
    rects = snapshot.get("rects")
    if not isinstance(rects, dict) or not isinstance(rects.get(rect_name), dict):
        raise ResponsiveGeometryFailure(
            f"Missing {rect_name} rect in {snapshot.get('name')!r}: {rects!r}."
        )
    return rects[rect_name]


def _rect_width(rect: dict[str, Any]) -> float:
    return _parse_float(rect.get("width"))


def _rect_left(rect: dict[str, Any]) -> float:
    return _parse_float(rect.get("left"))


def _rect_right(rect: dict[str, Any]) -> float:
    return _parse_float(rect.get("right"))


def _assert_close(
    *,
    actual: float,
    expected: float,
    tolerance: float,
    label: str,
    snapshot_name: Any,
) -> None:
    if abs(actual - expected) > tolerance:
        raise ResponsiveGeometryFailure(
            f"{label} mismatch in {snapshot_name}: actual={actual:.2f}, expected={expected:.2f}."
        )


def assert_mobile_search_reserved(snapshot: dict[str, Any]) -> None:
    css_vars = snapshot.get("cssVars")
    rects = snapshot.get("rects")
    if not isinstance(css_vars, dict) or not isinstance(rects, dict):
        raise ResponsiveGeometryFailure(f"Missing search reserve evidence for {snapshot.get('name')!r}.")
    toolbar_height = _parse_px(css_vars.get("toolbarHeight"))
    if toolbar_height < 96:
        raise ResponsiveGeometryFailure(
            f"Mobile search did not reserve declared toolbar height in {snapshot.get('name')}: {toolbar_height}px."
        )
    controls = {control.get("name"): control for control in _visible_toolbar_controls(snapshot)}
    if not controls.get("search-mobile"):
        raise ResponsiveGeometryFailure(f"Mobile search input is not visible in {snapshot.get('name')}.")
    toolbar_rect = rects.get("toolbar")
    grid_rect = rects.get("gridShell")
    if not isinstance(toolbar_rect, dict) or not isinstance(grid_rect, dict):
        raise ResponsiveGeometryFailure(f"Missing toolbar/grid rects for {snapshot.get('name')!r}.")
    if float(grid_rect.get("top", 0)) + 1 < float(toolbar_rect.get("bottom", 0)):
        raise ResponsiveGeometryFailure(
            f"Grid starts under the mobile search toolbar in {snapshot.get('name')}."
        )
    status_rect = rects.get("statusBand")
    if isinstance(status_rect, dict) and float(status_rect.get("height", 0)) > 1:
        if float(status_rect.get("top", 0)) + 1 < float(toolbar_rect.get("bottom", 0)):
            raise ResponsiveGeometryFailure(
                f"Status band starts under the mobile search toolbar in {snapshot.get('name')}."
            )


REQUIRED_DRAWER_CONTROLS = {
    "drawer-layout-grid",
    "drawer-layout-adaptive",
    "drawer-theme",
    "drawer-sort",
    "drawer-sort-dir",
    "drawer-filters",
    "drawer-refresh",
    "drawer-left-panel",
    "drawer-right-panel",
}

OPTIONAL_DRAWER_CONTROLS = {
    "drawer-upload",
}


def assert_mobile_drawer_reachable(snapshot: dict[str, Any]) -> None:
    layout = snapshot.get("layout")
    if not isinstance(layout, dict) or layout.get("mobileDrawerOpen") != "true":
        raise ResponsiveGeometryFailure(f"Mobile drawer is not open in {snapshot.get('name')!r}.")
    viewport = snapshot.get("viewport")
    viewport_width = float(viewport.get("width", 0)) if isinstance(viewport, dict) else 0.0
    required_controls = set(REQUIRED_DRAWER_CONTROLS)
    if viewport_width <= 767:
        required_controls.add("drawer-select")
    controls = {control.get("name"): control for control in _visible_toolbar_controls(snapshot)}
    missing = sorted(name for name in required_controls if name not in controls)
    if missing:
        raise ResponsiveGeometryFailure(
            f"Mobile drawer controls are missing in {snapshot.get('name')}: {', '.join(missing)}."
        )
    controls_to_check = required_controls | (OPTIONAL_DRAWER_CONTROLS & controls.keys())
    blocked = [
        name for name in sorted(controls_to_check)
        if not controls[name].get("hitTargetOk")
        or (not controls[name].get("focusDisabled") and not controls[name].get("keyboardFocusable"))
    ]
    if blocked:
        raise ResponsiveGeometryFailure(
            f"Mobile drawer controls are not pointer/keyboard reachable in {snapshot.get('name')}: "
            f"{', '.join(blocked)}."
        )


def assert_theme_settings_reachable(snapshot: dict[str, Any]) -> None:
    rects = snapshot.get("rects")
    theme_menu = snapshot.get("themeMenu")
    if not isinstance(rects, dict) or not isinstance(rects.get("themeMenu"), dict):
        raise ResponsiveGeometryFailure(f"Theme settings menu is not visible in {snapshot.get('name')}.")
    labels = theme_menu.get("labels") if isinstance(theme_menu, dict) else None
    if not isinstance(labels, list):
        raise ResponsiveGeometryFailure(f"Missing theme settings labels in {snapshot.get('name')}.")
    required = ("Autoload image metadata", "Order compare by selection")
    missing = sorted(label for label in required if not any(label in candidate for candidate in labels))
    if missing:
        raise ResponsiveGeometryFailure(
            f"Theme settings drawer controls are missing in {snapshot.get('name')}: {missing!r}."
        )


def assert_overlay_isolated(snapshot: dict[str, Any], expected_mode: str) -> None:
    _layout, rects, focus = _require_overlay_parts(snapshot, expected_mode)
    _assert_overlay_focus_state(snapshot, focus, expected_mode)
    _assert_overlay_edges(snapshot, rects)


def _require_overlay_parts(
    snapshot: dict[str, Any],
    expected_mode: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    layout = snapshot.get("layout")
    rects = snapshot.get("rects")
    focus = snapshot.get("focus")
    if not isinstance(layout, dict) or layout.get("overlayMode") != expected_mode:
        raise ResponsiveGeometryFailure(
            f"Expected {expected_mode} overlay mode in {snapshot.get('name')}, got {layout!r}."
        )
    if not isinstance(rects, dict) or not isinstance(rects.get("overlay"), dict):
        raise ResponsiveGeometryFailure(f"Missing overlay rect for {snapshot.get('name')}.")
    if not isinstance(focus, dict):
        raise ResponsiveGeometryFailure(f"Missing focus evidence for {snapshot.get('name')}.")
    return layout, rects, focus


def _assert_overlay_focus_state(
    snapshot: dict[str, Any],
    focus: dict[str, Any],
    expected_mode: str,
) -> None:
    if focus.get("browseShellInert") is not True or focus.get("browseShellAriaHidden") != "true":
        raise ResponsiveGeometryFailure(f"Browse shell is not inert under overlay in {snapshot.get('name')}.")
    if expected_mode == "compare" and (
        focus.get("toolbarInert") is not True or focus.get("toolbarAriaHidden") != "true"
    ):
        raise ResponsiveGeometryFailure(f"Compare overlay did not inert the toolbar in {snapshot.get('name')}.")
    if expected_mode == "viewer" and (
        focus.get("toolbarInert") is True or focus.get("toolbarAriaHidden") == "true"
    ):
        raise ResponsiveGeometryFailure(f"Viewer overlay disabled viewer toolbar chrome in {snapshot.get('name')}.")
    active = focus.get("activeElement")
    if isinstance(active, dict) and active.get("inBrowseShell"):
        raise ResponsiveGeometryFailure(f"Focus reached browse shell under overlay in {snapshot.get('name')}: {active!r}.")


def _assert_overlay_edges(snapshot: dict[str, Any], rects: dict[str, Any]) -> None:
    overlay_rect = rects["overlay"]
    viewport = snapshot.get("viewport", {})
    css_vars = snapshot.get("cssVars", {})
    expected_left = _parse_px(css_vars.get("overlayLeft") if isinstance(css_vars, dict) else None)
    expected_right = _parse_px(css_vars.get("overlayRight") if isinstance(css_vars, dict) else None)
    viewport_width = float(viewport.get("width", 0)) if isinstance(viewport, dict) else 0.0
    if float(overlay_rect.get("left", 0)) > expected_left + 1:
        raise ResponsiveGeometryFailure(f"Overlay left edge is squeezed in {snapshot.get('name')}: {overlay_rect!r}.")
    if float(overlay_rect.get("right", 0)) < viewport_width - expected_right - 1:
        raise ResponsiveGeometryFailure(f"Overlay right edge is squeezed in {snapshot.get('name')}: {overlay_rect!r}.")


def assert_side_regions_visible(snapshot: dict[str, Any]) -> None:
    layout = snapshot.get("layout")
    if not isinstance(layout, dict):
        raise ResponsiveGeometryFailure(f"Missing layout evidence for {snapshot.get('name')!r}.")
    if _parse_float(layout.get("effectiveLeftWidth")) <= 0:
        raise ResponsiveGeometryFailure(f"Left side region is not visible in {snapshot.get('name')}: {layout!r}.")
    if _parse_float(layout.get("effectiveRightWidth")) <= 0:
        raise ResponsiveGeometryFailure(f"Right side region is not visible in {snapshot.get('name')}: {layout!r}.")
    left = _require_rect(snapshot, "leftSidebar")
    right = _require_rect(snapshot, "rightSidebar")
    if _rect_width(left) <= 1 or _rect_width(right) <= 1:
        raise ResponsiveGeometryFailure(
            f"Side region rects are not visible in {snapshot.get('name')}: left={left!r}, right={right!r}."
        )


def assert_overlay_contained_to_center(
    before: dict[str, Any],
    after: dict[str, Any],
    expected_mode: str,
) -> None:
    assert_side_regions_visible(before)
    assert_side_regions_visible(after)
    assert_overlay_isolated(after, expected_mode)

    before_layout = before.get("layout")
    after_layout = after.get("layout")
    if not isinstance(before_layout, dict) or not isinstance(after_layout, dict):
        raise ResponsiveGeometryFailure(f"Missing layout evidence for overlay containment in {after.get('name')}.")
    if after_layout.get("leftSuppressionReason") == "overlay-active":
        raise ResponsiveGeometryFailure(f"Overlay suppressed the left side region in {after.get('name')}.")
    if after_layout.get("rightSuppressionReason") == "overlay-active":
        raise ResponsiveGeometryFailure(f"Overlay suppressed the right side region in {after.get('name')}.")

    before_left = _require_rect(before, "leftSidebar")
    before_right = _require_rect(before, "rightSidebar")
    after_left = _require_rect(after, "leftSidebar")
    after_right = _require_rect(after, "rightSidebar")
    for label, before_rect, after_rect in (
        ("left side width", before_left, after_left),
        ("right side width", before_right, after_right),
    ):
        _assert_close(
            actual=_rect_width(after_rect),
            expected=_rect_width(before_rect),
            tolerance=1.0,
            label=label,
            snapshot_name=after.get("name"),
        )

    grid = _require_rect(after, "gridShell")
    overlay = _require_rect(after, "overlay")
    _assert_close(
        actual=_rect_left(overlay),
        expected=_rect_left(grid),
        tolerance=1.0,
        label="overlay left edge versus grid shell",
        snapshot_name=after.get("name"),
    )
    _assert_close(
        actual=_rect_right(overlay),
        expected=_rect_right(grid),
        tolerance=1.0,
        label="overlay right edge versus grid shell",
        snapshot_name=after.get("name"),
    )

    viewport = after.get("viewport")
    viewport_width = _parse_float(viewport.get("width")) if isinstance(viewport, dict) else 0.0
    if viewport_width > 0 and _rect_width(overlay) >= viewport_width - 1:
        raise ResponsiveGeometryFailure(
            f"Overlay spans the full viewport despite visible side regions in {after.get('name')}: {overlay!r}."
        )

    if expected_mode == "compare":
        stage = _require_rect(after, "compareStage")
        if _rect_left(stage) < _rect_left(overlay) - 1 or _rect_right(stage) > _rect_right(overlay) + 1:
            raise ResponsiveGeometryFailure(
                f"Compare stage escaped contained overlay in {after.get('name')}: "
                f"stage={stage!r}, overlay={overlay!r}."
            )


def sample_overlay_images(
    page: Any,
    name: str,
    *,
    frames: int = 30,
    interval_ms: int = 35,
) -> dict[str, Any]:
    evidence = page.evaluate(
        """async ({ name, frames, intervalMs }) => {
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
          const readImage = (selector) => {
            const el = document.querySelector(selector);
            if (!(el instanceof HTMLImageElement)) return null;
            const rect = el.getBoundingClientRect();
            const style = getComputedStyle(el);
            return {
              selector,
              src: el.currentSrc || el.src || null,
              currentPath: el.getAttribute("data-current-path"),
              complete: el.complete,
              naturalWidth: el.naturalWidth,
              naturalHeight: el.naturalHeight,
              opacity: Number(style.opacity || "0"),
              display: style.display,
              visibility: style.visibility,
              rect: rectPayload(rect),
            };
          };
          const sleep = () => new Promise((resolve) => {
            requestAnimationFrame(() => window.setTimeout(resolve, intervalMs));
          });
          const startedAt = performance.now();
          const samples = [];
          for (let frame = 0; frame < frames; frame += 1) {
            await sleep();
            samples.push({
              frame,
              elapsedMs: Math.round(performance.now() - startedAt),
              images: {
                viewer: readImage('[role="dialog"][aria-label="Image viewer"] img[data-viewer-image="full"]'),
                compareA: readImage('[role="dialog"][aria-label="Compare images"] img[data-compare-image="a"]'),
                compareB: readImage('[role="dialog"][aria-label="Compare images"] img[data-compare-image="b"]'),
              },
            });
          }
          return { name, frames, intervalMs, samples };
        }""",
        {"name": name, "frames": frames, "intervalMs": interval_ms},
    )
    if not isinstance(evidence, dict):
        raise ResponsiveGeometryFailure(f"Failed to sample overlay images for {name}.")
    return evidence


def _sample_image_visible(image: Any) -> bool:
    if not isinstance(image, dict):
        return False
    rect = image.get("rect")
    return (
        bool(image.get("complete"))
        and _parse_float(image.get("naturalWidth")) > 0
        and _parse_float(image.get("naturalHeight")) > 0
        and _parse_float(image.get("opacity")) > 0.05
        and image.get("display") != "none"
        and image.get("visibility") != "hidden"
        and isinstance(rect, dict)
        and _rect_width(rect) > 1
        and _parse_float(rect.get("height")) > 1
    )


def assert_overlay_image_stable(
    samples: dict[str, Any],
    required_images: tuple[str, ...],
    expected_paths: dict[str, str] | None = None,
) -> None:
    raw_samples = _require_overlay_image_samples(samples)
    for image_name in required_images:
        expected_path = expected_paths.get(image_name) if expected_paths else None
        _assert_required_overlay_image_stable(samples, raw_samples, image_name, expected_path)


def _require_overlay_image_samples(samples: dict[str, Any]) -> list[Any]:
    raw_samples = samples.get("samples")
    if not isinstance(raw_samples, list) or not raw_samples:
        raise ResponsiveGeometryFailure(f"Missing image samples for {samples.get('name')!r}.")
    return raw_samples


def _sample_overlay_image(sample: Any, image_name: str) -> Any:
    if not isinstance(sample, dict):
        return None
    images = sample.get("images")
    if not isinstance(images, dict):
        return None
    return images.get(image_name)


def _assert_required_overlay_image_stable(
    samples: dict[str, Any],
    raw_samples: list[Any],
    image_name: str,
    expected_path: str | None,
) -> None:
    seen_visible = False
    last_image: Any = None
    for sample in raw_samples:
        image = _sample_overlay_image(sample, image_name)
        last_image = image
        visible = _sample_image_visible(image)
        if visible:
            _assert_overlay_image_path(samples, image_name, image, expected_path)
            seen_visible = True
            continue
        if seen_visible:
            frame = sample.get("frame") if isinstance(sample, dict) else None
            raise ResponsiveGeometryFailure(
                f"{image_name} became invisible after becoming visible in {samples.get('name')}: "
                f"frame={frame}, image={image!r}."
            )
    if not seen_visible:
        raise ResponsiveGeometryFailure(
            f"{image_name} did not become visibly loaded in {samples.get('name')}: last={last_image!r}."
        )


def _assert_overlay_image_path(
    samples: dict[str, Any],
    image_name: str,
    image: Any,
    expected_path: str | None,
) -> None:
    if expected_path is None or not isinstance(image, dict):
        return
    if image.get("currentPath") == expected_path:
        return
    raise ResponsiveGeometryFailure(
        f"{image_name} shows the wrong current path in {samples.get('name')}: "
        f"expected={expected_path!r}, image={image!r}."
    )


def assert_viewer_toolbar_chrome(snapshot: dict[str, Any]) -> None:
    controls = {control.get("name"): control for control in _visible_toolbar_controls(snapshot)}
    back = controls.get("back")
    if not back or not back.get("hitTargetOk") or not back.get("keyboardFocusable"):
        raise ResponsiveGeometryFailure(f"Viewer toolbar back control is not usable in {snapshot.get('name')}.")


def assert_overlay_closed(snapshot: dict[str, Any], expected_name: str) -> None:
    layout = snapshot.get("layout")
    focus = snapshot.get("focus")
    if not isinstance(layout, dict) or layout.get("overlayMode") != "none":
        raise ResponsiveGeometryFailure(f"Overlay did not close in {expected_name}: {layout!r}.")
    if isinstance(focus, dict):
        active = focus.get("activeElement")
        if isinstance(active, dict) and active.get("inOverlayDialog"):
            raise ResponsiveGeometryFailure(f"Focus stayed in closed overlay for {expected_name}: {active!r}.")


def assert_inspector_contained(snapshot: dict[str, Any]) -> None:
    layout = snapshot.get("layout")
    inspector = snapshot.get("inspector")
    if not isinstance(layout, dict):
        raise ResponsiveGeometryFailure(f"Missing layout for {snapshot.get('name')}.")
    if layout.get("effectiveRightWidth") == "0":
        return
    if not isinstance(inspector, dict):
        raise ResponsiveGeometryFailure(f"Missing inspector evidence for {snapshot.get('name')}.")
    scroll_width = float(inspector.get("scrollWidth", 0))
    client_width = float(inspector.get("clientWidth", 0))
    if scroll_width > client_width + 1:
        raise ResponsiveGeometryFailure(
            f"Inspector has horizontal overflow in {snapshot.get('name')}: "
            f"scrollWidth={scroll_width}, clientWidth={client_width}."
        )
    checks = inspector.get("checks")
    if not isinstance(checks, list):
        raise ResponsiveGeometryFailure(f"Missing inspector child checks for {snapshot.get('name')}.")
    overflowing = [check for check in checks if isinstance(check, dict) and check.get("overflowsPanel")]
    if overflowing:
        raise ResponsiveGeometryFailure(
            f"Inspector child escaped panel in {snapshot.get('name')}: {overflowing[:3]!r}."
        )


def assert_metrics_left_760_observed(snapshot: dict[str, Any]) -> None:
    layout, left_panel, effective_left_width = _metrics_left_760_context(snapshot)
    if effective_left_width <= 0:
        _assert_metrics_left_suppression_reason(snapshot, layout)
        return
    _assert_metrics_left_visible_panel(snapshot, left_panel)


def _metrics_left_760_context(snapshot: dict[str, Any]) -> tuple[dict[str, Any], Any, float]:
    _assert_metrics_left_state(snapshot)
    _assert_metrics_left_selection(snapshot)
    _assert_metrics_left_viewport(snapshot)
    _assert_metrics_left_storage(snapshot)
    layout = _require_metrics_left_narrow_layout(snapshot)
    effective_left_width = _parse_px(f"{layout.get('effectiveLeftWidth', '0')}px")
    return layout, snapshot.get("leftPanel"), effective_left_width


def _assert_metrics_left_state(snapshot: dict[str, Any]) -> None:
    state = snapshot.get("state")
    if not isinstance(state, dict) or state.get("activeLeftTool") != "metrics":
        raise ResponsiveGeometryFailure(f"Missing active metrics-left state for {snapshot.get('name')}.")
    if int(state.get("selectedCount", 0)) < 2:
        raise ResponsiveGeometryFailure(f"Metrics-left scenario did not keep selected items in {snapshot.get('name')}.")


def _assert_metrics_left_selection(snapshot: dict[str, Any]) -> None:
    selection = snapshot.get("selection")
    if not isinstance(selection, dict) or int(selection.get("ariaSelectedCount", 0)) < 2:
        raise ResponsiveGeometryFailure(f"Metrics-left DOM selection was not preserved in {snapshot.get('name')}.")


def _assert_metrics_left_viewport(snapshot: dict[str, Any]) -> None:
    viewport = snapshot.get("viewport")
    if not isinstance(viewport, dict) or int(viewport.get("width", 0)) != 760:
        raise ResponsiveGeometryFailure(f"Metrics-left R10 observation must run at 760px: {viewport!r}.")


def _assert_metrics_left_storage(snapshot: dict[str, Any]) -> None:
    storage = snapshot.get("storage")
    if not isinstance(storage, dict) or storage.get("leftOpen") != "1" or storage.get("rightOpen") != "1":
        raise ResponsiveGeometryFailure(
            f"Metrics-left R10 observation must preserve both sidebar preferences: {storage!r}."
        )


def _require_metrics_left_narrow_layout(snapshot: dict[str, Any]) -> dict[str, Any]:
    layout = snapshot.get("layout")
    if not isinstance(layout, dict) or layout.get("mode") != "narrow":
        raise ResponsiveGeometryFailure(f"Metrics-left R10 observation expected narrow mode: {layout!r}.")
    return layout


def _assert_metrics_left_suppression_reason(snapshot: dict[str, Any], layout: dict[str, Any]) -> None:
    if layout.get("leftSuppressionReason") in {"insufficient-center-space", "viewport-too-narrow"}:
        return
    raise ResponsiveGeometryFailure(
        f"Metrics-left panel was suppressed for an unexpected reason in {snapshot.get('name')}: "
        f"{layout!r}."
    )


def _assert_metrics_left_visible_panel(snapshot: dict[str, Any], left_panel: Any) -> None:
    if not isinstance(left_panel, dict):
        raise ResponsiveGeometryFailure(f"Metrics-left panel is visible but missing evidence in {snapshot.get('name')}.")
    if left_panel.get("activeTool") != "metrics":
        raise ResponsiveGeometryFailure(f"Left panel did not render Metrics tool in {snapshot.get('name')}.")
    if left_panel.get("horizontalOverflow"):
        raise ResponsiveGeometryFailure(f"Metrics-left panel has horizontal overflow in {snapshot.get('name')}.")
    selected_card = left_panel.get("selectedMetricsCard")
    if not isinstance(selected_card, dict):
        raise ResponsiveGeometryFailure(f"Selected metrics summary is missing in {snapshot.get('name')}.")
    if selected_card.get("overflowsPanel") or int(selected_card.get("childOverflowCount", 0)) > 0:
        raise ResponsiveGeometryFailure(
            f"Selected metrics summary escaped the left panel in {snapshot.get('name')}: {selected_card!r}."
        )


def assert_visible_metrics_left_contained(snapshot: dict[str, Any]) -> None:
    selection = snapshot.get("selection")
    if not isinstance(selection, dict) or int(selection.get("ariaSelectedCount", 0)) < 2:
        raise ResponsiveGeometryFailure(f"Visible metrics-left scenario has fewer than 2 selected items in {snapshot.get('name')}.")
    left_panel = snapshot.get("leftPanel")
    if not isinstance(left_panel, dict):
        raise ResponsiveGeometryFailure(f"Visible metrics-left panel is missing in {snapshot.get('name')}.")
    if left_panel.get("activeTool") != "metrics":
        raise ResponsiveGeometryFailure(f"Visible left panel did not render Metrics tool in {snapshot.get('name')}.")
    if int(left_panel.get("contentOverflowCount", 0)) > 0:
        raise ResponsiveGeometryFailure(
            f"Visible metrics-left content escaped the panel in {snapshot.get('name')}: "
            f"{left_panel.get('contentOverflowExamples')!r}."
        )
    selected_card = left_panel.get("selectedMetricsCard")
    if not isinstance(selected_card, dict):
        raise ResponsiveGeometryFailure(f"Visible selected metrics summary is missing in {snapshot.get('name')}.")
    if float(selected_card.get("scrollWidth", 0)) > float(selected_card.get("clientWidth", 0)) + 1:
        raise ResponsiveGeometryFailure(
            f"Selected metrics summary has horizontal overflow in {snapshot.get('name')}: "
            f"scrollWidth={selected_card.get('scrollWidth')}, clientWidth={selected_card.get('clientWidth')}."
        )
    if selected_card.get("overflowsPanel") or int(selected_card.get("childOverflowCount", 0)) > 0:
        raise ResponsiveGeometryFailure(
            f"Selected metrics summary escaped the visible left panel in {snapshot.get('name')}: {selected_card!r}."
        )
