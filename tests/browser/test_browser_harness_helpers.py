from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
REPO_ROOT = SCRIPTS_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.browser.large_tree import smoke as large_tree
from scripts.browser.responsive_geometry import evidence as responsive_evidence
from scripts.browser.responsive_geometry import harness as responsive


class _FakeResponsivePage:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, object | None]] = []

    def evaluate(self, script: str, arg: object | None = None) -> object:
        self.calls.append((script, arg))
        if not self.responses:
            raise AssertionError("unexpected extra page.evaluate call")
        return self.responses.pop(0)


class _FakeResponsiveBrowserContext:
    def __init__(self) -> None:
        self.page = _FakeScenarioPage()
        self.closed = False

    def new_page(self) -> "_FakeScenarioPage":
        return self.page

    def close(self) -> None:
        self.closed = True


class _FakeResponsiveBrowser:
    def __init__(self) -> None:
        self.contexts: list[_FakeResponsiveBrowserContext] = []
        self.new_context_calls: list[dict[str, object]] = []

    def new_context(self, **kwargs: object) -> _FakeResponsiveBrowserContext:
        self.new_context_calls.append(kwargs)
        context = _FakeResponsiveBrowserContext()
        self.contexts.append(context)
        return context


class _FakeScenarioPage:
    def __init__(self) -> None:
        self.timeout_ms: float | None = None

    def set_default_timeout(self, timeout_ms: float) -> None:
        self.timeout_ms = timeout_ms


def _baseline_payload(dataset_dir: str = "data/large") -> dict:
    return {
        "profiles": {
            "test": {
                "gate_tier": "unit",
                "dataset_dir": dataset_dir,
                "total_images": "40",
                "total_folders": 8,
                "image_width": 20,
                "image_height": "30",
                "jpeg_quality": 75,
                "first_grid_threshold_seconds": "2.5",
                "first_grid_hotpath_threshold_ms": 120,
                "first_thumbnail_threshold_ms": 90,
                "interaction_seconds": 1.25,
                "max_frame_gap_ms": "32",
                "write_mode": True,
                "expectations": "unit baseline",
            }
        }
    }


def _write_baseline(path: Path, payload: dict | None = None) -> None:
    path.write_text(json.dumps(payload or _baseline_payload()), encoding="utf-8")


def _base_args(baseline_file: Path) -> argparse.Namespace:
    return argparse.Namespace(
        baseline_file=baseline_file,
        baseline_profile="test",
        dataset_dir=None,
        total_images=None,
        total_folders=99,
        image_width=None,
        image_height=None,
        jpeg_quality=None,
        first_grid_threshold_seconds=None,
        first_grid_hotpath_threshold_ms=150.0,
        first_thumbnail_threshold_ms=None,
        interaction_seconds=None,
        max_frame_gap_ms=None,
        write_mode=False,
        metric_key="score",
        forbid_metric_key="internal",
    )


def test_responsive_collect_snapshot_merges_focused_collectors() -> None:
    shell_snapshot = {
        "name": "phone",
        "state": {"width": 390},
        "viewport": {"width": 390, "height": 520},
        "browser": {"url": "http://localhost"},
        "media": {"coarsePointer": True},
        "layout": {"mode": "phone"},
        "cssVars": {"toolbarHeight": "96px"},
        "scroll": {"scrollWidth": 390, "clientWidth": 390},
        "rects": {"shell": {"width": 390}},
    }
    focus_selection_storage = {
        "focus": {"activeElement": None},
        "selection": {"ariaSelectedCount": 0},
        "themeMenu": {"labels": []},
        "storage": {"leftOpen": "1"},
    }
    page = _FakeResponsivePage([
        shell_snapshot,
        {"viewer": None},
        focus_selection_storage,
        {"leftPanel": None, "inspector": None},
        [{"name": "drawer-theme", "visible": True}],
    ])

    snapshot = responsive.collect_snapshot(page, "phone", {"width": 390})

    assert snapshot["name"] == "phone"
    assert snapshot["images"] == {"viewer": None}
    assert snapshot["focus"] == {"activeElement": None}
    assert snapshot["leftPanel"] is None
    assert snapshot["toolbarControls"] == [{"name": "drawer-theme", "visible": True}]
    assert len(page.calls) == 5
    assert page.calls[0][1] == {"name": "phone", "state": {"width": 390}}


