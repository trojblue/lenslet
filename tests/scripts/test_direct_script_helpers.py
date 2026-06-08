from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
EXPERIMENTAL_SCRIPTS_DIR = SCRIPTS_DIR / "experimental"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(EXPERIMENTAL_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(EXPERIMENTAL_SCRIPTS_DIR))

import embed_parquet_embeddings  # noqa: E402
import examples.programmatic_api_example as programmatic_api_example  # noqa: E402
import fast_table_source_index as fast_index  # noqa: E402
import lint_repo  # noqa: E402
import setup_dev  # noqa: E402
import scripts.smoke_harness as smoke_harness  # noqa: E402
from scripts.browser import waits as browser_waits  # noqa: E402
from scripts.browser.gui_smoke import acceptance as gui_smoke_acceptance  # noqa: E402
from scripts.browser.gui_smoke import fixtures as gui_smoke_fixtures  # noqa: E402
from scripts.browser.gui_smoke import inspector as gui_smoke_inspector  # noqa: E402
from scripts.browser.gui_smoke import scenarios as gui_smoke_scenarios  # noqa: E402
from scripts.browser.overall_cleanup import fixtures as overall_cleanup_fixtures  # noqa: E402
from scripts.browser.responsive_geometry import catalog as responsive_geometry_catalog  # noqa: E402
from scripts.browser.responsive_geometry import fixtures as responsive_geometry_fixtures  # noqa: E402
from scripts.browser.viewer_probe import config as viewer_probe_config  # noqa: E402
from scripts.browser.viewer_probe import fixtures as viewer_probe_fixtures  # noqa: E402
from scripts.browser.viewer_probe import flicker_back as viewer_flicker_back_browser  # noqa: E402
from scripts.browser.viewer_probe import interaction_checks as viewer_probe_interaction_checks  # noqa: E402
from scripts.browser.viewer_probe import interactions as viewer_probe_interactions  # noqa: E402
from scripts.browser.viewer_probe import page as viewer_probe_page  # noqa: E402

BROWSER_SCRIPT_FILES = (
    "scripts/browser/waits.py",
    "scripts/browser/gui_smoke/acceptance.py",
    "scripts/browser/gui_smoke/fixtures.py",
    "scripts/browser/gui_smoke/inspector.py",
    "scripts/browser/gui_smoke/scenarios.py",
    "scripts/browser/gui_jitter/probe.py",
    "scripts/browser/gui_jitter/fixtures.py",
    "scripts/browser/gui_jitter/grid.py",
    "scripts/browser/gui_jitter/grid_dom.py",
    "scripts/browser/gui_jitter/inspector.py",
    "scripts/browser/gui_jitter/shared.py",
    "scripts/browser/gui_jitter/toolbar.py",
    "scripts/browser/viewer_probe/flicker_back.py",
    "scripts/browser/viewer_probe/back.py",
    "scripts/browser/viewer_probe/config.py",
    "scripts/browser/viewer_probe/fixtures.py",
    "scripts/browser/viewer_probe/interaction_checks.py",
    "scripts/browser/viewer_probe/interactions.py",
    "scripts/browser/viewer_probe/open.py",
    "scripts/browser/viewer_probe/open_checks.py",
    "scripts/browser/viewer_probe/page.py",
    "scripts/browser/responsive_geometry/catalog.py",
    "scripts/browser/responsive_geometry/errors.py",
    "scripts/browser/responsive_geometry/evidence.py",
    "scripts/browser/responsive_geometry/fixtures.py",
    "scripts/browser/responsive_geometry/harness.py",
    "scripts/browser/responsive_geometry/types.py",
    "scripts/browser/overall_cleanup/browser.py",
    "scripts/browser/overall_cleanup/fixtures.py",
    "scripts/browser/overall_cleanup/focus.py",
    "scripts/browser/overall_cleanup/grid.py",
    "scripts/browser/overall_cleanup/hover.py",
    "scripts/browser/overall_cleanup/media_requests.py",
    "scripts/browser/overall_cleanup/menus.py",
    "scripts/browser/overall_cleanup/mobile.py",
    "scripts/browser/overall_cleanup/panels.py",
    "scripts/browser/overall_cleanup/screenshots.py",
    "scripts/browser/overall_cleanup/surfaces.py",
    "scripts/browser/overall_cleanup/transforms.py",
    "scripts/browser/overall_cleanup/support.py",
    "scripts/browser/large_tree/smoke.py",
    "scripts/browser/large_tree/baselines.json",
)

