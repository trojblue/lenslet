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
from scripts.browser.gui_jitter import grid_hover_preview  # noqa: E402
from scripts.browser.gui_jitter import grid_dom as jitter_grid_dom  # noqa: E402
from scripts.browser.gui_jitter import inspector as jitter_inspector  # noqa: E402
from scripts.browser.gui_jitter import metrics as jitter_metrics  # noqa: E402
from scripts.browser.gui_jitter import metrics_derived as jitter_metrics_derived  # noqa: E402
from scripts.browser.gui_jitter import metrics_schema as jitter_metrics_schema  # noqa: E402
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
from scripts.browser.viewer_probe import flicker_back as viewer_probe_entrypoint  # noqa: E402
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


def _metrics_surface(
    token: str,
    text: str,
    *,
    field: str | None = None,
    state: str | None = None,
) -> dict:
    return {
        "token": token,
        "rect": {"top": 0, "left": 0, "width": 100, "height": 40},
        "text": text,
        "value": None,
        "visible": True,
        "attrs": {
            "data": {
                **({"data-categorical-card": field} if field else {}),
                **({"data-facet-state": state} if state else {}),
            },
        },
    }


def _metrics_marker(field: str) -> dict:
    return {"actionId": f"select-{field}", "expectedPath": field, "startedAt": 1.0}


def test_metrics_facet_summary_rejects_previous_field_data_under_target_label() -> None:
    trace = {
        "frames": [
            {
                "surfaces": {
                    "categorical_card": _metrics_surface("card", "Population: 10 synthetic"),
                    "categorical_selector": _metrics_surface("selector", "dataset_from"),
                    "next_control": _metrics_surface("next", "Attributes"),
                }
            },
            {
                "marker": _metrics_marker("review_group"),
                "surfaces": {
                    "categorical_card": _metrics_surface(
                        "card", "Population: 10 synthetic", field="review_group", state="ready",
                    ),
                    "categorical_selector": _metrics_surface("selector", "review_group"),
                    "next_control": _metrics_surface("next", "Attributes"),
                }
            },
        ]
    }

    summary = jitter_metrics._target_facet_trace_summary(
        trace,
        previous_field="dataset_from",
        field="review_group",
        terminal_state="ready",
        forbidden_texts=("synthetic",),
        expected_text="Population: 10",
        max_delta_px=1.0,
    )

    assert any("previous field" in violation for violation in summary["violations"])


def test_metrics_field_ownership_rejects_rendered_keys_missing_from_request() -> None:
    surfaces = {
        "metrics_panel": {
            "attrs": {
                "data": {
                    "data-requested-metric-fields": json.dumps(["quality_score"]),
                    "data-requested-categorical-fields": json.dumps(["review_group"]),
                }
            }
        },
        "metric_virtual_list": {
            "visible": True,
            "attrs": {
                "data": {
                    "data-rendered-field-keys": json.dumps(
                        ["contrast_score", "quality_score"]
                    )
                }
            },
        },
    }

    assert jitter_metrics._requested_field_ownership_violations(surfaces) == [
        "rendered metric fields lacked first-frame query ownership: ['contrast_score']"
    ]

    surfaces["metrics_panel"]["attrs"]["data"]["data-requested-metric-fields"] = json.dumps(
        ["contrast_score", "quality_score"]
    )
    assert jitter_metrics._requested_field_ownership_violations(surfaces) == []


def _metrics_reset_frame(metric_state: str, metric_text: str, categorical_state: str, categorical_text: str) -> dict:
    def surface(text: str, data: dict[str, str]) -> dict:
        value = _metrics_surface(text, text)
        value["attrs"]["data"] = data
        return value

    return {
        "surfaces": {
            "metrics_panel": surface("panel", {"data-presentation-reset-key": "reset-b"}),
            "metric_selector": surface("quality_score", {}),
            "metric_card": surface(metric_text, {
                "data-metric-card-host": "quality_score",
                "data-facet-state": metric_state,
            }),
            "categorical_selector": surface("review_group", {}),
            "categorical_card": surface(categorical_text, {
                "data-categorical-card": "review_group",
                "data-facet-state": categorical_state,
            }),
        }
    }


