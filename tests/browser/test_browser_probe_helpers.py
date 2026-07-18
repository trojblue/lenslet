from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
REPO_ROOT = SCRIPTS_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.browser.gui_jitter import fixtures as jitter_fixtures  # noqa: E402
from scripts.browser.gui_jitter import grid as jitter_grid  # noqa: E402
from scripts.browser.gui_jitter import grid_dom as jitter_grid_dom  # noqa: E402
from scripts.browser.gui_jitter import inspector as jitter_inspector  # noqa: E402
from scripts.browser.gui_jitter import probe as jitter_probe  # noqa: E402
from scripts.browser.gui_jitter import shared as jitter_shared  # noqa: E402
from scripts.browser.gui_jitter import toolbar as jitter_toolbar  # noqa: E402
from scripts.browser.overall_cleanup import browser as cleanup_browser  # noqa: E402
from scripts.browser.overall_cleanup import focus as cleanup_focus  # noqa: E402
from scripts.browser.overall_cleanup import grid as cleanup_grid  # noqa: E402
from scripts.browser.overall_cleanup import media_requests as cleanup_media_requests  # noqa: E402
from scripts.browser.overall_cleanup import mobile as cleanup_mobile  # noqa: E402
from scripts.browser.overall_cleanup import screenshots as cleanup_screenshots  # noqa: E402
from scripts.browser.overall_cleanup import surfaces as cleanup_surfaces  # noqa: E402
from scripts.browser.overall_cleanup import transforms as cleanup_transforms  # noqa: E402
from scripts.browser.viewer_probe import back as back_probe  # noqa: E402
from scripts.browser.viewer_probe import open as open_probe  # noqa: E402
from scripts.browser.viewer_probe import open_checks as open_checks  # noqa: E402
from scripts.browser.viewer_probe.config import BACK_CLICK_POINTS, BACK_SAMPLE_X_FRACS, BACK_SAMPLE_Y_FRACS  # noqa: E402


class _FakeLocator:
    def __init__(self, *, attributes: dict[str, str | None] | None = None) -> None:
        self.attributes = attributes or {}
        self.waits: list[dict] = []

    @property
    def first(self) -> "_FakeLocator":
        return self

    def get_attribute(self, name: str) -> str | None:
        return self.attributes.get(name)

    def wait_for(self, **kwargs) -> None:
        self.waits.append(kwargs)


class _FakeOverallPage:
    def __init__(
        self,
        evaluate_responses: list[object] | None = None,
        *,
        wait_error: Exception | None = None,
        locators: dict[str, _FakeLocator] | None = None,
        url: str = "http://lenslet.test/",
    ) -> None:
        self.evaluate_responses = list(evaluate_responses or [])
        self.wait_error = wait_error
        self.locators = locators or {}
        self.routes: list[tuple[str, object]] = []
        self.viewport_sizes: list[dict[str, int]] = []
        self.gotos: list[str] = []
        self.media_calls: list[dict] = []
        self.timeout_waits: list[float] = []
        self.url = url

    def evaluate(self, _script: str, _arg=None) -> object:
        if not self.evaluate_responses:
            raise AssertionError("unexpected evaluate call")
        response = self.evaluate_responses.pop(0)
        return response() if callable(response) else response

    def wait_for_function(self, _script: str, *, arg=None, timeout=None) -> None:
        _ = arg, timeout
        if self.wait_error is not None:
            raise self.wait_error

    def wait_for_timeout(self, timeout: float) -> None:
        self.timeout_waits.append(timeout)

    def locator(self, selector: str) -> _FakeLocator:
        return self.locators.get(selector, _FakeLocator())

    def route(self, pattern: str, handler) -> None:
        self.routes.append((pattern, handler))

    def set_viewport_size(self, size: dict[str, int]) -> None:
        self.viewport_sizes.append(size)

    def goto(self, url: str, **_kwargs) -> None:
        self.gotos.append(url)

    def get_by_role(self, _role: str, **_kwargs) -> _FakeLocator:
        return _FakeLocator()

    def emulate_media(self, **kwargs) -> None:
        self.media_calls.append(kwargs)


