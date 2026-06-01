from __future__ import annotations

import time

from scripts.browser.waits import wait_for_ui_settled
from scripts.smoke_harness import SmokeFailure

try:
    from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
except ImportError as exc:  # pragma: no cover - runtime dependency guard
    raise SystemExit(
        "playwright is required: run python scripts/setup_dev.py from the repo root"
    ) from exc


def inspector_section_order(page: Page) -> list[str]:
    raw = page.evaluate(
        """() => Array.from(document.querySelectorAll('.app-right-panel [data-inspector-section-id]'))
          .map((el) => el.getAttribute('data-inspector-section-id'))
          .filter((value) => typeof value === 'string' && value.length > 0)"""
    )
    if not isinstance(raw, list):
        raise SmokeFailure("Failed to inspect right-panel section order.")
    result: list[str] = []
    for candidate in raw:
        if isinstance(candidate, str):
            result.append(candidate)
    return result


def assert_section_precedes(order: list[str], first: str, second: str, context: str) -> None:
    try:
        first_idx = order.index(first)
    except ValueError as exc:
        raise SmokeFailure(f"Section '{first}' missing from inspector order during {context}: {order!r}") from exc
    try:
        second_idx = order.index(second)
    except ValueError as exc:
        raise SmokeFailure(f"Section '{second}' missing from inspector order during {context}: {order!r}") from exc
    if first_idx >= second_idx:
        raise SmokeFailure(
            f"Expected section '{first}' to precede '{second}' during {context}, got order: {order!r}"
        )


def wait_for_section_precedence(
    page: Page,
    first: str,
    second: str,
    timeout_ms: float,
    context: str,
) -> list[str]:
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    latest_order: list[str] = []
    while time.monotonic() < deadline:
        latest_order = inspector_section_order(page)
        try:
            assert_section_precedes(latest_order, first, second, context)
            return latest_order
        except SmokeFailure:
            page.wait_for_timeout(120)
    raise SmokeFailure(
        f"Timed out waiting for section precedence '{first}' before '{second}' during {context}. "
        f"Last order: {latest_order!r}"
    )


def set_right_panel_open(page: Page, open_state: bool, timeout_ms: float) -> None:
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    while time.monotonic() < deadline:
        is_open = page.locator(".app-right-panel").count() > 0
        if is_open == open_state:
            return
        toggle_button = page.locator("button[aria-label='Toggle right panel']").first
        if toggle_button.count() == 0:
            page.wait_for_timeout(120)
            continue
        toggle_button.click()
        wait_for_ui_settled(page, min(timeout_ms, 5_000))
    raise SmokeFailure(
        f"Timed out setting right panel open state to {open_state}. "
        f"Current count={page.locator('.app-right-panel').count()}."
    )


def ensure_inspector_reorder_handles(page: Page, timeout_ms: float) -> None:
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    last_reorder_labels: list[str] = []
    while time.monotonic() < deadline:
        metadata_handle = page.get_by_role("button", name="Reorder Metadata").first
        basics_handle = page.get_by_role("button", name="Reorder Basics").first
        labels_raw = page.evaluate(
            """() => Array.from(document.querySelectorAll('button[aria-label^="Reorder "]'))
              .map((el) => el.getAttribute('aria-label') || '')"""
        )
        if isinstance(labels_raw, list):
            last_reorder_labels = [value for value in labels_raw if isinstance(value, str)]
        if metadata_handle.count() > 0 and basics_handle.count() > 0:
            try:
                if metadata_handle.is_visible() and basics_handle.is_visible():
                    return
            except PlaywrightTimeoutError:
                pass
        page.wait_for_timeout(120)

    raise SmokeFailure(
        "Timed out waiting for inspector reorder handles. "
        f"Visible reorder labels: {last_reorder_labels!r}."
    )
