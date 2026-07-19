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
    return checks
