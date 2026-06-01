from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.browser.overall_cleanup.support import _SCREENSHOT_CAPTURE_ERRORS

def capture_context_screenshots(contexts: list[Any], screenshot_dir: Path, prefix: str) -> list[str]:
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for context_index, context in enumerate(contexts):
        for page_index, page in enumerate(context.pages):
            path = capture_page_screenshot(page, screenshot_dir, prefix, context_index, page_index)
            if path is not None:
                paths.append(path)
    return paths

def capture_page_screenshot(
    page: Any,
    screenshot_dir: Path,
    prefix: str,
    context_index: int,
    page_index: int,
) -> str | None:
    try:
        if page.is_closed():
            return None
        path = screenshot_dir / f"{prefix}_{context_index}_{page_index}.png"
        page.screenshot(path=str(path), full_page=True)
    except _SCREENSHOT_CAPTURE_ERRORS:
        return None
    return str(path)

def screenshot_suffix(paths: list[str]) -> str:
    if not paths:
        return ""
    return f" Screenshots: {', '.join(paths)}"