class _FakeRoute:
    def __init__(self, url: str) -> None:
        self.request = type("_Request", (), {"url": url})()
        self.continued = 0

    def continue_(self) -> None:
        self.continued += 1


def _viewer_frame(
    *,
    path: str = "/sample.jpg",
    elapsed_ms: int = 0,
    loading_state: str = "ready",
    neutral_loader_visible: bool = False,
) -> dict:
    return {
        "frame": 0,
        "elapsedMs": elapsed_ms,
        "loadingState": loading_state,
        "neutralLoaderVisible": neutral_loader_visible,
        "visibleImages": [{"viewerImage": "full", "currentPath": path}],
        "imageLikeElements": {
            "canvasCount": 0,
            "pictureCount": 0,
            "backgroundImages": [],
        },
    }


def test_viewer_open_acceptance_accepts_settled_full_image() -> None:
    scenario = {
        "name": "normal-fast-load",
        "openedPath": "/sample.jpg",
        "loaderExpected": False,
        "loaderForbidden": True,
        "riskSummary": {
            "thumbObserved": False,
            "fallbackObserved": False,
            "fullImageCrossfadeObserved": False,
            "duplicateVisibleImageObserved": False,
            "openFadeClassObserved": False,
        },
        "samples": {"samples": [_viewer_frame()]},
        "settled": {
            "dialogPath": "/sample.jpg",
            "imagePath": "/sample.jpg",
            "opacity": 1.0,
            "loadingState": "ready",
            "neutralLoaderVisible": False,
        },
    }

    assert open_checks.viewer_acceptance_failures([scenario]) == []


def test_viewer_open_acceptance_reports_loader_and_wrong_image() -> None:
    scenario = {
        "name": "bad-load",
        "openedPath": "/expected.jpg",
        "loaderExpected": False,
        "loaderForbidden": True,
        "riskSummary": {
            "thumbObserved": True,
            "fallbackObserved": False,
            "fullImageCrossfadeObserved": False,
            "duplicateVisibleImageObserved": False,
            "openFadeClassObserved": False,
        },
        "samples": {
            "samples": [
                {
                    **_viewer_frame(
                        path="/other.jpg",
                        loading_state="loading",
                        neutral_loader_visible=True,
                    ),
                }
            ]
        },
        "settled": {
            "dialogPath": "/expected.jpg",
            "imagePath": "/expected.jpg",
            "opacity": 1.0,
            "loadingState": "ready",
            "neutralLoaderVisible": False,
        },
    }

    failures = open_checks.viewer_acceptance_failures([scenario])

    assert any("thumbObserved is still true" in failure for failure in failures)
    assert any("neutral loader appeared" in failure for failure in failures)
    assert any("visible non-active image" in failure for failure in failures)


def test_viewer_open_sample_summary_tracks_transient_risks() -> None:
    summary = open_checks.summarize_open_samples(
        {
            "samples": [
                {
                    "thumb": {"opacity": 1.0},
                    "viewer": {"opacity": 0.5},
                    "fallback": {"tag": "DIV"},
                    "dialog": {"className": "z-viewer transition-opacity"},
                    "visibleImageCount": 2,
                },
                {
                    "viewer": {"opacity": 0.0},
                    "dialog": {"className": "z-viewer"},
                },
            ]
        }
    )

    assert summary == {
        "thumbObserved": True,
        "fallbackObserved": True,
        "fullImageCrossfadeObserved": True,
        "duplicateVisibleImageObserved": True,
        "invisibleFullImageObserved": True,
        "openFadeClassObserved": True,
    }


def test_viewer_open_probe_config_and_navigation_payloads() -> None:
    config = open_probe.ViewerOpenProbeConfig(
        timeout_ms=30_000,
        frames=24,
        interval_ms=20,
        delayed_file_route_ms=350,
    )
    trace = open_probe.ViewerNavigationTrace(
        from_path="/a.jpg",
        via_paths=("/b.jpg", "/c.jpg"),
        to_path="/d.jpg",
        direction="next",
    )

    assert config.viewport_size() == {"width": 1200, "height": 820}
    assert trace.as_payload() == {
        "from": "/a.jpg",
        "via": ["/b.jpg", "/c.jpg"],
        "to": "/d.jpg",
        "direction": "next",
    }