LEGACY_BROWSER_SCRIPT_FILES = (
    "scripts/browser_waits.py",
    "scripts/gui_smoke_acceptance.py",
    "scripts/gui_smoke_fixtures.py",
    "scripts/gui_smoke_inspector.py",
    "scripts/gui_smoke_scenarios.py",
    "scripts/gui_jitter_probe.py",
    "scripts/gui_jitter_fixtures.py",
    "scripts/gui_jitter_grid.py",
    "scripts/gui_jitter_grid_dom.py",
    "scripts/gui_jitter_inspector.py",
    "scripts/gui_jitter_shared.py",
    "scripts/gui_jitter_toolbar.py",
    "scripts/viewer_flicker_back_browser.py",
    "scripts/viewer_probe_back.py",
    "scripts/viewer_probe_config.py",
    "scripts/viewer_probe_fixtures.py",
    "scripts/viewer_probe_interaction_checks.py",
    "scripts/viewer_probe_interactions.py",
    "scripts/viewer_probe_open.py",
    "scripts/viewer_probe_open_checks.py",
    "scripts/viewer_probe_page.py",
    "scripts/responsive_geometry_catalog.py",
    "scripts/responsive_geometry_errors.py",
    "scripts/responsive_geometry_evidence.py",
    "scripts/responsive_geometry_fixtures.py",
    "scripts/responsive_geometry_harness.py",
    "scripts/responsive_geometry_types.py",
    "scripts/overall_cleanup_browser.py",
    "scripts/overall_cleanup_fixtures.py",
    "scripts/overall_cleanup_interactions.py",
    "scripts/overall_cleanup_support.py",
    "scripts/playwright_large_tree_smoke.py",
    "scripts/playwright_large_tree_smoke_baselines.json",
)


class _WaitPage:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def wait_for_function(self, script: str, *, arg=None, timeout=None) -> None:
        self.calls.append({"script": script, "arg": arg, "timeout": timeout})


def test_browser_wait_helpers_pass_bounded_waits_to_page() -> None:
    page = _WaitPage()

    browser_waits.wait_for_animation_frames(page, 123, frames=3)
    browser_waits.wait_for_dom_settled(page, 456, stable_ms=90)
    browser_waits.wait_for_grid_selection_count(page, 2, 789)

    assert [call["arg"] for call in page.calls] == [3, 90, 2]
    assert [call["timeout"] for call in page.calls] == [123, 456, 789]
    assert "aria-selected" in page.calls[-1]["script"]


def test_browser_script_family_layout_contract() -> None:
    missing = [path for path in BROWSER_SCRIPT_FILES if not (REPO_ROOT / path).exists()]
    lingering = [path for path in LEGACY_BROWSER_SCRIPT_FILES if (REPO_ROOT / path).exists()]

    assert missing == []
    assert lingering == []


def test_fast_table_source_index_reports_json_with_atomic_replace(tmp_path: Path) -> None:
    output_path = tmp_path / "nested" / "summary.json"
    result = fast_index.IndexBuildResult(
        row_count=2,
        item_count=2,
        folder_count=1,
        row_mapped_count=2,
        unresolved_remote_dimensions=0,
        elapsed_seconds=0.5,
        signature="abc123",
    )

    fast_index._write_json_atomic(output_path, {"fast": fast_index._result_payload(result)})

    assert fast_index._optional_column(" path ") == "path"
    assert fast_index._optional_column(" ") is None
    assert fast_index._encode_scalar(None) == b"<none>"
    assert '"img_per_second": 4.0' in output_path.read_text(encoding="utf-8")


