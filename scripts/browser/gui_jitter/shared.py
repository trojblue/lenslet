"""Shared helpers for GUI jitter probe scenarios."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlunparse

from scripts.smoke_harness import SmokeFailure

MILLISECONDS_PER_SECOND = 1000.0


@dataclass(frozen=True)
class ProbeResult:
    scenario: str
    max_delta_px: float
    max_anchor_delta_px: float = 0.0
    max_toolbar_delta_px: float = 0.0
    max_top_stack_delta_px: float = 0.0
    max_grid_width_delta_px: float = 0.0
    max_inspector_delta_px: float = 0.0
    checks: dict[str, Any] = field(default_factory=dict)


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    replaced = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
        replaced = True
    finally:
        if not replaced:
            with contextlib.suppress(OSError):
                os.unlink(temp_name)


def write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    replaced = False
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.replace(temp_name, path)
        replaced = True
    finally:
        if not replaced:
            with contextlib.suppress(OSError):
                os.unlink(temp_name)


def build_base_url(host: str, port: int) -> str:
    return urlunparse(("http", f"{host}:{port}", "", "", "", ""))


def wait_for_grid(page: Any, timeout_ms: float) -> None:
    page.wait_for_selector('[role="gridcell"][id^="cell-"]', timeout=timeout_ms)


def set_local_storage(page: Any, values: dict[str, str | None]) -> None:
    page.evaluate(
        """(entries) => {
          for (const [key, value] of Object.entries(entries)) {
            if (value === null) {
              window.localStorage.removeItem(key);
            } else {
              window.localStorage.setItem(key, value);
            }
          }
        }""",
        values,
    )


def state_delta(lhs: dict[str, Any], rhs: dict[str, Any], key: str) -> float:
    left_raw = lhs.get(key)
    right_raw = rhs.get(key)
    if left_raw is None or right_raw is None:
        return 0.0
    try:
        return abs(float(left_raw) - float(right_raw))
    except (TypeError, ValueError):
        return 0.0


def state_delta_nested(lhs: dict[str, Any], rhs: dict[str, Any], parent_key: str, key: str) -> float:
    left_parent = lhs.get(parent_key)
    right_parent = rhs.get(parent_key)
    if not isinstance(left_parent, dict) or not isinstance(right_parent, dict):
        return 0.0
    left_raw = left_parent.get(key)
    right_raw = right_parent.get(key)
    if left_raw is None or right_raw is None:
        return 0.0
    try:
        return abs(float(left_raw) - float(right_raw))
    except (TypeError, ValueError):
        return 0.0


def require_dict_snapshot(snapshot: Any, message: str) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        raise SmokeFailure(message)
    return snapshot
