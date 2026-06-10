from __future__ import annotations

import math
from dataclasses import replace

from lenslet.browse.query import (
    BrowseFilterAst,
    BrowseQueryRecord,
    BrowseQuerySpec,
    BuiltinSortSpec,
    CategoricalInFilter,
    DateRangeFilter,
    DerivedMetricCategoricalTerm,
    DerivedMetricNumericTerm,
    DerivedMetricSpec,
    HeightCompareFilter,
    MetricRangeFilter,
    MetricSortSpec,
    NameContainsFilter,
    NameNotContainsFilter,
    NotesContainsFilter,
    NotesNotContainsFilter,
    StarsInFilter,
    StarsNotInFilter,
    UrlContainsFilter,
    WidthCompareFilter,
    browse_analysis_query_key,
    browse_query_request_token,
    browse_window_request_token,
    derived_metric_key,
    evaluate_browse_records,
)


def _record(
    name: str,
    *,
    path: str | None = None,
    added_at: str | None = None,
    width: int | float | None = 8,
    height: int | float | None = 6,
    source: str | None = None,
    url: str | None = None,
    metrics: dict[str, object] | None = None,
    categoricals: dict[str, str] | None = None,
    star: int | None = None,
    notes: str | None = "",
    search_text: str | None = None,
) -> BrowseQueryRecord[str]:
    record_path = path or f"/gallery/{name}"
    return BrowseQueryRecord(
        payload=record_path,
        stable_identity=record_path,
        path=record_path,
        name=name,
        added_at=added_at,
        width=width,
        height=height,
        source=source,
        url=url,
        metrics=metrics or {},
        categoricals=categoricals or {},
        star=star,
        notes=notes,
        search_text=search_text if search_text is not None else f"{name} {record_path}",
    )


def _matches(clause, record: BrowseQueryRecord[str]) -> bool:
    spec = BrowseQuerySpec(
        path="/gallery",
        recursive=True,
        offset=0,
        limit=10,
        filters=BrowseFilterAst(and_clauses=(clause,)),
        sort=BuiltinSortSpec(key="name", direction="asc"),
    )
    return bool(evaluate_browse_records((record,), spec).window)


def test_backend_filter_evaluator_matches_frontend_edge_cases() -> None:
    assert not _matches(CategoricalInFilter("kind", ("cat",)), _record("a.jpg"))
    assert not _matches(MetricRangeFilter("score", 0.1, 0.9), _record("a.jpg"))
    assert not _matches(
        MetricRangeFilter("score", 0.1, 0.9), _record("a.jpg", metrics={"score": math.inf})
    )

    missing_star = _record("a.jpg", star=None)
    assert _matches(StarsInFilter((0,)), missing_star)
    assert not _matches(StarsNotInFilter((0,)), missing_star)

    assert _matches(StarsInFilter(()), missing_star)
    assert _matches(CategoricalInFilter("kind", ()), _record("a.jpg"))

    missing_notes = _record("a.jpg", notes=None)
    assert not _matches(NotesContainsFilter("cat"), missing_notes)
    assert not _matches(NotesNotContainsFilter("cat"), missing_notes)

    assert _matches(
        DateRangeFilter(to_value="2026-06-09"),
        _record("a.jpg", added_at="2026-06-09T23:59:59+00:00"),
    )
    assert not _matches(
        DateRangeFilter(to_value="2026-06-09"),
        _record("a.jpg", added_at="2026-06-10T00:00:00+00:00"),
    )

    assert not _matches(
        UrlContainsFilter("target"),
        _record("a.jpg", source="", url="https://example.test/target.jpg"),
    )
    assert _matches(
        UrlContainsFilter("target"),
        _record("a.jpg", source=None, url="https://example.test/target.jpg"),
    )
    assert not _matches(
        UrlContainsFilter("url-token"),
        _record("a.jpg", source="source-token", url="url-token"),
    )

    assert not _matches(WidthCompareFilter(">", 1), _record("a.jpg", width=0))
    assert not _matches(HeightCompareFilter(">", 1), _record("a.jpg", height=None))
    assert _matches(WidthCompareFilter(">=", 8), _record("a.jpg", width=8))


def test_backend_text_filter_variants() -> None:
    record = _record("Cathedral.jpg", notes="night scout")

    assert _matches(NameContainsFilter("cat"), record)
    assert not _matches(NameNotContainsFilter("cat"), record)
    assert _matches(NotesContainsFilter("scout"), record)
    assert _matches(NotesNotContainsFilter("missing"), record)