def test_responsive_collect_snapshot_stops_when_shell_missing() -> None:
    page = _FakeResponsivePage([{"name": "missing", "missingShell": True}])

    with pytest.raises(responsive.ResponsiveGeometryFailure, match="App shell"):
        responsive.collect_snapshot(page, "missing")

    assert len(page.calls) == 1


def test_responsive_scenario_runner_uses_run_context(tmp_path: Path) -> None:
    browser = _FakeResponsiveBrowser()
    evidence: dict[str, object] = {"scenarios": [], "failures": []}
    seen: dict[str, object] = {}

    def _runner(page: object, base_url: str, timeout_ms: float) -> dict[str, object]:
        seen["page"] = page
        seen["base_url"] = base_url
        seen["timeout_ms"] = timeout_ms
        return {"name": "phone"}

    scenario = responsive.BrowserScenario(
        name="phone",
        width=390,
        height=720,
        has_touch=True,
        runner=_runner,
    )
    run = responsive.BrowserScenarioRun(
        browser=browser,
        scenarios=[scenario],
        evidence=evidence,
        base_url="http://127.0.0.1:7070",
        timeout_ms=1234.0,
        screenshot_dir=tmp_path,
    )

    responsive.run_browser_scenarios(run)

    assert browser.new_context_calls == [
        {"viewport": {"width": 390, "height": 720}, "has_touch": True, "is_mobile": True}
    ]
    assert browser.contexts[0].closed is True
    assert browser.contexts[0].page.timeout_ms == 1234.0
    assert seen == {
        "page": browser.contexts[0].page,
        "base_url": "http://127.0.0.1:7070",
        "timeout_ms": 1234.0,
    }
    assert evidence["scenarios"] == [{"name": "phone"}]


def _toolbar_control(
    name: str,
    *,
    left: float = 0,
    top: float = 0,
    width: float = 40,
    height: float = 32,
    visible: bool = True,
    aria_hidden: str | None = None,
    hit_target_ok: bool = True,
    keyboard_focusable: bool = True,
    focus_disabled: bool = False,
) -> dict:
    return {
        "name": name,
        "visible": visible,
        "ariaHidden": aria_hidden,
        "hitTargetOk": hit_target_ok,
        "keyboardFocusable": keyboard_focusable,
        "focusDisabled": focus_disabled,
        "rect": {
            "left": left,
            "right": left + width,
            "top": top,
            "bottom": top + height,
            "width": width,
            "height": height,
        },
    }


def _responsive_visible_image(path: str = "/gallery/a.jpg", *, opacity: float = 1.0) -> dict:
    return {
        "complete": True,
        "naturalWidth": 320,
        "naturalHeight": 200,
        "opacity": opacity,
        "display": "block",
        "visibility": "visible",
        "currentPath": path,
        "rect": {"left": 0, "top": 0, "right": 320, "bottom": 200, "width": 320, "height": 200},
    }


def test_responsive_geometry_basic_predicates_accept_clean_snapshots() -> None:
    snapshot = {
        "name": "desktop",
        "scroll": {"scrollWidth": 900, "clientWidth": 900},
        "toolbarControls": [
            _toolbar_control("layout", left=0),
            _toolbar_control("sort", left=56),
            _toolbar_control("hidden", visible=False, aria_hidden="true", hit_target_ok=False, keyboard_focusable=False),
        ],
    }

    responsive_evidence.assert_no_document_overflow(snapshot)
    responsive_evidence.assert_no_visible_control_overlap(snapshot)
    responsive_evidence.assert_hidden_toolbar_controls_not_interactable(snapshot)


@pytest.mark.parametrize(
    ("check", "snapshot", "message"),
    [
        (
            responsive_evidence.assert_no_document_overflow,
            {"name": "wide", "scroll": {"scrollWidth": 902, "clientWidth": 900}},
            "Document overflow",
        ),
        (
            responsive_evidence.assert_no_visible_control_overlap,
            {
                "name": "overlap",
                "toolbarControls": [
                    _toolbar_control("layout", left=0),
                    _toolbar_control("sort", left=20),
                ],
            },
            "overlap",
        ),
        (
            responsive_evidence.assert_hidden_toolbar_controls_not_interactable,
            {
                "name": "hidden",
                "toolbarControls": [
                    _toolbar_control("drawer", visible=False, hit_target_ok=True, keyboard_focusable=True),
                ],
            },
            "still reachable",
        ),
    ],
)
def test_responsive_geometry_basic_predicates_reject_bad_snapshots(check, snapshot: dict, message: str) -> None:
    with pytest.raises(responsive_evidence.ResponsiveGeometryFailure, match=message):
        check(snapshot)