def test_back_acceptance_accepts_all_sampled_points_and_clicks() -> None:
    points = [
        {"resolvesToBack": True}
        for _ in range(len(BACK_SAMPLE_X_FRACS) * len(BACK_SAMPLE_Y_FRACS))
    ]
    clicks = [{"label": label, "closed": True} for label, _x, _y in BACK_CLICK_POINTS]

    assert back_probe.back_acceptance_failures(
        [{"name": "desktop", "sample": {"points": points}, "clicks": clicks}]
    ) == []


def test_back_acceptance_reports_missing_hit_targets_and_failed_clicks() -> None:
    points = [
        {"resolvesToBack": index != 0}
        for index in range(len(BACK_SAMPLE_X_FRACS) * len(BACK_SAMPLE_Y_FRACS))
    ]
    clicks = [{"label": "center", "closed": False}]

    failures = back_probe.back_acceptance_failures(
        [{"name": "mobile", "sample": {"points": points}, "clicks": clicks}]
    )

    assert any("do not resolve to Back" in failure for failure in failures)
    assert any("did not close viewer" in failure for failure in failures)


def test_overall_cleanup_path_from_grid_cell_id_decodes_path() -> None:
    assert cleanup_grid.path_from_grid_cell_id("cell-%2Fdogs%2Fsam%20ple.jpg") == "/dogs/sam ple.jpg"
    with pytest.raises(cleanup_browser.OverallCleanupBrowserFailure):
        cleanup_grid.path_from_grid_cell_id("row-%2Fdogs%2Fsample.jpg")


def test_overall_cleanup_interactions_filter_visible_grid_ids_and_media_urls() -> None:
    visible_ids = ["row-1", "cell-%2Fa.jpg", "cell-%2Fb.jpg", "cell-"]
    page = _FakeOverallPage([visible_ids, visible_ids])

    assert cleanup_grid.visible_grid_cell_ids(page) == [
        "cell-%2Fa.jpg",
        "cell-%2Fb.jpg",
        "cell-",
    ]
    assert cleanup_grid.wait_for_visible_grid_cell_ids(page, minimum_count=2, timeout_ms=100) == [
        "cell-%2Fa.jpg",
        "cell-%2Fb.jpg",
        "cell-",
    ]
    assert cleanup_media_requests.is_media_request("http://lenslet.test/thumb?path=%2Fa.jpg") is True
    assert cleanup_media_requests.is_media_request("http://lenslet.test/file?path=%2Fa.jpg") is True
    assert cleanup_media_requests.is_media_request("http://lenslet.test/api/browse") is False
    assert cleanup_screenshots.screenshot_suffix(["/tmp/a.png", "/tmp/b.png"]) == (
        " Screenshots: /tmp/a.png, /tmp/b.png"
    )