def test_metrics_single_field_reset_accepts_neutral_then_distinct_terminal_target() -> None:
    trace = {"frames": [
        _metrics_reset_frame(
            "pending",
            "Population: — Loading values for this metric…",
            "pending",
            "Population: — Loading values for this field…",
        ),
        _metrics_reset_frame(
            "ready",
            "Population: 1585 10.00 20.00",
            "empty",
            "Population: — No values found for this field.",
        ),
    ]}

    summary = jitter_metrics._single_field_reset_summary(
        trace,
        previous_reset_key="reset-a",
    )

    assert summary["violations"] == []


def test_metrics_single_field_reset_rejects_retained_previous_snapshot() -> None:
    trace = {"frames": [_metrics_reset_frame(
        "ready",
        "Population: 1585 0.000 1.000",
        "ready",
        "Population: 1585 review-0 review-1",
    )]}

    summary = jitter_metrics._single_field_reset_summary(
        trace,
        previous_reset_key="reset-a",
    )

    assert any("retained or mixed" in violation for violation in summary["violations"])


def _metrics_virtual_surface(cards: list[dict]) -> dict:
    surface = _metrics_surface("virtual-list", "cards")
    surface["attrs"]["data"]["data-rendered-field-keys"] = json.dumps(
        [card["key"] for card in cards]
    )
    surface["facetCards"] = cards
    return surface


def _metrics_virtual_card(
    key: str,
    state: str,
    text: str,
    *,
    retained: bool = False,
) -> dict:
    return {
        "key": key,
        "requested": key,
        "presented": key,
        "state": state,
        "text": text,
        "ariaBusy": "true" if retained else None,
        "ariaDisabled": "true" if retained else None,
        "inert": retained,
    }


def test_metrics_virtual_card_continuity_allows_neutral_cold_and_inert_retained_cards() -> None:
    trace = [{"surfaces": {"metric_virtual_list": _metrics_virtual_surface([
        _metrics_virtual_card("known", "ready", "Population: 10"),
        _metrics_virtual_card("cold", "pending", "Loading values for this metric…"),
    ])}}, {"surfaces": {"metric_virtual_list": _metrics_virtual_surface([
        _metrics_virtual_card("known", "ready", "Population: 10", retained=True),
        _metrics_virtual_card("cold", "ready", "Population: 12"),
    ])}}]

    assert jitter_metrics._virtual_card_continuity_violations(
        trace,
        surface_names=("metric_virtual_list",),
        initially_settled=frozenset(),
    ) == []

    trace[1]["surfaces"]["metric_virtual_list"]["facetCards"][0]["inert"] = False
    assert jitter_metrics._virtual_card_continuity_violations(
        trace,
        surface_names=("metric_virtual_list",),
        initially_settled=frozenset(),
    ) == ["retained Show-all field 'known' was not disabled and inert"]


def test_metrics_virtual_field_reset_requires_neutral_first_frame_and_terminal_card() -> None:
    pending = _metrics_virtual_card(
        "contrast_score", "pending", "Loading values for this metric…"
    )
    ready = _metrics_virtual_card("contrast_score", "ready", "Population: 1585")
    trace = {"frames": [
        {"surfaces": {
            "metrics_panel": {
                "attrs": {"data": {"data-presentation-reset-key": "reset-b"}}
            },
            "metric_virtual_list": _metrics_virtual_surface([pending]),
        }},
        {"surfaces": {
            "metrics_panel": {
                "attrs": {"data": {"data-presentation-reset-key": "reset-b"}}
            },
            "metric_virtual_list": _metrics_virtual_surface([ready]),
        }},
    ]}

    summary = jitter_metrics._virtual_field_reset_summary(
        trace,
        previous_reset_key="reset-a",
        expectations=(("metric_virtual_list", "contrast_score", "Population: 1585"),),
    )

    assert summary["violations"] == []


