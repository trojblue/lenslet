from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.browser.gui_jitter.painted_frames import (
    assert_painted_frame_summary,
    percentile,
    summarize_painted_frame_trace,
)
from scripts.browser.gui_jitter.inspector import request_attribution_violations
from scripts.smoke_harness import SmokeFailure


REQUIRED = ("panel", "filename", "basics", "metadata", "notes", "quick_view")
SENTINELS = {
    "/alpha.png": ("alpha.png", "alpha prompt", "alpha notes"),
    "/beta.png": ("beta.png", "beta prompt", "beta notes"),
}


def _surface(name: str, *, token: str | None = None, text: str = "", top: float = 0.0) -> dict:
    return {
        "token": token or f"node-{name}",
        "rect": {"top": top, "left": 0.0, "width": 100.0, "height": 20.0},
        "text": text,
        "value": None,
        "visible": True,
        "attrs": {"ariaPressed": None, "ariaBusy": None},
    }


def _surfaces(path: str = "/alpha.png") -> dict:
    filename = path.rsplit("/", 1)[-1]
    prompt = "alpha prompt" if path == "/alpha.png" else "beta prompt"
    surfaces = {
        "panel": _surface("panel", text=f"{filename} {prompt}"),
        "filename": _surface("filename", text=filename),
        "basics": _surface("basics", text="Basics"),
        "metadata": _surface("metadata", text=prompt),
        "notes": _surface("notes", text="Notes"),
        "quick_view": _surface("quick_view", text=prompt),
    }
    for star in range(1, 6):
        surfaces[f"star_{star}"] = {
            **_surface(f"star_{star}"),
            "attrs": {
                "ariaPressed": "true" if star == 1 else "false",
                "ariaBusy": None,
            },
        }
    return surfaces


def _valid_trace() -> dict:
    marker = {
        "actionId": "rating-1",
        "expectedPath": "/alpha.png",
        "expectedStar": 1,
        "startedAt": 10.0,
    }
    return {
        "page_id": "owner",
        "phase": "local_rating",
        "markers": [marker],
        "frames": [
            {"timestamp": 8.0, "marker": None, "surfaces": _surfaces()},
            {"timestamp": 14.0, "marker": marker, "surfaces": _surfaces()},
        ],
    }


def _summary(trace: object) -> dict:
    return summarize_painted_frame_trace(
        trace,
        required_surfaces=REQUIRED,
        sentinels_by_path=SENTINELS,
        max_delta_px=1.0,
    )


def test_percentile_interpolates_and_handles_empty_values() -> None:
    assert percentile([], 95.0) == 0.0
    assert percentile([5.0], 95.0) == 5.0
    assert percentile([0.0, 10.0], 50.0) == 5.0


@pytest.mark.parametrize("trace", [None, {}, {"frames": [], "markers": []}])
def test_trace_summary_fails_closed_for_malformed_or_empty_input(trace: object) -> None:
    summary = _summary(trace)
    with pytest.raises(SmokeFailure):
        assert_painted_frame_summary(summary)


def test_trace_summary_requires_post_action_frames_and_markers() -> None:
    trace = _valid_trace()
    trace["frames"] = trace["frames"][:1]
    summary = _summary(trace)
    assert any("no post-action painted frame" in value for value in summary["violations"])


def test_trace_summary_rejects_missing_and_replaced_required_nodes() -> None:
    trace = _valid_trace()
    trace["frames"][1]["surfaces"]["notes"] = None
    summary = _summary(trace)
    assert summary["missing_required_surface_frames"] == 1

    trace = _valid_trace()
    trace["frames"][1]["surfaces"]["notes"]["token"] = "replacement"
    summary = _summary(trace)
    assert summary["root_or_required_nodes_replaced"] is True


def test_trace_summary_rejects_geometry_blank_and_stale_frames() -> None:
    trace = _valid_trace()
    trace["frames"][1]["surfaces"]["basics"]["rect"]["top"] = 1.1
    trace["frames"][1]["surfaces"]["panel"]["text"] = "Loading inspector... beta prompt"
    summary = _summary(trace)
    assert summary["max_anchor_delta_px"] == pytest.approx(1.1)
    assert summary["blank_or_fallback_frames"] == 1
    assert summary["stale_text_frames"] == 1
    assert summary["failing_frames"]


def test_trace_summary_rejects_invisible_zero_size_blank_surfaces() -> None:
    trace = _valid_trace()
    for surface in trace["frames"][1]["surfaces"].values():
        surface["visible"] = False
        surface["rect"]["width"] = 0.0
        surface["rect"]["height"] = 0.0
        surface["text"] = ""
    summary = _summary(trace)
    assert summary["missing_required_surface_frames"] == 1
    assert summary["blank_or_fallback_frames"] >= 1
    assert summary["failing_frames"]


def test_trace_summary_enforces_delayed_rating_invariant() -> None:
    trace = _valid_trace()
    marker = trace["markers"][0]
    marker["expectedStar"] = 0
    marker["enforceStarInvariant"] = True
    summary = _summary(trace)
    assert any("rating invariant" in value for value in summary["violations"])
    assert summary["failing_frames"]


def test_trace_summary_requires_marker_content_on_every_painted_frame() -> None:
    trace = _valid_trace()
    trace["markers"][0]["requiredTexts"] = ["alpha prompt", "dirty notes"]
    trace["frames"][1]["marker"]["requiredTexts"] = ["alpha prompt", "dirty notes"]
    summary = _summary(trace)
    assert summary["missing_expected_content_frames"] == 1
    assert any("current-path content" in value for value in summary["violations"])
    assert summary["failing_frames"]


def test_expected_state_failure_retains_a_failing_frame() -> None:
    trace = _valid_trace()
    trace["markers"][0]["expectedStar"] = 5
    trace["frames"][1]["marker"]["expectedStar"] = 5
    summary = _summary(trace)
    assert any("never painted its expected state" in value for value in summary["violations"])
    assert any(
        frame.get("reason") == "expected state was never painted"
        for frame in summary["failing_frames"]
    )


def test_request_attribution_rejects_wrong_owner_phase_and_identity() -> None:
    allowed = {("GET", "/item", "/alpha.png")}
    records = [
        {
            "page_id": "wrong-page",
            "phase": "wrong-phase",
            "method": "GET",
            "pathname": "/item",
            "path": "/alpha.png",
        },
        {
            "page_id": "owner",
            "phase": "selection",
            "method": "PATCH",
            "pathname": "/metadata",
            "path": "/beta.png",
        },
    ]
    violations = request_attribution_violations(
        records,
        page_id="owner",
        phase="selection",
        allowed=allowed,
    )
    assert any("attribution" in value for value in violations)
    assert any("unexpected identity" in value for value in violations)


def test_request_attribution_enforces_exact_and_max_counts() -> None:
    identity = ("PATCH", "/item", "/alpha.png")
    records = [
        {
            "page_id": "owner",
            "phase": "rating",
            "method": identity[0],
            "pathname": identity[1],
            "path": identity[2],
        }
        for _ in range(2)
    ]
    violations = request_attribution_violations(
        records,
        page_id="owner",
        phase="rating",
        allowed={identity},
        exact_counts={identity: 1},
        max_counts={identity: 1},
    )
    assert any("instead of 1" in value for value in violations)
    assert any("maximum is 1" in value for value in violations)


def test_trace_summary_accepts_complete_path_consistent_frames() -> None:
    summary = _summary(_valid_trace())
    assert summary["paint_p95_ms"] == 4.0
    assert summary["violations"] == []
    assert_painted_frame_summary(summary)