def test_fast_table_source_index_uses_dimension_probe_vocabulary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["fast_table_source_index.py", "/tmp/images", "--skip-dimension-probe"],
    )

    args = fast_index._parse_args()

    assert args.skip_dimension_probe is True
    assert not hasattr(args, "skip_" + "indexing")


def test_responsive_geometry_fixture_module_builds_dataset(tmp_path: Path) -> None:
    responsive_geometry_fixtures.build_fixture_dataset(tmp_path)

    assert (tmp_path / "alpha" / "alpha_01.png").is_file()
    assert (tmp_path / "beta" / "beta_03.png").is_file()
    assert (tmp_path / "items.parquet").is_file()
    assert "leftW.metrics" in responsive_geometry_fixtures.seed_storage_script(
        responsive_geometry_fixtures.scenario_storage()
    )


def test_responsive_geometry_catalog_keeps_named_layout_scenarios() -> None:
    scenarios = responsive_geometry_catalog.layout_scenario_catalog()
    names = {scenario.name for scenario in scenarios}

    assert "desktop-open-oversized" in names
    assert "phone-search-open-320" in names
    assert "inspector-allowed-900" in names
    assert all(scenario.storage["rightW"] == "900" for scenario in scenarios)


def test_overall_cleanup_fixture_module_builds_dataset_and_atomic_writes(tmp_path: Path) -> None:
    overall_cleanup_fixtures.build_fixture_dataset(tmp_path)

    root_images = sorted(tmp_path.glob("cleanup_fixture_*.png"))
    nested_image = tmp_path / "cleanup_nested" / "cleanup_fixture_nested.png"

    assert [path.name for path in root_images] == [f"cleanup_fixture_{idx:02d}.png" for idx in range(8)]
    assert nested_image.is_file()
    with Image.open(root_images[0]) as image:
        assert image.size == (1000, 100)
        assert image.getpixel((0, 0)) == (215, 80, 75)
    with Image.open(nested_image) as image:
        assert image.size == (640, 360)

    bytes_path = tmp_path / "atomic" / "payload.bin"
    text_path = tmp_path / "atomic" / "payload.txt"
    overall_cleanup_fixtures.write_bytes_atomic(bytes_path, b"new-bytes")
    overall_cleanup_fixtures.write_text_atomic(text_path, "new-text")

    assert bytes_path.read_bytes() == b"new-bytes"
    assert text_path.read_text(encoding="utf-8") == "new-text"


def test_overall_cleanup_atomic_write_preserves_target_on_fsync_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "payload.bin"
    target.write_bytes(b"old")

    def _raise_fsync(_fd: int) -> None:
        raise OSError("disk refused sync")

    monkeypatch.setattr(overall_cleanup_fixtures.os, "fsync", _raise_fsync)

    with pytest.raises(OSError, match="disk refused sync"):
        overall_cleanup_fixtures.write_bytes_atomic(target, b"new")

    assert target.read_bytes() == b"old"
    assert list(tmp_path.glob(".payload.bin.*.tmp")) == []


def test_embed_parquet_embeddings_parser_builds_expected_options(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "embed_parquet_embeddings.py",
            "items.parquet",
            "--image-column",
            "image",
            "--embedding-column",
            "embedding",
            "--normalize",
            "--limit",
            "10",
        ],
    )

    args = embed_parquet_embeddings._parse_args()

    assert args.parquet == "items.parquet"
    assert args.image_column == "image"
    assert args.embedding_column == "embedding"
    assert args.error_policy == "raise"
    assert args.normalize is True
    assert args.limit == 10


def test_embed_parquet_embeddings_parser_keeps_zero_fill_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "embed_parquet_embeddings.py",
            "items.parquet",
            "--image-column",
            "image",
            "--error-policy",
            "zero",
        ],
    )

    args = embed_parquet_embeddings._parse_args()

    assert args.error_policy == "zero"