def _mobile_drawer_snapshot(
    *,
    missing: str | None = None,
    blocked: str | None = None,
    include_upload: bool = False,
) -> dict:
    required = set(responsive_evidence.REQUIRED_DRAWER_CONTROLS)
    required.add("drawer-select")
    if include_upload:
        required.add("drawer-upload")
    if missing is not None:
        required.remove(missing)
    controls = [
        _toolbar_control(
            name,
            hit_target_ok=name != blocked,
            keyboard_focusable=name != blocked,
        )
        for name in sorted(required)
    ]
    return {
        "name": "phone",
        "layout": {"mobileDrawerOpen": "true"},
        "viewport": {"width": 390},
        "toolbarControls": controls,
    }


def test_responsive_mobile_search_drawer_and_theme_assertions() -> None:
    search_snapshot = {
        "name": "phone-search",
        "cssVars": {"toolbarHeight": "104px"},
        "rects": {
            "toolbar": {"bottom": 90},
            "gridShell": {"top": 92},
            "topRail": {"top": 92, "height": 45},
        },
        "toolbarControls": [_toolbar_control("search-mobile")],
    }
    theme_snapshot = {
        "name": "theme",
        "rects": {"themeMenu": {"left": 0, "right": 200}},
        "themeMenu": {"labels": ["Autoload image metadata", "Order compare by selection"]},
    }

    responsive_evidence.assert_mobile_search_reserved(search_snapshot)
    responsive_evidence.assert_mobile_drawer_reachable(_mobile_drawer_snapshot())
    responsive_evidence.assert_theme_settings_reachable(theme_snapshot)

    with pytest.raises(responsive_evidence.ResponsiveGeometryFailure, match="missing"):
        responsive_evidence.assert_mobile_drawer_reachable(_mobile_drawer_snapshot(missing="drawer-sort"))
    with pytest.raises(responsive_evidence.ResponsiveGeometryFailure, match="not pointer/keyboard reachable"):
        responsive_evidence.assert_mobile_drawer_reachable(_mobile_drawer_snapshot(blocked="drawer-sort"))
    with pytest.raises(responsive_evidence.ResponsiveGeometryFailure, match="not pointer/keyboard reachable"):
        responsive_evidence.assert_mobile_drawer_reachable(
            _mobile_drawer_snapshot(blocked="drawer-upload", include_upload=True)
        )


def _overlay_snapshot(*, active_in_browse_shell: bool = False) -> dict:
    return {
        "name": "viewer",
        "layout": {"overlayMode": "viewer"},
        "rects": {"overlay": {"left": 0, "right": 390}},
        "focus": {
            "browseShellInert": True,
            "browseShellAriaHidden": "true",
            "toolbarInert": False,
            "toolbarAriaHidden": None,
            "activeElement": {"inBrowseShell": active_in_browse_shell},
        },
        "viewport": {"width": 390},
        "cssVars": {"overlayLeft": "0px", "overlayRight": "0px"},
    }


def test_responsive_overlay_and_image_stability_assertions() -> None:
    responsive_evidence.assert_overlay_isolated(_overlay_snapshot(), "viewer")
    responsive_evidence.assert_overlay_image_stable(
        {
            "name": "viewer",
            "samples": [
                {"frame": 0, "images": {"viewer": _responsive_visible_image()}},
                {"frame": 1, "images": {"viewer": _responsive_visible_image()}},
            ],
        },
        ("viewer",),
        {"viewer": "/gallery/a.jpg"},
    )

    with pytest.raises(responsive_evidence.ResponsiveGeometryFailure, match="Focus reached browse shell"):
        responsive_evidence.assert_overlay_isolated(_overlay_snapshot(active_in_browse_shell=True), "viewer")
    with pytest.raises(responsive_evidence.ResponsiveGeometryFailure, match="became invisible"):
        responsive_evidence.assert_overlay_image_stable(
            {
                "name": "viewer",
                "samples": [
                    {"frame": 0, "images": {"viewer": _responsive_visible_image()}},
                    {"frame": 1, "images": {"viewer": _responsive_visible_image(opacity=0.0)}},
                ],
            },
            ("viewer",),
            {"viewer": "/gallery/a.jpg"},
        )


