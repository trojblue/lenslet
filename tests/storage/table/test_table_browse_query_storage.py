from __future__ import annotations

from lenslet.browse.query import (
    BrowseFilterAst,
    BrowseQuerySpec,
    BrowseWindowProjection,
    BuiltinSortSpec,
    CategoricalInFilter,
    DerivedMetricCategoricalTerm,
    DerivedMetricNumericTerm,
    DerivedMetricSpec,
    MetricRangeFilter,
    MetricSortSpec,
    NotesContainsFilter,
    StarsInFilter,
    WidthCompareFilter,
    derived_metric_key,
)
from lenslet.storage.table import TableStorage, TableStorageOptions


def _table_storage(rows: list[dict[str, object]]) -> TableStorage:
    return TableStorage(
        rows,
        options=TableStorageOptions(
            source_column="source",
            path_column="path",
            skip_dimension_probe=True,
            allow_local=False,
        ),
    )


def _rows() -> list[dict[str, object]]:
    return [
        {
            "source": f"https://example.test/gallery/img{index}.jpg",
            "path": f"gallery/img{index}.jpg",
            "width": 8,
            "height": 6,
            "source_column": "target" if index in {4, 5} else "other",
            "score": float(index),
        }
        for index in range(6)
    ]


def test_table_query_filters_full_scope_and_materializes_only_window() -> None:
    storage = _table_storage(_rows())
    row_store = storage._row_store
    assert row_store is not None
    assert row_store.materialized_item_count == 0

    result = storage.query_browse_scope(
        BrowseQuerySpec(
            path="/gallery",
            recursive=True,
            offset=0,
            limit=1,
            filters=BrowseFilterAst(
                and_clauses=(CategoricalInFilter("source_column", ("target",)),)
            ),
            sort=BuiltinSortSpec("name", "asc"),
        )
    )

    assert result.scope_total == 6
    assert result.filtered_total == 2
    assert [item.path for item in result.items] == ["gallery/img4.jpg"]
    assert row_store.materialized_item_count == 1
    assert result.metric_keys == ()
    assert result.categorical_keys == ()


def test_table_query_and_facets_use_columns_and_bound_window_materialization(
    monkeypatch,
) -> None:
    metric_count = 300
    rows = [
        {
            "source": f"https://example.test/gallery/img{index:04}.jpg",
            "path": f"gallery/img{index:04}.jpg",
            "width": 8,
            "height": 6,
            "metrics": {
                f"q{metric_index}": float(index + metric_index)
                for metric_index in range(metric_count)
            },
        }
        for index in range(500)
    ]
    storage = _table_storage(rows)
    row_store = storage._require_row_store()
    row_store.materialized_item_count = 0

    def fail_row_metric_expansion(_row_idx: int) -> dict[str, float]:
        raise AssertionError("production query paths must read prebuilt columns")

    def fail_facet_sort(*_args, **_kwargs):
        raise AssertionError("facet aggregation must not order filtered rows")

    monkeypatch.setattr(storage, "_metrics_for_row", fail_row_metric_expansion)
    spec = BrowseQuerySpec(
        path="/gallery",
        recursive=True,
        offset=100,
        limit=200,
        sort=BuiltinSortSpec("name", "asc"),
        projection=BrowseWindowProjection(metric_keys=("q0", "q1", "q2")),
    )

    result = storage.query_browse_scope(spec)

    assert len(result.items) == 200
    assert row_store.materialized_item_count == 200
    assert all(set(item.metrics) == {"q0", "q1", "q2"} for item in result.items)

    row_store.materialized_item_count = 0
    monkeypatch.setattr(storage.query_engine, "order", fail_facet_sort)
    facets = storage.facet_summary_for_query(spec)

    assert facets["total_items"] == 500
    assert facets["metrics"]["q0"]["histogram"]["count"] == 500
    assert row_store.materialized_item_count == 0


def test_dynamic_sidecar_metrics_are_projected_and_faceted() -> None:
    storage = _table_storage(_rows())
    path = "/gallery/img4.jpg"
    sidecar = storage.ensure_sidecar(path)
    sidecar["metrics"] = {"review_score": 42.0}
    storage.set_sidecar(path, sidecar)
    assert storage.metric_keys() == ["review_score", "score"]
    spec = BrowseQuerySpec(
        path="/gallery",
        recursive=True,
        offset=0,
        limit=10,
        filters=BrowseFilterAst((MetricRangeFilter("review_score", 40.0, 50.0),)),
        sort=MetricSortSpec("review_score", "desc"),
        projection=BrowseWindowProjection(metric_keys=("review_score",)),
    )

    result = storage.query_browse_scope(spec)
    facets = storage.facet_summary_for_query(spec)

    assert [item.path for item in result.items] == ["gallery/img4.jpg"]
    assert result.items[0].metrics["review_score"] == 42.0
    assert result.items[0].mutable_metric_keys == ("review_score",)
    assert "review_score" in result.metric_keys
    assert facets["metric_keys"] == ["review_score", "score"]
    assert facets["metrics"]["review_score"]["histogram"]["count"] == 1