def test_metric_sort_keeps_invalid_values_after_valid_values_in_both_directions() -> None:
    records = (
        _record("b.jpg", metrics={"score": 0.2}),
        _record("invalid-a.jpg", metrics={"score": math.inf}),
        _record("a.jpg", metrics={"score": 0.8}),
        _record("missing.jpg"),
    )

    asc = evaluate_browse_records(
        records,
        BrowseQuerySpec(
            path="/gallery",
            recursive=True,
            offset=0,
            limit=10,
            sort=MetricSortSpec("score", "asc"),
        ),
    )
    desc = evaluate_browse_records(
        records,
        BrowseQuerySpec(
            path="/gallery",
            recursive=True,
            offset=0,
            limit=10,
            sort=MetricSortSpec("score", "desc"),
        ),
    )

    assert [record.name for record in asc.window] == [
        "b.jpg",
        "a.jpg",
        "invalid-a.jpg",
        "missing.jpg",
    ]
    assert [record.name for record in desc.window] == [
        "a.jpg",
        "b.jpg",
        "invalid-a.jpg",
        "missing.jpg",
    ]


def test_sort_ties_have_stable_path_tiebreakers() -> None:
    records = (
        _record("same.jpg", path="/gallery/b.jpg", metrics={"score": 1.0}),
        _record("same.jpg", path="/gallery/a.jpg", metrics={"score": 1.0}),
        _record("same.jpg", path="/gallery/c.jpg", metrics={"score": 1.0}),
    )

    result = evaluate_browse_records(
        records,
        BrowseQuerySpec(
            path="/gallery",
            recursive=True,
            offset=0,
            limit=10,
            sort=MetricSortSpec("score", "desc"),
        ),
    )

    assert [record.path for record in result.window] == [
        "/gallery/a.jpg",
        "/gallery/b.jpg",
        "/gallery/c.jpg",
    ]


def test_seeded_random_sort_is_stable_across_offset_windows() -> None:
    records = tuple(_record(f"img{i}.jpg") for i in range(6))
    base = BrowseQuerySpec(
        path="/gallery",
        recursive=True,
        offset=0,
        limit=6,
        sort=BuiltinSortSpec("random", "asc"),
        random_seed="seed-1",
    )
    full = evaluate_browse_records(records, base)
    first = evaluate_browse_records(records, replace(base, offset=0, limit=2))
    second = evaluate_browse_records(records, replace(base, offset=2, limit=2))

    assert [record.path for record in first.window + second.window] == [
        record.path for record in full.window[:4]
    ]
    assert not {record.path for record in first.window} & {record.path for record in second.window}
    assert [record.path for record in full.window] == [
        record.path for record in evaluate_browse_records(records, base).window
    ]


def test_analysis_query_key_excludes_window_fields() -> None:
    base = BrowseQuerySpec(
        path="/gallery",
        recursive=True,
        offset=0,
        limit=10,
        filters=BrowseFilterAst(and_clauses=(CategoricalInFilter("source_column", ("target",)),)),
        sort=BuiltinSortSpec("name", "asc"),
        text_query="cat",
        random_seed="inactive-seed",
    )

    assert browse_analysis_query_key(base) == browse_analysis_query_key(
        replace(base, offset=20, limit=50, random_seed="ignored-seed")
    )
    assert browse_analysis_query_key(base) != browse_analysis_query_key(
        replace(base, text_query="dog")
    )
    assert browse_analysis_query_key(base) != browse_analysis_query_key(
        replace(base, unsupported_metric_intent="derived-filter")
    )
    assert browse_analysis_query_key(
        replace(base, unsupported_metric_intent=" derived-filter ")
    ) == browse_analysis_query_key(
        replace(base, unsupported_metric_intent="derived-filter")
    )
    assert browse_analysis_query_key(
        replace(base, sort=BuiltinSortSpec("random", "asc"), random_seed="seed-a")
    ) != browse_analysis_query_key(
        replace(base, sort=BuiltinSortSpec("random", "asc"), random_seed="seed-b")
    )


def test_window_request_token_includes_window_fields_and_generation() -> None:
    base = BrowseQuerySpec(
        path="/gallery",
        recursive=True,
        offset=0,
        limit=10,
        sort=BuiltinSortSpec("name", "asc"),
    )

    assert browse_window_request_token(base) == browse_query_request_token(base)
    assert browse_window_request_token(base) != browse_window_request_token(
        replace(base, offset=10)
    )
    assert browse_window_request_token(base) != browse_window_request_token(replace(base, limit=20))
    assert browse_window_request_token(
        base, generation_token="gen-a"
    ) != browse_window_request_token(
        base,
        generation_token="gen-b",
    )


