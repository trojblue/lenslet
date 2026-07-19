"""Focused dropdown controls exercised by the Metrics painted-frame probe."""

from __future__ import annotations

from typing import Any


def collapse_left_panel_with_focus_check(page: Any, timeout_ms: float) -> dict[str, Any]:
    page.locator("[data-metric-show-all]").focus()
    page.keyboard.press("Control+b")
    page.wait_for_function(
        "() => document.querySelector('.app-left-panel')?.getAttribute('data-left-content-open') === 'false'",
        timeout=timeout_ms,
    )
    state = page.evaluate(
        """() => {
          const active = document.activeElement;
          const panel = document.querySelector('.app-left-panel');
          return {
            activeTag: active?.tagName || null,
            activeInLeftPanel: Boolean(active && panel?.contains(active)),
            activeInHiddenOrInert: Boolean(active?.closest?.('[hidden], [inert]')),
          };
        }"""
    )
    state["violations"] = []
    if state["activeInLeftPanel"] or state["activeInHiddenOrInert"]:
        state["violations"].append(
            f"collapsed left content retained a hidden focus target: {state!r}"
        )
    return state


def capture_dropdown_first_paint(page: Any, trigger: Any, aria_label: str) -> dict[str, Any]:
    page.evaluate(
        """label => {
          const samples = [];
          const capture = (panel, phase) => {
            if (!(panel instanceof HTMLElement) || panel.getAttribute('aria-label') !== label) return;
            const style = getComputedStyle(panel);
            samples.push({
              phase,
              opacity: Number(style.opacity),
              transform: style.transform,
              animationName: style.animationName,
              visibility: style.visibility,
            });
          };
          const observer = new MutationObserver(records => {
            for (const record of records) {
              for (const node of record.addedNodes) {
                if (!(node instanceof HTMLElement)) continue;
                const panel = node.matches('.dropdown-panel') ? node : node.querySelector('.dropdown-panel');
                if (!(panel instanceof HTMLElement) || panel.getAttribute('aria-label') !== label) continue;
                capture(panel, 'mount');
                requestAnimationFrame(() => {
                  capture(panel, 'raf-1');
                  requestAnimationFrame(() => capture(panel, 'raf-2'));
                });
              }
            }
          });
          observer.observe(document.body, { childList: true, subtree: true });
          window.__lensletDropdownPaint = { samples, observer };
        }""",
        aria_label,
    )
    trigger.scroll_into_view_if_needed()
    trigger.click()
    page.locator(f'[role="listbox"][aria-label="{aria_label}"]').wait_for(state="visible")
    page.wait_for_timeout(60)
    samples = page.evaluate(
        """() => {
          const trace = window.__lensletDropdownPaint;
          trace?.observer?.disconnect();
          return trace?.samples || [];
        }"""
    )
    page.keyboard.press("Escape")
    visible = [sample for sample in samples if sample.get("visibility") != "hidden"]
    violations: list[str] = []
    if not visible:
        violations.append(f"{aria_label} had no visible first-paint sample")
    for sample in visible:
        if abs(float(sample.get("opacity", 0)) - 1.0) > 0.001:
            violations.append(f"{aria_label} painted with opacity {sample.get('opacity')!r}")
        if sample.get("transform") not in {"none", "matrix(1, 0, 0, 1, 0, 0)"}:
            violations.append(f"{aria_label} painted with transform {sample.get('transform')!r}")
        if sample.get("animationName") not in {"none", ""}:
            violations.append(f"{aria_label} retained animation {sample.get('animationName')!r}")
    return {"samples": samples, "violations": violations}


