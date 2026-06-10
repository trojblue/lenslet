from __future__ import annotations

from dataclasses import dataclass

import pytest

from lenslet.cli.browse_args import _build_browse_parser
from lenslet.media_policy import build_original_media_policy
from lenslet.web.models import BROWSE_QUERY_DEFAULT_LIMIT, BROWSE_QUERY_MAX_LIMIT


@dataclass(frozen=True, slots=True)
class Phase1BaselineFixture:
    rows: tuple[dict[str, object], ...]
    local_source: str
    http_source: str
    direct_failure_path: str
    large_metric_row_count: int


def phase1_baseline_fixture() -> Phase1BaselineFixture:
    return Phase1BaselineFixture(
        rows=(
            {
                "source_a": "gallery/local-a.jpg",
                "source_b": "https://cdn.example.test/media/a.jpg?sig=secret",
                "path": "gallery/a.jpg",
                "width": None,
                "height": None,
                "score": 0.8,
            },
            {
                "source_a": "gallery/local-b.jpg",
                "source_b": "https://cdn.example.test/media/b.jpg?sig=secret",
                "path": "gallery/b.jpg",
                "width": 8,
                "height": 6,
                "score": 0.2,
            },
        ),
        local_source="/data/private/gallery/local-a.jpg",
        http_source="https://cdn.example.test/media/a.jpg?sig=secret",
        direct_failure_path="/gallery/a.jpg",
        large_metric_row_count=50_000,
    )


def test_phase1_baseline_fixture_covers_source_media_and_metric_cases() -> None:
    fixture = phase1_baseline_fixture()

    assert any(row["width"] is None and row["height"] is None for row in fixture.rows)
    assert {"source_a", "source_b", "path"} <= set(fixture.rows[0])
    assert fixture.local_source.startswith("/")
    assert fixture.http_source.startswith("https://")
    assert fixture.direct_failure_path == "/gallery/a.jpg"
    assert fixture.large_metric_row_count > BROWSE_QUERY_DEFAULT_LIMIT


def test_source_parquet_dimension_cache_default_is_workspace_backed() -> None:
    args = _build_browse_parser().parse_args(["items.parquet"])

    assert args.cache_dimensions is False
    assert args.dimension_cache == "workspace"


@pytest.mark.xfail(
    strict=True, reason="S1-T3 adds direct-browser failure recovery through backend proxy"
)
def test_direct_browser_failure_can_fall_back_to_backend_proxy() -> None:
    fixture = phase1_baseline_fixture()
    policy = build_original_media_policy(
        fixture.http_source,
        proxy_available=True,
        direct_browser_allowed=True,
        direct_browser_preferred=True,
    )

    current_media_state_after_direct_error = "error"

    assert policy.mode == "browser_direct_preferred_with_proxy_fallback"
    assert current_media_state_after_direct_error == "proxy"


@pytest.mark.xfail(
    strict=True, reason="S3B-T3 replaces 50k metric-sort hydration with bounded pages"
)
def test_large_metric_sort_first_payload_stays_near_normal_page_size() -> None:
    assert BROWSE_QUERY_MAX_LIMIT <= BROWSE_QUERY_DEFAULT_LIMIT