def _metrics_schema_frame(
    schema: list[str],
    *,
    requested: list[str],
    rendered: list[str],
    scroll_top: int = 0,
    visible: bool = True,
    action_id: str = "schema-test",
) -> dict:
    return {
        "marker": {"actionId": action_id},
        "surfaces": {
            "metrics_panel": {
                "attrs": {"data": {
                    "data-metric-field-schema": json.dumps(schema, separators=(",", ":")),
                    "data-requested-metric-fields": json.dumps(requested),
                }},
            },
            "metric_virtual_list": {
                "visible": visible,
                "scrollTop": scroll_top,
                "attrs": {"data": {
                    "data-rendered-field-keys": json.dumps(rendered),
                }},
            },
        },
    }


def test_metrics_schema_transition_requires_top_owned_earliest_frame() -> None:
    schema = [f"metric_{index:02d}" for index in range(30)]
    expected_batch = schema[:24]
    frame = _metrics_schema_frame(
        schema,
        requested=expected_batch,
        rendered=expected_batch[:6],
    )

    summary = jitter_metrics_schema._schema_transition_summary(
        {"frames": [frame]},
        schema,
        True,
    )

    assert summary["violations"] == []

    frame["surfaces"]["metric_virtual_list"]["scrollTop"] = 120
    frame["surfaces"]["metric_virtual_list"]["attrs"]["data"][
        "data-rendered-field-keys"
    ] = json.dumps([schema[-1]])
    summary = jitter_metrics_schema._schema_transition_summary(
        {"frames": [frame]},
        schema,
        True,
    )

    assert any("retained scrollTop" in violation for violation in summary["violations"])
    assert any("rendered unowned fields" in violation for violation in summary["violations"])


def test_metrics_schema_transition_rejects_stale_first_post_action_frame() -> None:
    schema_a = [f"old_{index:02d}" for index in range(30)]
    schema_b = [f"new_{index:02d}" for index in range(30)]
    stale = _metrics_schema_frame(
        schema_a,
        requested=schema_a[-24:],
        rendered=schema_a[-6:],
        scroll_top=120,
    )
    settled = _metrics_schema_frame(
        schema_b,
        requested=schema_b[:24],
        rendered=schema_b[:6],
    )

    summary = jitter_metrics_schema._schema_transition_summary(
        {"frames": [stale, settled]},
        schema_b,
        True,
    )

    assert any("earliest post-action frame painted schema" in value for value in summary["violations"])


def test_metrics_facet_summary_rejects_pending_to_target_ready_in_one_shell() -> None:
    trace = {
        "frames": [
            {
                "surfaces": {
                    "categorical_card": _metrics_surface("card", "Population: 10 synthetic"),
                    "categorical_selector": _metrics_surface("selector", "dataset_from"),
                    "next_control": _metrics_surface("next", "Attributes"),
                }
            },
            {
                "marker": _metrics_marker("review_group"),
                "surfaces": {
                    "categorical_card": _metrics_surface(
                        "card", "Loading values for this field…", field="review_group", state="pending",
                    ),
                    "categorical_selector": _metrics_surface("selector", "review_group"),
                    "next_control": _metrics_surface("next", "Attributes"),
                }
            },
            {
                "marker": _metrics_marker("review_group"),
                "surfaces": {
                    "categorical_card": _metrics_surface(
                        "card", "Population: 10 review-0", field="review_group", state="ready",
                    ),
                    "categorical_selector": _metrics_surface("selector", "review_group"),
                    "next_control": _metrics_surface("next", "Attributes"),
                }
            },
        ]
    }

    summary = jitter_metrics._target_facet_trace_summary(
        trace,
        previous_field="dataset_from",
        field="review_group",
        terminal_state="ready",
        forbidden_texts=("synthetic",),
        expected_text="Population: 10",
        max_delta_px=1.0,
    )

    assert any("incomplete or mixed field frame" in value for value in summary["violations"])