def test_responsive_inspector_and_metrics_panel_assertions() -> None:
    inspector_snapshot = {
        "name": "inspector",
        "layout": {"effectiveRightWidth": "320"},
        "inspector": {"scrollWidth": 300, "clientWidth": 300, "checks": [{"overflowsPanel": False}]},
    }
    metrics_snapshot = {
        "name": "metrics",
        "selection": {"ariaSelectedCount": 2},
        "leftPanel": {
            "activeTool": "metrics",
            "contentOverflowCount": 0,
            "selectedMetricsCard": {
                "scrollWidth": 240,
                "clientWidth": 240,
                "overflowsPanel": False,
                "childOverflowCount": 0,
            },
        },
    }

    responsive_evidence.assert_inspector_contained(inspector_snapshot)
    responsive_evidence.assert_visible_metrics_left_contained(metrics_snapshot)

    with pytest.raises(responsive_evidence.ResponsiveGeometryFailure, match="horizontal overflow"):
        responsive_evidence.assert_inspector_contained(
            {**inspector_snapshot, "inspector": {"scrollWidth": 330, "clientWidth": 300, "checks": []}}
        )


def test_large_tree_baseline_loading_and_argument_defaults(tmp_path: Path) -> None:
    baseline_file = tmp_path / "baselines.json"
    _write_baseline(baseline_file, _baseline_payload("fixtures/tree"))

    profile = large_tree.load_baseline_profile(baseline_file, "test")

    assert profile.dataset_dir == Path("fixtures/tree")
    assert profile.total_images == 40
    assert profile.first_grid_threshold_seconds == 2.5
    assert profile.write_mode is True

    args = large_tree.resolve_args_with_baseline(_base_args(baseline_file))

    assert args.dataset_dir == Path("fixtures/tree")
    assert args.total_images == 40
    assert args.total_folders == 99
    assert args.first_grid_hotpath_threshold_ms == 150.0
    assert args.write_mode is True
    assert args.baseline_gate_tier == "unit"
    assert args.baseline_expectations == "unit baseline"


def test_large_tree_baseline_validation_rejects_bool_numbers(tmp_path: Path) -> None:
    baseline_file = tmp_path / "baselines.json"
    payload = _baseline_payload()
    payload["profiles"]["test"]["total_images"] = True
    _write_baseline(baseline_file, payload)

    with pytest.raises(large_tree.SmokeFailure, match="total_images"):
        large_tree.load_baseline_profile(baseline_file, "test")


def test_large_tree_fixture_tail_path_uses_ceiling_folder_size(tmp_path: Path) -> None:
    tail = large_tree._expected_fixture_tail_path(
        tmp_path,
        total_images=10,
        total_folders=3,
    )

    assert tail == tmp_path / "folder_00002" / "image_00009.jpg"


def test_large_tree_scope_url_and_toolbar_count_parsing() -> None:
    assert large_tree.normalize_scope_path(None) == "/"
    assert large_tree.normalize_scope_path(" nested/path/ ") == "/nested/path"
    assert large_tree.scope_url("http://127.0.0.1:7070", "/") == "http://127.0.0.1:7070"
    assert (
        large_tree.scope_url("http://127.0.0.1:7070", "group A/@set")
        == "http://127.0.0.1:7070#/group%20A/@set"
    )
    assert large_tree.parse_toolbar_count_label("1,234 / 40,000 items") == (1234, 40000)
    assert large_tree.parse_toolbar_count_label("25 items") == (25, None)

    with pytest.raises(large_tree.SmokeFailure):
        large_tree.parse_toolbar_count_label("25 images")