def test_overall_cleanup_fixture_and_summary_writes(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "fixtures"
    cleanup_browser.build_fixture_dataset(fixture_dir)

    assert (fixture_dir / "cleanup_fixture_00.png").is_file()
    assert (fixture_dir / "cleanup_nested" / "cleanup_fixture_nested.png").is_file()

    summary_path = tmp_path / "out" / "summary.json"
    cleanup_browser.write_summary(summary_path, {"status": "passed"})

    assert json.loads(summary_path.read_text(encoding="utf-8")) == {"status": "passed"}
    assert not list(summary_path.parent.glob(".*.tmp"))


def test_overall_cleanup_server_command_uses_current_cli_flags(tmp_path: Path) -> None:
    command = cleanup_browser.server_command(tmp_path / "images", host="127.0.0.1", port=7777)

    assert command[:4] == [sys.executable, "-m", "lenslet.cli", str(tmp_path / "images")]
    assert command[-5:] == ["--host", "127.0.0.1", "--port", "7777", "--verbose"]
    assert "--no-skip-indexing" not in command


def test_overall_cleanup_center_and_compare_assertions() -> None:
    before = {
        "normalizedCenter": {"x": 0.5, "y": 0.5},
    }
    after = {
        "name": "viewer",
        "normalizedCenter": {"x": 0.52, "y": 0.53},
        "container": {"width": 200, "height": 200},
        "naturalWidth": 600,
        "naturalHeight": 500,
        "transform": {"scaleX": 1.0, "scaleY": 1.0},
    }
    cleanup_transforms.assert_center_preserved(before, after)
    cleanup_transforms.assert_compare_split_in_range({"inlinePct": 50, "renderedPct": 50}, "compare")
    cleanup_transforms.assert_compare_split_changed({"inlinePct": 20}, {"inlinePct": 40}, "compare")
    cleanup_transforms.assert_compare_split_stable({"inlinePct": 40}, {"inlinePct": 40.5}, "compare")

    with pytest.raises(cleanup_browser.OverallCleanupBrowserFailure):
        cleanup_transforms.assert_center_preserved(
            before,
            {**after, "normalizedCenter": {"x": 0.7, "y": 0.5}},
        )
    with pytest.raises(cleanup_browser.OverallCleanupBrowserFailure):
        cleanup_transforms.assert_compare_split_in_range({"inlinePct": 3, "renderedPct": 50}, "compare")
    with pytest.raises(cleanup_browser.OverallCleanupBrowserFailure):
        cleanup_transforms.assert_compare_split_changed({"inlinePct": 20}, {"inlinePct": 25}, "compare")
    with pytest.raises(cleanup_browser.OverallCleanupBrowserFailure):
        cleanup_transforms.assert_compare_split_stable({"inlinePct": 40}, {"inlinePct": 42}, "compare")


def _adaptive_snapshot(*, legacy_label: bool = False, row_height: float = 220.0) -> dict:
    rows = []
    for row_index in range(3):
        rows.append(
            {
                "rowIndex": row_index,
                "imageHeight": row_height,
                "cells": [
                    {
                        "id": f"cell-{row_index}-a",
                        "fit": "contain" if row_index < 2 else "cover",
                        "rect": {"left": 0, "right": 200, "top": row_index * row_height, "bottom": (row_index + 1) * row_height},
                    },
                    {
                        "id": f"cell-{row_index}-b",
                        "fit": "cover",
                        "rect": {"left": 210, "right": 410, "top": row_index * row_height, "bottom": (row_index + 1) * row_height},
                    },
                ],
            }
        )
    return {
        "name": "adaptive",
        "grid": {"left": 0, "right": 420},
        "rows": rows,
        "labels": {
            "mobileJustified": "Justified rows",
            "bodyIncludesLegacyMasonry": legacy_label,
        },
    }


def test_overall_cleanup_geometry_assertions_accept_clean_snapshots() -> None:
    cleanup_grid.assert_adaptive_geometry(_adaptive_snapshot())
    cleanup_surfaces.assert_surface_inside_visible_bounds(
        {
            "name": "menu",
            "rect": {"left": 10, "right": 190, "top": 20, "bottom": 220},
            "bounds": {"left": 0, "right": 200, "top": 0, "bottom": 240},
        }
    )
    cleanup_transforms.assert_transform_stable(
        {"transform": {"scaleX": 1, "scaleY": 1, "tx": 10, "ty": 20}},
        {"transform": {"scaleX": 1.005, "scaleY": 1, "tx": 10.5, "ty": 20.5}},
        "viewer",
    )
    cleanup_transforms.assert_meaningfully_off_center({"normalizedCenter": {"x": 0.56, "y": 0.5}}, "viewer")
    cleanup_transforms.assert_surface_wheel_zoomed(
        {"transform": {"scaleX": 1.0}},
        {"transform": {"scaleX": 1.2}},
        "viewer",
    )


@pytest.mark.parametrize(
    ("check", "message"),
    [
        (lambda: cleanup_grid.assert_adaptive_geometry(_adaptive_snapshot(legacy_label=True)), "Legacy Masonry"),
        (
            lambda: cleanup_grid.assert_adaptive_geometry(_adaptive_snapshot(row_height=120)),
            "too short",
        ),
        (
            lambda: cleanup_surfaces.assert_surface_inside_visible_bounds(
                {
                    "name": "menu",
                    "rect": {"left": -5, "right": 190, "top": 20, "bottom": 220},
                    "bounds": {"left": 0, "right": 200, "top": 0, "bottom": 240},
                }
            ),
            "horizontally",
        ),
        (
            lambda: cleanup_transforms.assert_transform_stable(
                {"transform": {"scaleX": 1, "scaleY": 1, "tx": 0, "ty": 0}},
                {"transform": {"scaleX": 1, "scaleY": 1, "tx": 4, "ty": 0}},
                "viewer",
            ),
            "transform changed",
        ),
        (
            lambda: cleanup_transforms.assert_meaningfully_off_center(
                {"normalizedCenter": {"x": 0.51, "y": 0.5}},
                "viewer",
            ),
            "off-center",
        ),
        (
            lambda: cleanup_transforms.assert_surface_wheel_zoomed(
                {"transform": {"scaleX": 1.0}},
                {"transform": {"scaleX": 1.0}},
                "viewer",
            ),
            "did not increase",
        ),
    ],
)
def test_overall_cleanup_geometry_assertions_reject_bad_snapshots(check, message: str) -> None:
    with pytest.raises(cleanup_browser.OverallCleanupBrowserFailure, match=message):
        check()


def test_overall_cleanup_focus_and_alt_helpers_use_fake_page_objects() -> None:
    cleanup_focus.assert_focus_inside(_FakeOverallPage(), "#dialog", "dialog")
    cleanup_focus.assert_focus_restored(_FakeOverallPage([True]), "#cell", "cell")
    assert cleanup_focus.assert_focused_element_has_visible_outline(
        _FakeOverallPage([
            {
                "tag": "BUTTON",
                "text": "Close",
                "label": "Close",
                "outlineStyle": "solid",
                "outlineWidth": "2px",
                "boxShadow": "none",
            }
        ]),
        "dialog",
    )["label"] == "Close"
    assert cleanup_focus.assert_useful_image_alt(
        _FakeOverallPage(locators={"img": _FakeLocator(attributes={"alt": "red sample cat"})}),
        "img",
        "viewer",
        {"viewer"},
    ) == "red sample cat"

    with pytest.raises(cleanup_browser.OverallCleanupBrowserFailure, match="Focus escaped"):
        cleanup_focus.assert_focus_inside(
            _FakeOverallPage([{"tag": "BODY"}], wait_error=RuntimeError("lost focus")),
            "#dialog",
            "dialog",
        )
    with pytest.raises(cleanup_browser.OverallCleanupBrowserFailure, match="did not restore"):
        cleanup_focus.assert_focus_restored(_FakeOverallPage([False, {"tag": "BODY"}]), "#cell", "cell")
    with pytest.raises(cleanup_browser.OverallCleanupBrowserFailure, match="no visible focus style"):
        cleanup_focus.assert_focused_element_has_visible_outline(
            _FakeOverallPage([
                {
                    "tag": "BUTTON",
                    "outlineStyle": "none",
                    "outlineWidth": "0px",
                    "boxShadow": "none",
                }
            ]),
            "dialog",
        )
    with pytest.raises(cleanup_browser.OverallCleanupBrowserFailure, match="generic alt"):
        cleanup_focus.assert_useful_image_alt(
            _FakeOverallPage(locators={"img": _FakeLocator(attributes={"alt": "viewer"})}),
            "img",
            "viewer",
            {"viewer"},
        )


def test_overall_cleanup_route_delay_helpers_count_matching_requests() -> None:
    nth_page = _FakeOverallPage()
    nth_state, nth_handler = cleanup_media_requests.delay_nth_file_request(nth_page, request_index=2, delay_ms=0)
    first = _FakeRoute("http://lenslet.test/file?path=%2Fa.jpg")
    second = _FakeRoute("http://lenslet.test/file?path=%2Fb.jpg")

    nth_handler(first)
    nth_handler(second)

    assert nth_page.routes[0][0] == "**/file?*"
    assert nth_state == {"count": 2, "delayed": 1}
    assert first.continued == 1
    assert second.continued == 1

    path_page = _FakeOverallPage()
    path_state, path_handler = cleanup_media_requests.delay_file_path_requests(
        path_page,
        target_path="/b.jpg",
        delay_ms=0,
    )
    path_handler(_FakeRoute("http://lenslet.test/file?path=%2Fa.jpg"))
    matched = _FakeRoute("http://lenslet.test/file?path=%2Fb.jpg")
    path_handler(matched)

    assert path_state == {"count": 2, "delayed": 1}
    assert matched.continued == 1


def test_overall_cleanup_pointer_and_motion_helpers_use_fake_pages() -> None:
    coarse_snapshot = {
        "coarse": True,
        "gridAction": {"visible": True, "opacity": "1"},
        "folderAction": {"visible": True, "opacity": "0.98"},
    }
    coarse_page = _FakeOverallPage([coarse_snapshot])

    assert cleanup_mobile.verify_coarse_pointer_actions(coarse_page, timeout_ms=1000) == coarse_snapshot
    assert coarse_page.viewport_sizes == [{"width": 900, "height": 700}]

    reduced_snapshot = {
        "reduced": True,
        "probeTransitionDuration": "0s",
        "probeAnimationName": "none",
        "animated": [],
    }
    reduced_page = _FakeOverallPage([reduced_snapshot])

    assert cleanup_mobile.verify_reduced_motion(reduced_page, timeout_ms=1000) == reduced_snapshot
    assert reduced_page.media_calls == [{"reduced_motion": "reduce"}]

    with pytest.raises(cleanup_browser.OverallCleanupBrowserFailure, match="Coarse pointer emulation"):
        cleanup_mobile.verify_coarse_pointer_actions(_FakeOverallPage([{"coarse": False}]), timeout_ms=1000)
    with pytest.raises(cleanup_browser.OverallCleanupBrowserFailure, match="active animation"):
        cleanup_mobile.verify_reduced_motion(
            _FakeOverallPage([{"reduced": True, "animated": [{"className": "spin"}]}]),
            timeout_ms=1000,
        )


def test_jitter_probe_delta_helpers_handle_missing_and_numeric_values() -> None:
    left = {
        "anchors": {"search": {"left": 10, "width": 100, "top": 5}},
        "height": 40,
        "bandHeights": {"filters": 12},
        "present": True,
        "top": 20,
    }
    right = {
        "anchors": {"search": {"left": 12, "width": 95, "top": 9}},
        "height": "43",
        "bandHeights": {"filters": "18"},
        "present": True,
        "top": 25,
    }

    assert jitter_toolbar.anchor_delta(left, right, "search") == 5
    assert jitter_toolbar.anchor_delta(left, right, "missing") is None
    assert jitter_shared.state_delta(left, right, "height") == 3
    assert jitter_shared.state_delta_nested(left, right, "bandHeights", "filters") == 6
    assert jitter_inspector.quick_view_delta(
        {**left, "height": 40},
        {**right, "height": 44},
    ) == 5


def test_jitter_probe_hidden_control_state_reports_accessibility_contract() -> None:
    violations: list[str] = []
    jitter_toolbar.assert_hidden_control_state(
        {
            "controls": {
                "selectAll": {
                    "disabled": False,
                    "tabIndex": 0,
                    "ariaHidden": False,
                }
            }
        },
        "selectAll",
        "narrow toolbar",
        violations,
    )

    assert violations == [
        "narrow toolbar: expected selectAll to be disabled",
        "narrow toolbar: expected selectAll tabindex=-1",
        "narrow toolbar: expected selectAll aria-hidden=true",
    ]


def test_jitter_fixture_builder_creates_parquet_and_label_snapshot(tmp_path: Path) -> None:
    jitter_fixtures.build_fixture_dataset(tmp_path)

    image_paths = [
        path.relative_to(tmp_path).as_posix()
        for path in jitter_fixtures.fixture_image_paths(tmp_path)
    ]

    assert callable(jitter_probe.parse_args)
    assert "sample_000.jpg" in image_paths
    assert "quick_00_meta.png" in image_paths
    assert "scope_a/scope_00.jpg" in image_paths
    assert (tmp_path / "items.parquet").is_file()
    assert (tmp_path / ".lenslet" / "labels.snapshot.json").is_file()


def test_jitter_grid_result_helpers_compare_named_snapshots() -> None:
    snapshots = jitter_grid.GridProbeSnapshots(
        warmup_filters_active={},
        builtin_initial={
            "topStackHeight": 10,
            "bandHeights": {"status": 2, "similarity": 3, "filters": 4},
        },
        filters_active={
            "topStackHeight": 12,
            "bandHeights": {"status": 2, "similarity": 5, "filters": 4},
        },
        filters_cleared={
            "topStackHeight": 11,
            "bandHeights": {"status": 2, "similarity": 3, "filters": 7},
        },
        metric_mode={"gridBodyWidth": 800, "firstCellLeft": 20, "firstCellWidth": 120, "metricRailWidth": 44},
        builtin_restored={"gridBodyWidth": 790, "firstCellLeft": 22, "firstCellWidth": 118, "metricRailWidth": 40},
        metric_sort_label="probe_score",
    )

    top_stack = jitter_grid.grid_top_stack_deltas(snapshots)
    widths = jitter_grid.grid_width_deltas(snapshots)

    assert top_stack["baseline_to_filters_top_stack_delta"] == 2
    assert top_stack["baseline_to_restored_filters_band_delta"] == 3
    assert widths["metric_to_restored_body_width_delta"] == 10
    assert jitter_grid_dom.COUNT_LABEL_RE.match("1,234 / 2,000 items")


def test_jitter_grid_state_uses_visible_sort_controls() -> None:
    snapshots = jitter_grid.GridProbeSnapshots(
        warmup_filters_active={},
        builtin_initial={},
        filters_active={},
        filters_cleared={},
        metric_mode={"metricRailActive": True, "sortLabel": "probe_score"},
        builtin_restored={"sortLabel": "Date added"},
        metric_sort_label="probe_score",
        metric_desc_visible_paths=["/b.jpg", "/a.jpg"],
        metric_asc_visible_paths=["/a.jpg", "/b.jpg"],
    )

    assert jitter_grid.grid_state_violations(snapshots) == []


def test_jitter_grid_false_zero_detection_distinguishes_unknown_from_settled_empty() -> None:
    pending = {
        "phase": "loading",
        "gridState": "loading",
        "countLabel": "0 items",
        "filteredLabels": [],
    }
    unknown = {
        "phase": "loading",
        "gridState": "loading",
        "countLabel": None,
        "filteredLabels": [],
    }

    assert jitter_grid._false_zero_frames([pending, unknown]) == [pending]


def test_jitter_grid_identity_trace_requires_atomic_grace_and_inert_rail() -> None:
    frames = [
        {
            "phase": "steady",
            "paths": ["/a.jpg"],
            "presentedTarget": "a",
            "requestedTarget": "a",
            "epoch": 1,
        },
        {
            "phase": "grace",
            "paths": ["/a.jpg"],
            "presentedTarget": "a",
            "requestedTarget": "b",
            "epoch": 1,
            "railActive": True,
            "railInteractionDisabled": True,
        },
        {
            "phase": "steady",
            "paths": ["/b.jpg"],
            "presentedTarget": "b",
            "requestedTarget": "b",
            "epoch": 2,
        },
    ]

    assert jitter_grid._transition_identity_violations("sort", frames) == []

    frames[1]["railInteractionDisabled"] = False
    assert jitter_grid._transition_identity_violations("sort", frames) == [
        "sort: active metric rail remained interactive during grace"
    ]

    assert jitter_grid._transition_identity_violations("sort", frames[:2])[-1] == (
        "sort: terminal steady identity did not match the requested target"
    )