def test_metrics_facet_summary_accepts_complete_previous_then_complete_target() -> None:
    marker = _metrics_marker("review_group")
    trace = {
        "frames": [
            {
                "marker": marker,
                "surfaces": {
                    "categorical_card": _metrics_surface(
                        "card", "Population: 10 synthetic", field="dataset_from", state="ready",
                    ),
                    "categorical_selector": _metrics_surface("selector", "dataset_from"),
                    "next_control": _metrics_surface("next", "Attributes"),
                },
            },
            {
                "marker": marker,
                "surfaces": {
                    "categorical_card": _metrics_surface(
                        "card", "Population: 10 review-0", field="review_group", state="ready",
                    ),
                    "categorical_selector": _metrics_surface("selector", "review_group"),
                    "next_control": _metrics_surface("next", "Attributes"),
                },
            },
        ],
    }

    summary = jitter_metrics._target_facet_trace_summary(
        trace,
        previous_field="dataset_from",
        field="review_group",
        terminal_state="ready",
        forbidden_texts=("synthetic",),
        expected_text="Population: 10",
        max_delta_px=1.0,
    )

    assert summary["violations"] == []


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
        "visibleImageCount": 1,
        "visibleImages": [{
            "viewerImage": "full",
            "currentPath": path,
            "alt": f"Image viewer: {path.rsplit('/', 1)[-1]}",
            "complete": True,
            "naturalWidth": 48,
            "opacity": 1.0,
            "rgb": [20, 30, 40],
        }],
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
            "imageCount": 1,
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
            "imageCount": 1,
            "opacity": 1.0,
            "loadingState": "ready",
            "neutralLoaderVisible": False,
        },
    }

    failures = open_checks.viewer_acceptance_failures([scenario])

    assert any("thumbObserved is still true" in failure for failure in failures)
    assert any("neutral loader appeared" in failure for failure in failures)
    assert any("visible non-presented image" in failure for failure in failures)


def test_viewer_navigation_acceptance_rejects_zero_visible_images() -> None:
    frame = _viewer_frame(path="/a.jpg", loading_state="pending")
    frame["visibleImages"] = []
    frame["visibleImageCount"] = 0
    scenario = {
        "name": "next",
        "openedPath": "/b.jpg",
        "navigation": {"from": "/a.jpg", "to": "/b.jpg", "direction": "next"},
        "loaderExpected": False,
        "loaderForbidden": False,
        "riskSummary": {
            "thumbObserved": False,
            "fallbackObserved": False,
            "fullImageCrossfadeObserved": False,
            "duplicateVisibleImageObserved": False,
            "openFadeClassObserved": False,
        },
        "samples": {"samples": [frame]},
        "settled": {
            "dialogPath": "/b.jpg",
            "imagePath": "/b.jpg",
            "imageCount": 1,
            "opacity": 1.0,
            "loadingState": "ready",
            "neutralLoaderVisible": False,
        },
    }

    failures = open_checks.viewer_acceptance_failures([scenario])

    assert any("navigation painted zero visible images" in failure for failure in failures)


def test_hover_preview_oracle_rejects_visible_loading_or_undecoded_portal() -> None:
    frames = [
        {"surfaceVisible": True, "path": "/a.jpg", "state": "loading", "image": None},
        {
            "surfaceVisible": True,
            "path": "/a.jpg",
            "state": "ready",
            "image": {"complete": True, "naturalWidth": 0, "visible": True, "rgb": None},
        },
    ]

    violations = grid_hover_preview.hover_preview_case_violations(
        "proxy", frames, expected_path="/a.jpg", expected_rgb=[32, 72, 144],
    )

    assert violations == ["hover proxy: visible portal did not own decoded target pixels"]


def test_hover_preview_oracle_accepts_first_visible_decoded_target() -> None:
    frames = [
        {"surfaceVisible": False, "path": "/a.jpg", "state": "decoding", "image": None},
        {
            "surfaceVisible": True,
            "path": "/a.jpg",
            "state": "ready",
            "image": {
                "complete": True,
                "naturalWidth": 48,
                "visible": True,
                "rgb": [32, 72, 144],
            },
        },
    ]

    assert grid_hover_preview.hover_preview_case_violations(
        "proxy", frames, expected_path="/a.jpg", expected_rgb=[32, 72, 144],
    ) == []


