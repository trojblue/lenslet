from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.browser.responsive_geometry import evidence  # noqa: E402
from scripts.browser.responsive_geometry.types import Scenario  # noqa: E402


class _FakePage:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, object | None]] = []

    def evaluate(self, script: str, arg: object | None = None) -> object:
        self.calls.append((script, arg))
        if not self.responses:
            raise AssertionError("unexpected page.evaluate call")
        return self.responses.pop(0)


def _toolbar_control(
    name: str,
    *,
    visible: bool = True,
    hit_target_ok: bool = True,
    keyboard_focusable: bool = True,
    focus_disabled: bool = False,
) -> dict[str, Any]:
    return {
        "name": name,
        "visible": visible,
        "ariaHidden": None,
        "hitTargetOk": hit_target_ok,
        "keyboardFocusable": keyboard_focusable,
        "focusDisabled": focus_disabled,
        "rect": {"left": 0, "right": 40, "top": 0, "bottom": 32, "width": 40, "height": 32},
    }


def _visible_image(path: str = "/gallery/a.jpg", *, opacity: float = 1.0) -> dict[str, Any]:
    return {
        "complete": True,
        "naturalWidth": 320,
        "naturalHeight": 180,
        "opacity": opacity,
        "display": "block",
        "visibility": "visible",
        "currentPath": path,
        "rect": {"left": 0, "right": 320, "top": 0, "bottom": 180, "width": 320, "height": 180},
    }


def _contained_overlay_snapshot(name: str, *, mode: str = "viewer") -> dict[str, Any]:
    return {
        "name": name,
        "viewport": {"width": 1200, "height": 800},
        "layout": {
            "overlayMode": mode,
            "effectiveLeftWidth": "220",
            "effectiveRightWidth": "220",
            "leftSuppressionReason": None,
            "rightSuppressionReason": None,
        },
        "cssVars": {"overlayLeft": "220px", "overlayRight": "220px"},
        "focus": {
            "browseShellInert": True,
            "browseShellAriaHidden": "true",
            "toolbarInert": mode == "compare",
            "toolbarAriaHidden": "true" if mode == "compare" else None,
            "activeElement": {"inBrowseShell": False, "inOverlayDialog": True},
        },
        "rects": {
            "leftSidebar": {"left": 0, "right": 220, "width": 220},
            "rightSidebar": {"left": 980, "right": 1200, "width": 220},
            "gridShell": {"left": 220, "right": 980, "width": 760},
            "overlay": {"left": 220, "right": 980, "width": 760},
            "compareStage": {"left": 230, "right": 970, "width": 740},
        },
        "toolbarControls": [_toolbar_control("back")],
    }


def test_responsive_evidence_scenario_state_copies_storage() -> None:
    scenario = Scenario(
        name="phone",
        width=390,
        height=844,
        storage={"leftOpen": "1"},
        open_mobile_search=True,
        has_touch=True,
        select_first=True,
        assert_inspector=True,
    )

    state = evidence.scenario_state(scenario)
    scenario.storage["leftOpen"] = "0"

    assert state == {
        "width": 390,
        "height": 844,
        "storage": {"leftOpen": "1"},
        "openMobileSearch": True,
        "hasTouch": True,
        "selectFirst": True,
        "assertInspector": True,
    }


def test_responsive_evidence_collect_snapshot_merges_all_collectors() -> None:
    shell_snapshot = {
        "name": "desktop",
        "viewport": {"width": 1200, "height": 800},
        "layout": {"mode": "desktop"},
        "cssVars": {},
        "scroll": {"scrollWidth": 1200, "clientWidth": 1200},
        "rects": {"shell": {"width": 1200}},
    }
    page = _FakePage([
        shell_snapshot,
        {"viewer": _visible_image()},
        {"focus": {"activeElement": None}, "selection": {"ariaSelectedCount": 0}, "themeMenu": {"labels": []}, "storage": {}},
        {"leftPanel": None, "inspector": None},
        [_toolbar_control("sort")],
    ])

    snapshot = evidence.collect_snapshot(page, "desktop", {"width": 1200})

    assert snapshot["name"] == "desktop"
    assert snapshot["images"]["viewer"]["currentPath"] == "/gallery/a.jpg"
    assert snapshot["toolbarControls"][0]["name"] == "sort"
    assert page.calls[0][1] == {"name": "desktop", "state": {"width": 1200}}