def test_lazy_dimensions_update_column_filters_and_projected_items() -> None:
    storage = _table_storage([{
        "source": "https://example.test/gallery/img0.jpg",
        "path": "gallery/img0.jpg",
        "width": 0,
        "height": 0,
    }])
    spec = BrowseQuerySpec(
        path="/gallery",
        recursive=True,
        offset=0,
        limit=10,
        filters=BrowseFilterAst((WidthCompareFilter(">=", 8),)),
    )
    baseline_stamp = storage.query_engine.dependency_stamp(spec)

    assert storage.query_browse_scope(spec).items == ()

    storage._update_dimensions("/gallery/img0.jpg", (8, 6))
    result = storage.query_browse_scope(spec)

    assert storage.query_engine.dependency_stamp(spec) != baseline_stamp
    assert [(item.path, item.width, item.height) for item in result.items] == [
        ("gallery/img0.jpg", 8, 6),
    ]


def test_table_query_sidecar_filters_do_not_materialize_unsliced_candidates() -> None:
    storage = _table_storage(_rows())
    row_store = storage._row_store
    assert row_store is not None

    star_sidecar = storage.ensure_sidecar("/gallery/img4.jpg")
    star_sidecar["star"] = 5
    star_sidecar["notes"] = "blue target"
    storage.set_sidecar("/gallery/img4.jpg", star_sidecar)
    notes_sidecar = storage.ensure_sidecar("/gallery/img5.jpg")
    notes_sidecar["notes"] = "blue target"
    storage.set_sidecar("/gallery/img5.jpg", notes_sidecar)
    row_store.materialized_item_count = 0

    star_result = storage.query_browse_scope(
        BrowseQuerySpec(
            path="/gallery",
            recursive=True,
            offset=0,
            limit=10,
            filters=BrowseFilterAst(and_clauses=(StarsInFilter((5,)),)),
            sort=BuiltinSortSpec("name", "asc"),
        )
    )

    assert star_result.filtered_total == 1
    assert [item.path for item in star_result.items] == ["gallery/img4.jpg"]
    assert row_store.materialized_item_count == 1
    row_store.materialized_item_count = 0

    notes_result = storage.query_browse_scope(
        BrowseQuerySpec(
            path="/gallery",
            recursive=True,
            offset=0,
            limit=1,
            filters=BrowseFilterAst(and_clauses=(NotesContainsFilter("blue"),)),
            sort=BuiltinSortSpec("name", "asc"),
        )
    )

    assert notes_result.filtered_total == 2
    assert [item.path for item in notes_result.items] == ["gallery/img4.jpg"]
    assert row_store.materialized_item_count == 1


def test_table_query_text_search_respects_source_toggle() -> None:
    rows = [
        {
            "source": "https://cdn.example.test/source-token/local.jpg",
            "path": "gallery/local.jpg",
            "width": 8,
            "height": 6,
        },
    ]
    enabled = TableStorage(
        rows,
        options=TableStorageOptions(
            source_column="source",
            path_column="path",
            skip_dimension_probe=True,
            allow_local=False,
            include_source_in_search=True,
        ),
    )
    disabled = TableStorage(
        rows,
        options=TableStorageOptions(
            source_column="source",
            path_column="path",
            skip_dimension_probe=True,
            allow_local=False,
            include_source_in_search=False,
        ),
    )
    spec = BrowseQuerySpec(
        path="/gallery",
        recursive=True,
        offset=0,
        limit=10,
        text_query="source-token",
        sort=BuiltinSortSpec("name", "asc"),
    )

    assert [item.path for item in enabled.query_browse_scope(spec).items] == ["gallery/local.jpg"]
    assert disabled.query_browse_scope(spec).items == ()


def test_table_query_sorts_by_derived_metric_across_full_scope() -> None:
    rows = [
        {
            "source": f"https://example.test/gallery/img{index}.jpg",
            "path": f"gallery/img{index}.jpg",
            "width": 8,
            "height": 6,
            "q1": float(index),
            "dataset_from": "gt" if index == 4 else "other",
        }
        for index in range(6)
    ]
    storage = _table_storage(rows)
    row_store = storage._row_store
    assert row_store is not None
    spec = DerivedMetricSpec(
        id="rubric_1",
        name="Rubric score",
        intercept=0.0,
        numeric_terms=(DerivedMetricNumericTerm("q1", 1.0, "invalid"),),
        categorical_terms=(DerivedMetricCategoricalTerm("dataset_from", "gt", 10.0),),
    )
    key = derived_metric_key(spec)

    result = storage.query_browse_scope(
        BrowseQuerySpec(
            path="/gallery",
            recursive=True,
            offset=0,
            limit=1,
            filters=BrowseFilterAst(and_clauses=(MetricRangeFilter(key, 10.0, 20.0),)),
            sort=MetricSortSpec(key, "desc"),
            derived_metric=spec,
            projection=BrowseWindowProjection(metric_keys=(key,)),
        )
    )

    assert result.filtered_total == 1
    assert [item.path for item in result.items] == ["gallery/img4.jpg"]
    assert result.items[0].metrics[key] == 14.0
    assert row_store.materialized_item_count == 1
