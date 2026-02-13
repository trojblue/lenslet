from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_smoke_module() -> ModuleType:
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "playwright_large_tree_smoke.py"
    spec = importlib.util.spec_from_file_location("playwright_large_tree_smoke", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load playwright_large_tree_smoke module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _make_args(**overrides: object) -> argparse.Namespace:
    defaults = {
        "dataset_dir": None,
        "total_images": None,
        "total_folders": None,
        "image_width": None,
        "image_height": None,
        "jpeg_quality": None,
        "first_grid_threshold_seconds": None,
        "first_grid_hotpath_threshold_ms": None,
        "first_thumbnail_threshold_ms": None,
        "interaction_seconds": None,
        "max_frame_gap_ms": None,
        "baseline_file": Path("scripts/playwright_large_tree_smoke_baselines.json"),
        "baseline_profile": "primary_large_no_write",
        "write_mode": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_load_baseline_profile_primary_defaults() -> None:
    smoke = _load_smoke_module()
    profile = smoke.load_baseline_profile(
        Path("scripts/playwright_large_tree_smoke_baselines.json"),
        "primary_large_no_write",
    )

    assert profile.gate_tier == "primary"
    assert profile.total_images == 40_000
    assert profile.total_folders == 10_000
    assert profile.first_grid_hotpath_threshold_ms == 5_000.0
    assert profile.write_mode is False


def test_default_baseline_file_is_script_relative() -> None:
    smoke = _load_smoke_module()
    assert smoke.DEFAULT_BASELINE_FILE.is_absolute()
    assert smoke.DEFAULT_BASELINE_FILE.name == "playwright_large_tree_smoke_baselines.json"
    assert smoke.DEFAULT_BASELINE_FILE.exists()


def test_resolve_args_with_baseline_allows_overrides() -> None:
    smoke = _load_smoke_module()
    args = _make_args(
        baseline_profile="secondary_tiny_fast",
        first_grid_threshold_seconds=7.5,
        write_mode=True,
    )
    resolved = smoke.resolve_args_with_baseline(args)

    assert resolved.baseline_gate_tier == "secondary"
    assert resolved.total_images == 400
    assert resolved.total_folders == 100
    assert resolved.first_grid_threshold_seconds == 7.5
    assert resolved.first_grid_hotpath_threshold_ms == 10_000.0
    assert resolved.write_mode is True


def test_thresholds_require_first_grid_hotpath_metric() -> None:
    smoke = _load_smoke_module()
    with pytest.raises(smoke.SmokeFailure, match="first-grid telemetry"):
        smoke.assert_responsiveness_thresholds(
            first_grid_visible_seconds=1.0,
            first_grid_threshold_seconds=5.0,
            first_grid_hotpath_latency_ms=None,
            first_grid_hotpath_threshold_ms=5_000.0,
            max_frame_gap_ms=100.0,
            max_frame_gap_threshold_ms=700.0,
            first_thumbnail_latency_ms=700,
            first_thumbnail_threshold_ms=5_000.0,
        )