def test_hover_preview_oracle_rejects_mixed_pixels_and_visible_decode() -> None:
    mixed = [{
        "surfaceVisible": True,
        "path": "/scope_a/scope_01.jpg",
        "state": "ready",
        "image": {
            "complete": True,
            "naturalWidth": 48,
            "visible": True,
            "rgb": [160, 64, 48],
        },
    }]
    corrupt = [{
        "surfaceVisible": True,
        "path": "/sample_011.jpg",
        "state": "decoding",
        "image": None,
    }]

    assert grid_hover_preview.hover_preview_case_violations(
        "mixed",
        mixed,
        expected_path="/scope_a/scope_01.jpg",
        expected_rgb=[190, 64, 88],
    ) == ["hover mixed: visible pixels did not match '/scope_a/scope_01.jpg'"]
    assert grid_hover_preview.hover_preview_case_violations(
        "corrupt", corrupt, expected_path="/sample_011.jpg", outcome="error",
    ) == [
        "hover corrupt: invalid resource became visible before terminal error",
        "hover corrupt: corrupt target did not remain a terminal error",
    ]


def test_hover_preview_error_oracle_rejects_stale_visible_pixels() -> None:
    frames = [{
        "surfaceVisible": True,
        "path": "/sample_011.jpg",
        "state": "error",
        "image": {"visible": True, "rgb": [190, 64, 88]},
    }]

    assert grid_hover_preview.hover_preview_case_violations(
        "corrupt", frames, expected_path="/sample_011.jpg", outcome="error",
    ) == [
        "hover corrupt: terminal error retained a media node",
        "hover corrupt: corrupt target did not remain a terminal error",
    ]
    assert grid_hover_preview.fixture_rgb("/quick_03_meta.png") == [38, 96, 154]

    hidden_orphan = [{
        "surfaceVisible": False,
        "path": "/sample_011.jpg",
        "state": "decoding",
        "image": {"visible": False},
    }]
    assert grid_hover_preview.hover_preview_case_violations(
        "cancelled", hidden_orphan, expected_path="/sample_011.jpg", outcome="cancelled",
    ) == ["hover cancelled: orphan preview node remained"]


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
        retained_transform="matrix(2, 0, 0, 2, 10, 20)",
    )

    assert config.viewport_size() == {"width": 1200, "height": 820}
    assert trace.as_payload() == {
        "from": "/a.jpg",
        "via": ["/b.jpg", "/c.jpg"],
        "to": "/d.jpg",
        "direction": "next",
        "retainedTransform": "matrix(2, 0, 0, 2, 10, 20)",
    }


def test_viewer_baseline_mode_enforces_every_collected_scenario() -> None:
    failures = viewer_probe_entrypoint.acceptance_failures_for_mode("baseline", {})

    assert any(failure.startswith("viewer:") for failure in failures)
    assert any(failure.startswith("back:") for failure in failures)
    assert any(failure.startswith("interactions:") for failure in failures)


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