def test_large_tree_request_budget_compliance() -> None:
    limits, peaks = large_tree.assert_request_budget_compliance(
        {
            "requestBudget": {
                "limits": {"folders": "2", "thumb": 8, "file": 1},
                "peakInflight": {"folders": 2, "thumb": "7", "file": 0},
            }
        }
    )

    assert limits == {"folders": 2, "thumb": 8, "file": 1}
    assert peaks == {"folders": 2, "thumb": 7, "file": 0}

    with pytest.raises(large_tree.SmokeFailure, match="overflow"):
        large_tree.assert_request_budget_compliance(
            {
                "requestBudget": {
                    "limits": {"folders": 1, "thumb": 8, "file": 1},
                    "peakInflight": {"folders": 2, "thumb": 1, "file": 0},
                }
            }
        )


def test_large_tree_responsiveness_thresholds() -> None:
    thresholds = large_tree.SmokeThresholds(
        first_grid_seconds=1.0,
        first_grid_hotpath_ms=100,
        first_thumbnail_ms=100,
        max_frame_gap_ms=16,
    )

    large_tree.assert_responsiveness_thresholds(
        thresholds=thresholds,
        first_grid_visible_seconds=0.2,
        first_grid_hotpath_latency_ms=80,
        max_frame_gap_ms=12,
        first_thumbnail_latency_ms=70,
    )

    with pytest.raises(large_tree.SmokeFailure, match="first-grid telemetry"):
        large_tree.assert_responsiveness_thresholds(
            thresholds=thresholds,
            first_grid_visible_seconds=0.2,
            first_grid_hotpath_latency_ms=None,
            max_frame_gap_ms=12,
            first_thumbnail_latency_ms=70,
        )

    with pytest.raises(large_tree.SmokeFailure, match="UI freeze"):
        large_tree.assert_responsiveness_thresholds(
            thresholds=thresholds,
            first_grid_visible_seconds=0.2,
            first_grid_hotpath_latency_ms=80,
            max_frame_gap_ms=20,
            first_thumbnail_latency_ms=70,
        )


def test_large_tree_smoke_result_assembly(tmp_path: Path) -> None:
    baseline_file = tmp_path / "baselines.json"
    _write_baseline(baseline_file)
    args = large_tree.resolve_args_with_baseline(_base_args(baseline_file))
    outcome = large_tree.PlaywrightProbeOutcome(
        first_grid_visible_seconds=0.42,
        probe_result={"maxGapMs": 12.5, "avgGapMs": 4.25, "frames": 120},
        hotpath_snapshot=None,
        page_errors=["page"],
        console_errors=["console", "console-2"],
        metric_probe={
            "metric_sort_desc_top_path": "/b.jpg",
            "metric_sort_asc_top_path": "/a.jpg",
            "metric_filter_count_before": "40",
            "metric_filter_count_after": 12,
            "metric_filter_max": "0.97",
        },
    )
    metadata = large_tree.SmokeRunMetadata(
        baseline_file=args.baseline_file,
        baseline_profile=args.baseline_profile,
        gate_tier=args.baseline_gate_tier,
        write_mode=bool(args.write_mode),
        dataset_dir=tmp_path / "dataset",
        source_path=tmp_path / "dataset",
        total_images=args.total_images,
        total_folders=args.total_folders,
        scope_path=None,
        metric_key=args.metric_key,
        forbidden_metric_key=args.forbid_metric_key,
    )
    thresholds = large_tree.SmokeThresholds(
        first_grid_seconds=args.first_grid_threshold_seconds,
        first_grid_hotpath_ms=args.first_grid_hotpath_threshold_ms,
        first_thumbnail_ms=args.first_thumbnail_threshold_ms,
        max_frame_gap_ms=args.max_frame_gap_ms,
    )

    result = large_tree._build_smoke_result(
        metadata=metadata,
        thresholds=thresholds,
        probe_outcome=outcome,
        request_budget_limits={"folders": 2, "thumb": 8, "file": 1},
        request_budget_peaks={"folders": 1, "thumb": 4, "file": 0},
        indexing={"state": "ready", "done": 40, "total": 40},
        first_grid_hotpath_latency_ms=80,
        first_thumbnail_latency_ms=70,
    )

    payload = asdict(result)
    assert payload["scope_path"] is None
    assert payload["page_errors"] == 1
    assert payload["console_errors"] == 2
    assert payload["metric_filter_count_before"] == 40
    assert payload["metric_filter_max"] == 0.97
