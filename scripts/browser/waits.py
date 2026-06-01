from __future__ import annotations

from typing import Any


def wait_for_animation_frames(page: Any, timeout_ms: float, frames: int = 2) -> None:
    """Wait for a bounded number of browser paint opportunities."""
    page.wait_for_function(
        """(frameCount) => new Promise((resolve) => {
          let remaining = Math.max(1, Number(frameCount) || 1);
          const tick = () => {
            remaining -= 1;
            if (remaining <= 0) {
              resolve(true);
              return;
            }
            requestAnimationFrame(tick);
          };
          requestAnimationFrame(tick);
        })""",
        arg=frames,
        timeout=timeout_ms,
    )


def wait_for_dom_settled(page: Any, timeout_ms: float, stable_ms: float = 80) -> None:
    """Wait until DOM mutations have been quiet for a short, centralized window."""
    page.wait_for_function(
        """(stableWindowMs) => new Promise((resolve) => {
          const root = document.body || document.documentElement;
          if (!root) {
            resolve(true);
            return;
          }
          let lastChange = performance.now();
          const observer = new MutationObserver(() => {
            lastChange = performance.now();
          });
          observer.observe(root, {
            attributes: true,
            characterData: true,
            childList: true,
            subtree: true,
          });
          const tick = () => {
            if (performance.now() - lastChange >= stableWindowMs) {
              observer.disconnect();
              resolve(true);
              return;
            }
            requestAnimationFrame(tick);
          };
          requestAnimationFrame(tick);
        })""",
        arg=stable_ms,
        timeout=timeout_ms,
    )


def wait_for_ui_settled(page: Any, timeout_ms: float, stable_ms: float = 80) -> None:
    wait_for_animation_frames(page, timeout_ms)
    wait_for_dom_settled(page, timeout_ms, stable_ms=stable_ms)
    wait_for_animation_frames(page, timeout_ms)


def wait_for_grid_selection_count(page: Any, expected_count: int, timeout_ms: float) -> None:
    page.wait_for_function(
        """(expectedCount) => (
          document.querySelectorAll('[role="gridcell"][aria-selected="true"]').length === expectedCount
        )""",
        arg=expected_count,
        timeout=timeout_ms,
    )