def test_filtered_window_is_sliced_after_full_scope_filtering() -> None:
    records = tuple(
        _record(
            f"img{i}.jpg",
            categoricals={"source_column": "target" if i in {4, 5} else "other"},
        )
        for i in range(6)
    )
    result = evaluate_browse_records(
        records,
        BrowseQuerySpec(
            path="/gallery",
            recursive=True,
            offset=0,
            limit=2,
            filters=BrowseFilterAst(
                and_clauses=(CategoricalInFilter("source_column", ("target",)),)
            ),
            sort=BuiltinSortSpec("name", "asc"),
        ),
    )

    assert result.filtered_total == 2
    assert [record.name for record in result.window] == ["img4.jpg", "img5.jpg"]


def test_derived_metric_sort_and_filter_run_before_windowing() -> None:
    spec = DerivedMetricSpec(
        id="rubric_1",
        name="Rubric score",
        intercept=1.0,
        numeric_terms=(
            DerivedMetricNumericTerm("q1", 2.0, "invalid"),
            DerivedMetricNumericTerm("q2", 1.0, "zero"),
        ),
        categorical_terms=(DerivedMetricCategoricalTerm("dataset_from", "gt", 3.0),),
    )
    key = derived_metric_key(spec)
    records = (
        _record("low.jpg", metrics={"q1": 0.1}, categoricals={"dataset_from": "synthetic"}),
        _record("high.jpg", metrics={"q1": 0.9, "q2": 1.2}, categoricals={"dataset_from": "gt"}),
        _record("mid.jpg", metrics={"q1": 0.5}, categoricals={"dataset_from": "gt"}),
        _record("invalid.jpg", metrics={"q2": 1.0}, categoricals={"dataset_from": "gt"}),
    )

    result = evaluate_browse_records(
        records,
        BrowseQuerySpec(
            path="/gallery",
            recursive=True,
            offset=0,
            limit=2,
            filters=BrowseFilterAst(and_clauses=(MetricRangeFilter(key, 4.0, 10.0),)),
            sort=MetricSortSpec(key, "desc"),
            derived_metric=spec,
        ),
        metric_keys=("q1", "q2"),
        categorical_keys=("dataset_from",),
    )

    assert result.filtered_total == 2
    assert [record.name for record in result.window] == ["high.jpg", "mid.jpg"]
    assert result.window[0].metrics and result.window[0].metrics[key] == 7.0


def test_derived_metric_z_normalize_uses_scope_population() -> None:
    spec = DerivedMetricSpec(
        id="rubric_1",
        name="Rubric score",
        intercept=0.0,
        numeric_terms=(DerivedMetricNumericTerm("q1", 1.0, "invalid", z_normalize=True),),
    )
    key = derived_metric_key(spec)
    records = (
        _record("low.jpg", metrics={"q1": 0.0}),
        _record("mid.jpg", metrics={"q1": 10.0}),
        _record("high.jpg", metrics={"q1": 20.0}),
    )

    result = evaluate_browse_records(
        records,
        BrowseQuerySpec(
            path="/gallery",
            recursive=True,
            offset=0,
            limit=2,
            filters=BrowseFilterAst(and_clauses=(MetricRangeFilter(key, 1.0, 2.0),)),
            sort=MetricSortSpec(key, "desc"),
            derived_metric=spec,
        ),
        metric_keys=("q1",),
    )

    assert result.filtered_total == 1
    assert [record.name for record in result.window] == ["high.jpg"]
    assert result.window[0].metrics
    assert math.isclose(result.window[0].metrics[key], math.sqrt(3 / 2))


def test_derived_metric_is_not_applied_when_inputs_are_unavailable() -> None:
    spec = DerivedMetricSpec(
        id="rubric_1",
        name="Rubric score",
        intercept=0.0,
        numeric_terms=(DerivedMetricNumericTerm("missing_q", 1.0, "zero"),),
    )
    key = derived_metric_key(spec)
    result = evaluate_browse_records(
        (_record("a.jpg", metrics={"q1": 0.9}),),
        BrowseQuerySpec(
            path="/gallery",
            recursive=True,
            offset=0,
            limit=10,
            sort=MetricSortSpec(key, "desc"),
            derived_metric=spec,
        ),
        metric_keys=("q1",),
    )

    assert result.window[0].metrics == {"q1": 0.9}