def test_responsive_evidence_collect_snapshot_rejects_missing_shell() -> None:
    with pytest.raises(evidence.ResponsiveGeometryFailure, match="App shell"):
        evidence.collect_snapshot(_FakePage([{"name": "missing", "missingShell": True}]), "missing")


def test_responsive_evidence_overlay_contracts_accept_contained_viewer() -> None:
    before = _contained_overlay_snapshot("before")
    after = _contained_overlay_snapshot("after")

    evidence.assert_overlay_contained_to_center(before, after, "viewer")
    evidence.assert_viewer_toolbar_chrome(after)
    evidence.assert_overlay_closed(
        {"layout": {"overlayMode": "none"}, "focus": {"activeElement": {"inOverlayDialog": False}}},
        "after-close",
    )


def test_responsive_evidence_overlay_contracts_reject_suppression_and_bad_chrome() -> None:
    before = _contained_overlay_snapshot("before")
    after = _contained_overlay_snapshot("after")
    after["layout"] = {**after["layout"], "leftSuppressionReason": "overlay-active"}

    with pytest.raises(evidence.ResponsiveGeometryFailure, match="suppressed the left side"):
        evidence.assert_overlay_contained_to_center(before, after, "viewer")
    with pytest.raises(evidence.ResponsiveGeometryFailure, match="back control"):
        evidence.assert_viewer_toolbar_chrome({**before, "toolbarControls": [_toolbar_control("back", hit_target_ok=False)]})


def test_responsive_evidence_overlay_image_stability_checks_paths_and_visibility() -> None:
    samples = {
        "name": "viewer",
        "samples": [
            {"frame": 0, "images": {"viewer": _visible_image("/gallery/a.jpg")}},
            {"frame": 1, "images": {"viewer": _visible_image("/gallery/a.jpg")}},
        ],
    }

    evidence.assert_overlay_image_stable(samples, ("viewer",), {"viewer": "/gallery/a.jpg"})

    wrong_path = {"name": "viewer", "samples": [{"frame": 0, "images": {"viewer": _visible_image("/gallery/b.jpg")}}]}
    with pytest.raises(evidence.ResponsiveGeometryFailure, match="wrong current path"):
        evidence.assert_overlay_image_stable(wrong_path, ("viewer",), {"viewer": "/gallery/a.jpg"})

    flicker = {
        "name": "viewer",
        "samples": [
            {"frame": 0, "images": {"viewer": _visible_image("/gallery/a.jpg")}},
            {"frame": 1, "images": {"viewer": _visible_image("/gallery/a.jpg", opacity=0.0)}},
        ],
    }
    with pytest.raises(evidence.ResponsiveGeometryFailure, match="became invisible"):
        evidence.assert_overlay_image_stable(flicker, ("viewer",), {"viewer": "/gallery/a.jpg"})


def test_responsive_evidence_metrics_left_760_accepts_visible_and_suppressed_states() -> None:
    visible = {
        "name": "metrics-left",
        "state": {"activeLeftTool": "metrics", "selectedCount": 2},
        "selection": {"ariaSelectedCount": 2},
        "viewport": {"width": 760},
        "storage": {"leftOpen": "1", "rightOpen": "1"},
        "layout": {"mode": "narrow", "effectiveLeftWidth": "280"},
        "leftPanel": {
            "activeTool": "metrics",
            "horizontalOverflow": False,
            "selectedMetricsCard": {"overflowsPanel": False, "childOverflowCount": 0},
        },
    }
    suppressed = {
        **visible,
        "layout": {
            "mode": "narrow",
            "effectiveLeftWidth": "0",
            "leftSuppressionReason": "insufficient-center-space",
        },
        "leftPanel": None,
    }

    evidence.assert_metrics_left_760_observed(visible)
    evidence.assert_metrics_left_760_observed(suppressed)

    with pytest.raises(evidence.ResponsiveGeometryFailure, match="unexpected reason"):
        evidence.assert_metrics_left_760_observed(
            {**suppressed, "layout": {**suppressed["layout"], "leftSuppressionReason": "overlay-active"}}
        )