def test_toolbar_cold_first_frame_contract_detects_responsive_and_persisted_mismatch() -> None:
    settings = {
        "viewMode": "grid",
        "gridItemSize": 300,
        "userLeftOpen": "false",
        "userRightOpen": "false",
        "autoloadImageMetadata": "false",
        "compareOrderMode": "selection",
        "proxyHttpOriginals": "true",
        "query": "sample",
        "sortKind": "builtin",
        "sortKey": "name",
        "sortDir": "asc",
    }
    traces = {
        "phone": [{
            **settings,
            "layoutMode": "phone",
            "desktopSearchVisible": False,
            "searchToggleVisible": True,
        }],
        "narrow": [{
            **settings,
            "layoutMode": "narrow",
            "desktopSearchVisible": False,
            "searchToggleVisible": True,
        }],
        "desktop": [{
            **settings,
            "layoutMode": "desktop",
            "desktopSearchVisible": True,
            "searchToggleVisible": False,
        }],
    }

    assert jitter_toolbar.cold_first_frame_violations(traces) == []
    traces["phone"][0]["layoutMode"] = "desktop"
    assert jitter_toolbar.cold_first_frame_violations(traces) == [
        "phone cold load painted layout 'desktop'",
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
            "topRailHeight": 10,
            "gridBodyTop": 20,
        },
        filters_active={
            "topStackHeight": 12,
            "topRailHeight": 12,
            "gridBodyTop": 22,
        },
        filters_cleared={
            "topStackHeight": 11,
            "topRailHeight": 11,
            "gridBodyTop": 21,
        },
        metric_mode={"gridBodyWidth": 800, "firstCellLeft": 20, "firstCellWidth": 120, "metricRailWidth": 44},
        builtin_restored={"gridBodyWidth": 790, "firstCellLeft": 22, "firstCellWidth": 118, "metricRailWidth": 40},
        metric_sort_label="probe_score",
    )

    top_stack = jitter_grid.grid_top_stack_deltas(snapshots)
    widths = jitter_grid.grid_width_deltas(snapshots)

    assert top_stack["baseline_to_filters_top_stack_delta"] == 2
    assert top_stack["baseline_to_restored_top_rail_delta"] == 1
    assert top_stack["baseline_to_filters_grid_body_top_delta"] == 2
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


def test_jitter_grid_terminal_error_requires_an_inactive_metric_rail() -> None:
    frame = {
        "railActive": True,
        "railIdentity": {"key": "score", "state": "pending"},
    }

    assert jitter_grid._terminal_error_rail_violations(frame) == [
        "terminal error retained an active or pending metric rail"
    ]
    assert jitter_grid._terminal_error_rail_violations({
        "railActive": False,
        "railIdentity": None,
    }) == []


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
            "interactionDisabled": True,
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
        "sort: active metric rail remained interactive while pending"
    ]

    assert jitter_grid._transition_identity_violations("sort", frames[:2])[-1] == (
        "sort: terminal steady identity did not match the requested target"
    )


def test_derived_numeric_trace_requires_retained_or_terminal_whole_rows() -> None:
    def surface(
        *,
        data: dict[str, str],
        text: str = "",
        inert: bool = False,
        busy: str | None = None,
        disabled: str | None = None,
    ) -> dict:
        return {
            "text": text,
            "attrs": {
                "data": data,
                "inert": inert,
                "ariaBusy": busy,
                "ariaDisabled": disabled,
            },
        }

    retained = {
        "surfaces": {
            "numeric_term": surface(
                data={
                    "data-facet-requested-field": "q2",
                    "data-facet-presented-field": "q1",
                },
                inert=True,
                busy="true",
                disabled="true",
            ),
            "numeric_selector": surface(data={}, text="q1"),
            "numeric_histogram": surface(data={"data-facet-presented-field": "q1"}),
            "numeric_histogram_content": surface(data={"data-facet-state": "ready"}),
        },
    }
    terminal = {
        "surfaces": {
            "numeric_term": surface(
                data={
                    "data-facet-requested-field": "q2",
                    "data-facet-presented-field": "q2",
                },
            ),
            "numeric_selector": surface(data={}, text="q2"),
            "numeric_histogram": surface(data={"data-facet-presented-field": "q2"}),
            "numeric_histogram_content": surface(data={"data-facet-state": "ready"}),
        },
    }

    trace = {"frames": [retained, terminal]}
    assert jitter_metrics_derived._identity_violations(trace, "q2", "ready") == []

    retained["surfaces"]["numeric_term"]["attrs"]["inert"] = False
    terminal["surfaces"]["numeric_histogram_content"]["attrs"]["data"][
        "data-facet-state"
    ] = "pending"
    assert jitter_metrics_derived._identity_violations(trace, "q2", "ready") == [
        "q2 mixed its pending numeric row with the retained metric",
        "q2 presented before terminal numeric state ready",
    ]