def test_smoke_harness_command_and_json_helpers(tmp_path: Path) -> None:
    command = smoke_harness.lenslet_command(
        tmp_path / "images",
        host="127.0.0.1",
        port=7777,
        extra_args=["--reload"],
    )

    assert command[:3] == [sys.executable, "-m", "lenslet.cli"]
    assert command[-5:] == ["--host", "127.0.0.1", "--port", "7777", "--reload"]

    evidence_path = tmp_path / "nested" / "evidence.json"
    smoke_harness.write_json_evidence(evidence_path, {"ok": True})
    assert '"ok": true' in evidence_path.read_text(encoding="utf-8")
    assert smoke_harness.read_log_tail(evidence_path, line_count=1).strip() == "}"
    assert smoke_harness.server_base_url("127.0.0.1", 7777) == "http://127.0.0.1:7777"
    assert smoke_harness.server_base_url("::1", 7777) == "http://[::1]:7777"


def test_lint_repo_filters_candidates_and_counts_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "src").mkdir()
    tracked = tmp_path / "src" / "app.py"
    tracked.write_text("one\ntwo\n", encoding="utf-8")
    hidden = tmp_path / "src" / ".hidden.py"
    hidden.write_text("ignored\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    assert lint_repo.should_scan_file(Path("src/app.py")) is True
    assert lint_repo.should_scan_file(Path("src/.hidden.py")) is False
    assert list(lint_repo.iter_candidate_files(["src"])) == [Path("src/app.py")]
    assert lint_repo.count_lines(Path("src/app.py")) == 2


def test_setup_dev_command_helpers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    constraint = tmp_path / "constraints.txt"
    constraint.write_text("# pinned\n", encoding="utf-8")
    monkeypatch.setattr(setup_dev, "ROOT", tmp_path)

    assert setup_dev.shell_join(["python", "-m", "pip"]) == "python -m pip"
    assert setup_dev.editable_target("dev, s3") == ".[dev,s3]"
    assert setup_dev.python_constraint_args("none") == []
    assert setup_dev.python_constraint_args(str(constraint)) == ["-c", str(constraint)]
    with pytest.raises(SystemExit, match="constraint file does not exist"):
        setup_dev.python_constraint_args(str(tmp_path / "missing.txt"))


def test_programmatic_api_example_calls_launch_with_expected_shapes(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[dict, object]] = []

    def _fake_launch(datasets, options):
        calls.append((datasets, options))

    monkeypatch.setattr(programmatic_api_example.lenslet, "launch", _fake_launch)

    programmatic_api_example.example_mixed()

    datasets, options = calls[-1]
    assert "mixed_dataset" in datasets
    assert any(path.startswith("s3://") for path in datasets["mixed_dataset"])
    assert options.blocking is False
    assert options.port == 7070


def test_viewer_flicker_dispatches_acceptance_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(viewer_flicker_back_browser, "viewer_acceptance_failures", lambda raw: ["viewer"])
    monkeypatch.setattr(viewer_flicker_back_browser, "back_acceptance_failures", lambda raw: ["back"])
    monkeypatch.setattr(
        viewer_flicker_back_browser,
        "interactions_acceptance_failures",
        lambda raw: ["interactions"],
    )

    scenarios = {"viewerOpen": [], "backHitTarget": [], "interactions": {}}

    assert viewer_flicker_back_browser.acceptance_failures_for_mode("viewer", scenarios) == ["viewer"]
    assert viewer_flicker_back_browser.acceptance_failures_for_mode("all", scenarios) == [
        "viewer",
        "back",
        "interactions",
    ]


def test_gui_smoke_inspector_section_order_assertion() -> None:
    gui_smoke_inspector.assert_section_precedes(["basics", "metadata"], "basics", "metadata", "probe")
    with pytest.raises(gui_smoke_inspector.SmokeFailure, match="Expected section"):
        gui_smoke_inspector.assert_section_precedes(["metadata", "basics"], "basics", "metadata", "probe")


def test_viewer_probe_modules_keep_page_and_interaction_bounds(tmp_path: Path) -> None:
    viewer_probe_fixtures.build_fixture_dataset(tmp_path)

    assert (tmp_path / "alpha" / "alpha_00_wide.jpg").is_file()
    assert viewer_probe_page.path_from_cell_id("cell-%2Fanimals%2Fcat.jpg") == "/animals/cat.jpg"
    with pytest.raises(viewer_probe_config.ViewerProbeFailure):
        viewer_probe_page.path_from_cell_id("row-%2Fanimals%2Fcat.jpg")

    state = {
        "matrix": {"a": 1.0, "d": 1.0, "e": 10.0, "f": -5.0},
        "transformBounds": {
            "x": {"strictMin": -10, "strictMax": 11, "slackMin": -12, "slackMax": 12},
            "y": {"strictMin": -6, "strictMax": 6, "slackMin": -8, "slackMax": 8},
        },
        "imageRect": {"left": 10, "right": 100, "top": 20, "bottom": 110},
        "dialogRect": {"left": 0, "right": 120, "top": 0, "bottom": 120},
    }

    assert viewer_probe_interaction_checks.transform_changed(
        {"matrix": {"a": 1.0, "d": 1.0, "e": 0.0, "f": 0.0}},
        state,
    )
    assert viewer_probe_interactions.active_drag_axis(5, 2) == "x"
    assert viewer_probe_interactions.active_drag_value(state, "y") == -5.0
    assert viewer_probe_interactions.reached_strict_edge(state, 10, 0) is True
    assert viewer_probe_interaction_checks.transform_outside_bounds(state, "slack") is False
    assert viewer_probe_interaction_checks.image_still_recoverable(state) is True
    assert viewer_probe_interaction_checks.interactions_acceptance_failures(
        {
            "defaultFitPan": [],
            "zoomEdgePan": [],
            "zoomControls": [],
            "clicks": {},
        }
    )


def test_gui_smoke_acceptance_summary_and_section_order(tmp_path: Path) -> None:
    assert gui_smoke_acceptance.parse_iso8601_timestamp("2026-05-30T00:00:00Z") is not None
    assert gui_smoke_acceptance.has_indexing_lifecycle_proof(
        {
            "indexing": {
                "state": "ready",
                "started_at": "2026-05-30T00:00:00Z",
                "finished_at": "2026-05-30T00:00:01Z",
            }
        }
    )
    gui_smoke_scenarios.assert_section_precedes(["metadata", "quickView"], "metadata", "quickView", "test")
    with pytest.raises(smoke_harness.SmokeFailure):
        gui_smoke_scenarios.assert_section_precedes(["quickView", "metadata"], "metadata", "quickView", "test")

    result = gui_smoke_scenarios.SmokeResult(
        indexing_banner_seen=False,
        sidebar_resize_delta_px=0.0,
        left_collapsed_width_px=56.0,
        left_hotkey_reopen_width_px=240.0,
        right_resized_width_px=320.0,
        center_width_after_right_resize_px=800.0,
        anchor_before="/a.jpg",
        anchor_restored="/b.jpg",
        anchor_settled="/b.jpg",
        anchor_reentry_exact=False,
        search_visible_matches=["/b.jpg"],
        inspector_default_order=["metadata", "quickView"],
        inspector_reordered_order=["quickView", "metadata"],
        inspector_reloaded_order=["quickView", "metadata"],
        inspector_compare_over_cap_message="too many",
    )
    summary = gui_smoke_acceptance.build_summary(
        base_url="http://127.0.0.1:7070",
        dataset_dir=tmp_path,
        server_log=tmp_path / "server.log",
        initial_health={},
        final_health={},
        result=result,
    )

    assert summary["checks"]["inspector_reorder_persisted"] is True
    assert summary["warnings"]


def test_gui_smoke_fixture_image_helpers(tmp_path: Path) -> None:
    payload = gui_smoke_fixtures._build_jpeg_payload()
    target = tmp_path / "nested" / "sample.jpg"

    gui_smoke_fixtures._write_image(target, payload)

    assert target.read_bytes().startswith(b"\xff\xd8")


def test_gui_smoke_derived_metric_table_fixture(tmp_path: Path) -> None:
    pytest.importorskip("pyarrow")
    parquet_path = gui_smoke_fixtures.build_derived_metric_table_fixture(tmp_path, row_count=12)

    assert parquet_path == tmp_path / "items.parquet"
    assert parquet_path.is_file()
    assert (tmp_path / "shared.jpg").is_file()