def exercise_operator_dropdowns(page: Any, timeout_ms: float) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    for dimension in ("width", "height"):
        label = f"{dimension.title()} operator"
        trigger = page.locator(
            f'[data-dimension-operator="{dimension}"] button[aria-haspopup="listbox"]'
        ).first
        checks[dimension] = capture_dropdown_first_paint(page, trigger, label)
        trigger.focus()
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Home")
        page.keyboard.press("Enter")
        page.wait_for_function(
            """expected => (document.querySelector(expected.selector)?.textContent || '').trim() === '<'""",
            arg={"selector": f'[data-dimension-operator="{dimension}"] button'},
            timeout=timeout_ms,
        )
    native_select_count = page.locator(
        "[data-derived-score-card] select, [data-attributes-card] select"
    ).count()
    checks["native_select_count"] = native_select_count
    checks["violations"] = [
        violation
        for dimension in ("width", "height")
        for violation in checks[dimension]["violations"]
    ]
    if native_select_count:
        checks["violations"].append(f"found {native_select_count} native operator/missing selects")
    checks["edit_safety"] = _exercise_external_filter_projection(page, timeout_ms)
    checks["violations"].extend(checks["edit_safety"]["violations"])
    return checks


def _exercise_external_filter_projection(page: Any, timeout_ms: float) -> dict[str, Any]:
    width = page.get_by_label("Width pixels")
    minimum = page.get_by_label("quality_score minimum")
    maximum = page.get_by_label("quality_score maximum")
    filename = page.get_by_role("textbox", name="Filename contains", exact=True)
    clear = page.locator('[data-grid-top-rail] button:has-text("Clear all")').first
    domain_min = float(minimum.get_attribute("placeholder") or "0")
    domain_max = float(maximum.get_attribute("placeholder") or "1")
    range_min = f"{domain_min + (domain_max - domain_min) * 0.2:g}"
    range_max = f"{domain_min + (domain_max - domain_min) * 0.8:g}"

    def set_committed_inputs() -> None:
        width.fill("640")
        minimum.fill(range_min)
        minimum.press("Enter")
        maximum.fill(range_max)
        maximum.press("Enter")
        filename.fill("committed")
        page.wait_for_timeout(300)
        clear.wait_for(state="visible", timeout=timeout_ms)

    def clear_without_focus_change() -> None:
        page.evaluate(
            """() => Array.from(document.querySelectorAll('[data-grid-top-rail] button'))
              .find(button => (button.textContent || '').trim() === 'Clear all')?.click()"""
        )
        page.evaluate("() => new Promise(resolve => requestAnimationFrame(() => resolve(null)))")

    set_committed_inputs()
    filename.focus()
    clear_without_focus_change()
    page.wait_for_timeout(300)
    filename.blur()
    focus_only_text = _filter_control_values(page)

    set_committed_inputs()
    minimum.focus()
    clear_without_focus_change()
    minimum.blur()
    page.wait_for_timeout(300)
    focus_only_range = _filter_control_values(page)

    set_committed_inputs()
    filename.fill("active-draft")
    clear_without_focus_change()
    active_clear = _filter_control_values(page)
    page.wait_for_timeout(300)
    filename.blur()
    page.wait_for_function(
        """() => (document.querySelector('[aria-label="Filename contains"]')?.value || '')
          === 'active-draft'""",
        timeout=timeout_ms,
    )
    clear.wait_for(state="visible", timeout=timeout_ms)
    clear.click()
    page.wait_for_function(
        """() => {
          const value = selector => document.querySelector(selector)?.value || '';
          return value('[aria-label="Filename contains"]') === ''
            && value('[aria-label="Width pixels"]') === ''
            && value('[aria-label="quality_score minimum"]') === ''
            && value('[aria-label="quality_score maximum"]') === '';
        }""",
        timeout=timeout_ms,
    )
    settled_clear = _filter_control_values(page)

    _select_operator(page, "width", "<=", timeout_ms)
    width.fill("777")
    minimum.fill(range_min)
    minimum.press("Enter")
    maximum.fill(range_max)
    maximum.press("Enter")
    page.get_by_role("button", name="Folders").click()
    page.once("dialog", lambda dialog: dialog.accept("Projection fixture"))
    page.get_by_role("button", name="+ New").click()
    page.get_by_role("button", name="Projection fixture").wait_for(timeout=timeout_ms)
    page.get_by_role("button", name="Metrics and Filters", exact=True).click()
    clear.wait_for(state="visible", timeout=timeout_ms)
    clear.click()
    page.get_by_role("button", name="Folders").click()
    page.get_by_role("button", name="Projection fixture").click()
    page.get_by_role("button", name="Metrics and Filters", exact=True).click()
    width.wait_for(state="visible", timeout=timeout_ms)
    page.wait_for_timeout(300)
    smart_folder = _filter_control_values(page)
    shared_url = page.url

    restored_page = page.context.new_page()
    try:
        restored_page.goto(page.url, wait_until="domcontentloaded")
        restored_page.get_by_role("grid", name="Gallery").wait_for(timeout=timeout_ms)
        restored_page.get_by_role("button", name="Metrics and Filters", exact=True).click()
        restored_page.get_by_label("Width pixels").wait_for(state="visible", timeout=timeout_ms)
        metric_trigger = restored_page.locator(
            '[data-metric-selector] button[aria-haspopup="listbox"]'
        ).first
        metric_trigger.click()
        restored_page.get_by_role("option", name="quality_score", exact=True).click()
        restored_page.locator(
            '[data-metric-histogram-card="quality_score"][data-facet-state="ready"]'
        ).wait_for(state="visible", timeout=timeout_ms)
        restored = _filter_control_values(restored_page)
    finally:
        restored_page.close()
    clear.click()

    violations: list[str] = []
    expected_active_clear = {
        "operator": ">=",
        "width": "",
        "minimum": "",
        "maximum": "",
        "filename": "active-draft",
    }
    expected_focus_only = {**expected_active_clear, "filename": ""}
    if focus_only_text != expected_focus_only:
        violations.append(
            f"focus-only text draft resurrected external state: {focus_only_text!r}"
        )
    if focus_only_range != expected_focus_only:
        violations.append(
            f"focus-only range draft resurrected external state: {focus_only_range!r}"
        )
    if active_clear != expected_active_clear:
        violations.append(f"external Clear all mixed or overwrote an active edit: {active_clear!r}")
    expected_projection = {
        "operator": "<=",
        "width": "777",
        "minimum": range_min,
        "maximum": range_max,
        "filename": "",
    }
    if settled_clear != {**expected_active_clear, "filename": ""}:
        violations.append(f"settled Clear all left stale controlled values: {settled_clear!r}")
    if smart_folder != expected_projection:
        violations.append(f"Smart Folder activation projected stale controls: {smart_folder!r}")
    if restored != expected_projection:
        violations.append(
            f"URL view restore projected stale controls: {restored!r}; url={shared_url!r}"
        )
    return {
        "active_clear": active_clear,
        "focus_only_text": focus_only_text,
        "focus_only_range": focus_only_range,
        "settled_clear": settled_clear,
        "smart_folder": smart_folder,
        "restored": restored,
        "shared_url": shared_url,
        "violations": violations,
    }


def _select_operator(page: Any, dimension: str, value: str, timeout_ms: float) -> None:
    trigger = page.locator(
        f'[data-dimension-operator="{dimension}"] button[aria-haspopup="listbox"]'
    ).first
    trigger.click()
    page.get_by_role("option", name=value, exact=True).click()
    page.wait_for_function(
        """expected => (document.querySelector(expected.selector)?.textContent || '').trim()
          === expected.value""",
        arg={"selector": f'[data-dimension-operator="{dimension}"] button', "value": value},
        timeout=timeout_ms,
    )


def _filter_control_values(page: Any) -> dict[str, str]:
    return page.evaluate(
        """() => ({
          operator: (document.querySelector('[data-dimension-operator="width"] button')
            ?.textContent || '').trim(),
          width: document.querySelector('[aria-label="Width pixels"]')?.value || '',
          minimum: document.querySelector('[aria-label="quality_score minimum"]')?.value || '',
          maximum: document.querySelector('[aria-label="quality_score maximum"]')?.value || '',
          filename: document.querySelector('[aria-label="Filename contains"]')?.value || '',
        })"""
    )
