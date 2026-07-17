from __future__ import annotations

import pytest

from lenslet.browse.query import (
    BrowseFilterAst,
    BrowseFilterClause,
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
    UrlNotContainsFilter,
    WidthCompareFilter,
    query_dependency_manifest,
)


@pytest.mark.parametrize(
    ("clause", "fields", "metric_keys", "categorical_keys"),
    [
        (StarsInFilter((0,)), {"star"}, set(), set()),
        (StarsNotInFilter((5,)), {"star"}, set(), set()),
        (NameContainsFilter("cat"), {"name"}, set(), set()),
        (NameNotContainsFilter("cat"), {"name"}, set(), set()),
        (NotesContainsFilter("review"), {"notes"}, set(), set()),
        (NotesNotContainsFilter("review"), {"notes"}, set(), set()),
        (UrlContainsFilter("bucket"), {"source", "url"}, set(), set()),
        (UrlNotContainsFilter("bucket"), {"source", "url"}, set(), set()),
        (DateRangeFilter("2026-01-01", None), {"added_at"}, set(), set()),
        (WidthCompareFilter(">=", 100), {"width"}, set(), set()),
        (HeightCompareFilter("<", 200), {"height"}, set(), set()),
        (MetricRangeFilter("quality", 0.1, 0.9), set(), {"quality"}, set()),
        (CategoricalInFilter("source", ("gt",)), set(), set(), {"source"}),
    ],
)
def test_query_dependency_manifest_covers_each_filter_clause(
    clause: BrowseFilterClause,
    fields: set[str],
    metric_keys: set[str],
    categorical_keys: set[str],
) -> None:
    spec = BrowseQuerySpec(
        path="/",
        recursive=True,
        offset=0,
        limit=100,
        filters=BrowseFilterAst((clause,)),
        sort=BuiltinSortSpec(key="random"),
    )

    manifest = query_dependency_manifest(spec)

    assert manifest.fields == fields
    assert manifest.metric_keys == metric_keys
    assert manifest.categorical_keys == categorical_keys
    assert manifest.unknown is False


def test_query_dependency_manifest_covers_text_sort_derived_and_facets() -> None:
    spec = BrowseQuerySpec(
        path="/",
        recursive=True,
        offset=0,
        limit=100,
        sort=MetricSortSpec("rank"),
        text_query="cat",
        derived_metric=DerivedMetricSpec(
            id="rubric",
            name="Rubric",
            intercept=0,
            numeric_terms=(DerivedMetricNumericTerm("quality", 1, "invalid"),),
            categorical_terms=(DerivedMetricCategoricalTerm("source", "gt", 2),),
        ),
    )

    manifest = query_dependency_manifest(
        spec,
        facet_metric_keys=("brightness",),
        facet_categorical_keys=("split",),
    )

    assert manifest.fields == {"name", "path", "tags", "notes", "source", "url"}
    assert manifest.metric_keys == {"rank", "quality", "brightness"}
    assert manifest.categorical_keys == {"source", "split"}
    assert manifest.unknown is False


@pytest.mark.parametrize(
    ("sort", "expected"),
    [
        (BuiltinSortSpec(key="added"), {"added_at"}),
        (BuiltinSortSpec(key="name"), {"name"}),
        (BuiltinSortSpec(key="random"), set()),
    ],
)
def test_query_dependency_manifest_covers_builtin_sort(
    sort: BuiltinSortSpec,
    expected: set[str],
) -> None:
    manifest = query_dependency_manifest(
        BrowseQuerySpec(path="/", recursive=True, offset=0, limit=100, sort=sort)
    )

    assert manifest.fields == expected


def test_query_dependency_manifest_marks_unknown_intent_conservatively() -> None:
    manifest = query_dependency_manifest(
        BrowseQuerySpec(
            path="/",
            recursive=True,
            offset=0,
            limit=100,
            unsupported_metric_intent="future-clause",
        )
    )

    assert manifest.unknown is True
