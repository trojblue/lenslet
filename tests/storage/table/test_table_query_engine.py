from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import math
import random

import pytest

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
    NotesContainsFilter,
    NotesNotContainsFilter,
    StarsInFilter,
    UrlContainsFilter,
    WidthCompareFilter,
    derived_metric_key,
    evaluate_browse_records,
    evaluate_derived_metric_for_records,
)
from lenslet.metrics import normalize_metric_mapping
from lenslet.storage.search_text import build_search_haystack, sidecar_source_fields
from lenslet.storage.source.paths import normalize_item_path
from lenslet.storage.table import TableStorage, TableStorageOptions
from lenslet.storage.table.query_engine import (
    TableQueryCancelled,
    TableQueryEngine,
)


def _storage(
    rows: list[dict[str, object]],
    *,
    categorical_keys: tuple[str, ...] = (),
    include_source_in_search: bool = True,
) -> TableStorage:
    return TableStorage(
        rows,
        options=TableStorageOptions(
            source_column="source",
            path_column="path",
            categorical_columns=categorical_keys,
            include_source_in_search=include_source_in_search,
            skip_dimension_probe=True,
            allow_local=False,
        ),
    )


def _scope_rows(storage: TableStorage) -> tuple[int, ...]:
    row_store = storage._require_row_store()
    return row_store.rows_in_scope("gallery")


def _generic_records(storage: TableStorage):
    row_store = storage._require_row_store()
    records: list[BrowseQueryRecord[int]] = []
    for row_id in _scope_rows(storage):
        path, name, _mime, width, height, _size, mtime, url, source = (
            row_store.item_fields_for_row(row_id)
        )
        canonical = f"/{normalize_item_path(path)}"
        sidecar = storage.get_sidecar_readonly(path)
        tags = sidecar.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        sidecar_source, sidecar_url = sidecar_source_fields(sidecar)
        row_source = source if storage._include_source_in_search else None
        row_url = url if storage._include_source_in_search else None
        search_source = " ".join(
            value for value in (row_source, sidecar_source) if value
        ) or None
        search_url = " ".join(
            value for value in (row_url, sidecar_url) if value
        ) or None
        metrics = storage._metrics_for_row(row_id)
        metrics.update(normalize_metric_mapping(sidecar.get("metrics")) or {})
        records.append(BrowseQueryRecord(
            payload=row_id,
            stable_identity=canonical,
            path=canonical,
            name=name,
            added_at=(
                datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
                if mtime > 0
                else None
            ),
            width=width,
            height=height,
            source=source,
            url=url,
            metrics=metrics,
            categoricals=storage._query_categoricals_for_row(row_id),
            star=sidecar.get("star"),
            notes=sidecar.get("notes", ""),
            search_text=build_search_haystack(
                logical_path=canonical,
                name=name,
                tags=tags,
                notes=sidecar.get("notes", ""),
                source=search_source,
                url=search_url,
                include_source_fields=(
                    storage._include_source_in_search
                    or bool(sidecar_source or sidecar_url)
                ),
            ),
        ))
    return records


def _assert_query_parity(storage: TableStorage, spec: BrowseQuerySpec) -> None:
    rows = _scope_rows(storage)
    generic = evaluate_browse_records(
        _generic_records(storage),
        replace(spec, offset=0, limit=max(1, len(rows))),
        metric_keys=storage.metric_keys(),
        categorical_keys=storage.categorical_keys(),
    )
    analysis = storage.query_engine.analyze_filter(rows, spec)
    ordered = storage.query_engine.order(
        analysis,
        spec.sort,
        random_seed=spec.random_seed,
    )

    assert ordered.ordered_row_ids == tuple(record.payload for record in generic.window)
    assert analysis.derived_metric_status == generic.derived_metric_status


def _parity_rows(count: int = 80) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(count):
        rows.append({
            "source": f"https://bucket-{index % 3}.example.test/assets/{index}.jpg",
            "path": f"gallery/batch-{index % 4}/image-{index:03}.jpg",
            "name": f"item {index % 11:02}.jpg",
            "width": 0 if index % 17 == 0 else 100 + index,
            "height": 0 if index % 19 == 0 else 80 + index,
            "mtime": 1_700_000_000.0 + index * 86_400,
            "q1": math.nan if index % 13 == 0 else float(index % 10),
            "q2": None if index % 7 == 0 else float((index * 3) % 17),
            "category": None if index % 9 == 0 else f"group-{index % 3}",
        })
    return rows


def _annotate_parity_rows(storage: TableStorage) -> None:
    for index in range(0, len(storage.query_engine.columns.row_ids), 5):
        path = f"/gallery/batch-{index % 4}/image-{index:03}.jpg"
        sidecar = storage.ensure_sidecar(path)
        sidecar["star"] = index % 6
        sidecar["notes"] = "blue target" if index % 10 == 0 else "ordinary note"
        sidecar["tags"] = ["tag-needle"] if index % 15 == 0 else []
        storage.set_sidecar(path, sidecar)


def test_filter_order_and_window_keys_invalidate_only_their_semantic_layer() -> None:
    storage = _storage(_parity_rows(12), categorical_keys=("category",))
    base = BrowseQuerySpec(
        "/gallery",
        True,
        0,
        5,
        BrowseFilterAst((MetricRangeFilter("q1", 1.0, 8.0),)),
        BuiltinSortSpec("name", "asc"),
    )
    engine = storage.query_engine
    base_filter_key = engine.filter_key(base)
    assert engine.filter_key(replace(base, offset=5, limit=2)) == base_filter_key
    assert engine.filter_key(replace(base, sort=BuiltinSortSpec("added", "desc"))) == base_filter_key
    assert engine.filter_key(replace(base, text_query="item")) != base_filter_key

    rows = _scope_rows(storage)
    analysis = engine.analyze_filter(rows, base, expected_key=base_filter_key)
    base_order_key = engine.order_key(analysis, base)
    assert engine.order_key(analysis, replace(base, offset=5, limit=2)) == base_order_key
    assert engine.order_key(
        analysis,
        replace(base, sort=BuiltinSortSpec("added", "desc")),
    ) != base_order_key

    order = engine.order(analysis, base.sort, key=base_order_key)
    first_window = engine.window_key(order, base, metric_keys=("q1",))
    assert engine.window_key(
        order,
        replace(base, offset=5),
        metric_keys=("q1",),
    ) != first_window
    assert engine.window_key(order, base, metric_keys=("q1", "q2")) != first_window

    sidecar = storage.ensure_sidecar("/gallery/batch-0/image-000.jpg")
    sidecar["star"] = 5
    storage.set_sidecar("/gallery/batch-0/image-000.jpg", sidecar)
    assert engine.filter_key(base) == base_filter_key
    star_spec = replace(base, filters=BrowseFilterAst((StarsInFilter((5,)),)))
    star_key = engine.filter_key(star_spec)
    sidecar["star"] = 4
    storage.set_sidecar("/gallery/batch-0/image-000.jpg", sidecar)
    assert engine.filter_key(star_spec) != star_key


def test_column_store_normalizes_once_with_stable_rows_and_bounded_buffers() -> None:
    rows = [
        {
            "source": f"https://example.test/gallery/{index}.jpg",
            "path": f"gallery/{index:04}.jpg",
            "width": 8,
            "height": 6,
        }
        for index in range(2_000)
    ]
    storage = _storage(rows)
    row_store = storage._require_row_store()
    metric_calls: dict[int, int] = {}
    categorical_calls: dict[int, int] = {}
    metric_keys = tuple(f"q{index}" for index in range(300))

    def metrics_for_row(row_id: int) -> dict[str, float]:
        metric_calls[row_id] = metric_calls.get(row_id, 0) + 1
        return {
            key: (
                math.nan
                if row_id == 0 and index == 0
                else math.inf
                if row_id == 0 and index == 1
                else float(row_id + index)
            )
            for index, key in enumerate(metric_keys)
        }

    def categoricals_for_row(row_id: int) -> dict[str, str]:
        categorical_calls[row_id] = categorical_calls.get(row_id, 0) + 1
        return {"split": "even" if row_id % 2 == 0 else "odd"}

    engine = TableQueryEngine.from_row_store(
        row_store,
        source_generation="fixture-v1",
        metric_keys=metric_keys,
        categorical_keys=("split",),
        metrics_for_row=metrics_for_row,
        categoricals_for_row=categoricals_for_row,
        include_source_in_search=True,
    )

    assert engine.columns.row_ids == tuple(range(2_000))
    assert engine.columns.stable_identities[:2] == ("/gallery/0000.jpg", "/gallery/0001.jpg")
    assert set(metric_calls.values()) == {1}
    assert set(categorical_calls.values()) == {1}
    assert engine.columns.metric_value(0, "q0") is None
    assert engine.columns.metric_value(0, "q1") is None
    assert engine.columns.metric_value(1, "q1") == 2.0
    assert engine.columns.buffer_nbytes <= 16 * 1024 * 1024


def test_sidecar_updates_change_only_relevant_dependency_generations() -> None:
    storage = _storage(_parity_rows(10), categorical_keys=("category",))
    engine = storage.query_engine
    rows = _scope_rows(storage)
    path = "/gallery/batch-0/image-000.jpg"
    star_spec = BrowseQuerySpec(
        path="/gallery",
        recursive=True,
        offset=0,
        limit=10,
        filters=BrowseFilterAst((StarsInFilter((5,)),)),
    )
    notes_spec = replace(
        star_spec,
        filters=BrowseFilterAst((NotesContainsFilter("blue"),)),
    )
    metric_spec = replace(
        star_spec,
        filters=BrowseFilterAst((MetricRangeFilter("dynamic", 0.0, 1.0),)),
    )
    name_spec = replace(
        star_spec,
        filters=BrowseFilterAst((NameContainsFilter("item"),)),
    )
    unknown_spec = replace(name_spec, unsupported_metric_intent="future-clause")
    baseline = {
        "star": engine.dependency_stamp(star_spec),
        "notes": engine.dependency_stamp(notes_spec),
        "metric": engine.dependency_stamp(metric_spec),
        "name": engine.dependency_stamp(name_spec),
        "unknown": engine.dependency_stamp(unknown_spec),
    }

    sidecar = storage.ensure_sidecar(path)
    sidecar["version"] = 2
    storage.set_sidecar(path, sidecar)
    assert engine.dependency_stamp(name_spec) == baseline["name"]
    assert engine.dependency_stamp(star_spec) == baseline["star"]

    sidecar["star"] = 5
    storage.set_sidecar(path, sidecar)
    starred = engine.analyze_filter(rows, star_spec)
    assert starred.row_ids == (0,)
    assert engine.dependency_stamp(star_spec) != baseline["star"]
    assert engine.dependency_stamp(notes_spec) == baseline["notes"]
    assert engine.dependency_stamp(metric_spec) == baseline["metric"]
    assert engine.dependency_stamp(unknown_spec) != baseline["unknown"]

    sidecar["notes"] = "blue target"
    storage.set_sidecar(path, sidecar)
    assert engine.dependency_stamp(notes_spec) != baseline["notes"]
    assert engine.dependency_stamp(metric_spec) == baseline["metric"]

    sidecar["metrics"] = {"dynamic": 0.5}
    storage.set_sidecar(path, sidecar)
    assert engine.dependency_stamp(metric_spec) != baseline["metric"]
    assert engine.analyze_filter(rows, metric_spec).row_ids == (0,)

    sidecar["star"] = None
    storage.set_sidecar(path, sidecar)
    assert starred.row_ids == (0,)
    assert engine.analyze_filter(rows, star_spec).row_ids == ()

    storage.replace_sidecars({})
    assert engine.analyze_filter(rows, notes_spec).row_ids == ()
    assert engine.analyze_filter(rows, metric_spec).row_ids == ()


@pytest.mark.parametrize(
    "spec",
    [
        BrowseQuerySpec("/gallery", True, 0, 100, text_query="tag-needle"),
        BrowseQuerySpec(
            "/gallery",
            True,
            0,
            100,
            BrowseFilterAst((StarsInFilter((0, 5)), NameContainsFilter("item 0"))),
            BuiltinSortSpec("name", "asc"),
        ),
        BrowseQuerySpec(
            "/gallery",
            True,
            0,
            100,
            BrowseFilterAst((NotesNotContainsFilter("blue"),)),
            BuiltinSortSpec("name", "desc"),
        ),
        BrowseQuerySpec(
            "/gallery",
            True,
            0,
            100,
            BrowseFilterAst((UrlContainsFilter("bucket-1"),)),
        ),
        BrowseQuerySpec(
            "/gallery",
            True,
            0,
            100,
            BrowseFilterAst((DateRangeFilter("2023-11-20", "2023-12-15"),)),
        ),
        BrowseQuerySpec(
            "/gallery",
            True,
            0,
            100,
            BrowseFilterAst((WidthCompareFilter(">=", 120), HeightCompareFilter("<", 150))),
        ),
        BrowseQuerySpec(
            "/gallery",
            True,
            0,
            100,
            BrowseFilterAst((
                MetricRangeFilter("q1", 2.0, 8.0),
                MetricRangeFilter("q2", 3.0, 14.0),
                CategoricalInFilter("category", ("group-1", "group-2")),
            )),
            MetricSortSpec("q2", "desc"),
        ),
    ],
)
def test_column_filters_match_generic_evaluator(spec: BrowseQuerySpec) -> None:
    storage = _storage(_parity_rows(), categorical_keys=("category",))
    _annotate_parity_rows(storage)
    _assert_query_parity(storage, spec)


def test_column_filtering_does_not_materialize_generic_query_records() -> None:
    storage = _storage(_parity_rows(), categorical_keys=("category",))
    assert not hasattr(storage, "_query_record_for_row")
    result = storage.query_engine.analyze_filter(
        _scope_rows(storage),
        BrowseQuerySpec(
            "/gallery",
            True,
            0,
            80,
            filters=BrowseFilterAst((MetricRangeFilter("q1", 2.0, 8.0),)),
        ),
    )
    assert result.row_ids


def test_randomized_metric_and_categorical_filters_match_generic_evaluator() -> None:
    storage = _storage(_parity_rows(), categorical_keys=("category",))
    rng = random.Random(20260717)
    for _index in range(24):
        low = rng.randint(0, 7)
        high = rng.randint(low, 12)
        categories = tuple(rng.sample(("group-0", "group-1", "group-2"), rng.randint(1, 3)))
        spec = BrowseQuerySpec(
            path="/gallery",
            recursive=True,
            offset=0,
            limit=100,
            filters=BrowseFilterAst((
                MetricRangeFilter("q1", float(low), float(high)),
                CategoricalInFilter("category", categories),
            )),
            sort=MetricSortSpec("q1", rng.choice(("asc", "desc"))),
        )
        _assert_query_parity(storage, spec)


def test_text_search_source_toggle_and_sidecar_source_match_generic_evaluator() -> None:
    storage = _storage(_parity_rows(5), include_source_in_search=False)
    spec = BrowseQuerySpec("/gallery", True, 0, 10, text_query="bucket-0")
    _assert_query_parity(storage, spec)
    assert storage.query_engine.analyze_filter(_scope_rows(storage), spec).row_ids == ()

    path = "/gallery/batch-0/image-000.jpg"
    sidecar = storage.ensure_sidecar(path)
    sidecar["source"] = "sidecar-only-token"
    storage.set_sidecar(path, sidecar)
    sidecar_spec = replace(spec, text_query="sidecar-only-token")
    _assert_query_parity(storage, sidecar_spec)


def test_filter_cancellation_checks_row_and_time_bounds() -> None:
    storage = _storage(_parity_rows(600), categorical_keys=("category",))
    spec = BrowseQuerySpec("/gallery", True, 0, 600)
    calls = 0

    def cancel_at_row_checkpoint() -> bool:
        nonlocal calls
        calls += 1
        return calls >= 2

    with pytest.raises(TableQueryCancelled):
        storage.query_engine.analyze_filter(_scope_rows(storage), spec, cancel_at_row_checkpoint)
    assert calls == 2

    class TickClock:
        value = 0.0

        def __call__(self) -> float:
            self.value += 0.03
            return self.value

    timed_engine = TableQueryEngine(storage.query_engine.columns, clock=TickClock())
    calls = 0

    def cancel_at_time_checkpoint() -> bool:
        nonlocal calls
        calls += 1
        return calls >= 2

    with pytest.raises(TableQueryCancelled):
        timed_engine.analyze_filter(_scope_rows(storage), spec, cancel_at_time_checkpoint)
    assert calls == 2


@pytest.mark.parametrize(
    "derived",
    [
        DerivedMetricSpec(
            "applied",
            "Applied",
            1.0,
            (
                DerivedMetricNumericTerm("q1", 2.0, "zero", True),
                DerivedMetricNumericTerm("q2", 0.5, "invalid"),
            ),
            (DerivedMetricCategoricalTerm("category", "group-1", 4.0),),
        ),
        DerivedMetricSpec(
            "zero_variance",
            "Zero variance",
            0.0,
            (DerivedMetricNumericTerm("constant", 1.0, "invalid", True),),
        ),
        DerivedMetricSpec(
            "unavailable",
            "Unavailable",
            0.0,
            (DerivedMetricNumericTerm("missing_key", 1.0, "invalid"),),
        ),
        DerivedMetricSpec("bad id", "Invalid", 0.0),
    ],
)
def test_derived_analysis_matches_generic_evaluator(derived: DerivedMetricSpec) -> None:
    rows = _parity_rows(40)
    for row in rows:
        row["constant"] = 3.0
    storage = _storage(rows, categorical_keys=("category",))
    records = _generic_records(storage)
    generic = evaluate_derived_metric_for_records(
        records,
        derived,
        metric_keys=storage.metric_keys(),
        categorical_keys=storage.categorical_keys(),
    )
    spec = BrowseQuerySpec(
        path="/gallery",
        recursive=True,
        offset=0,
        limit=100,
        derived_metric=derived,
    )
    analysis = storage.query_engine.analyze_filter(_scope_rows(storage), spec)
    expected_scores: dict[int, float] = {}
    expected_key = generic.status.key
    for record in generic.records:
        if expected_key is not None and record.metrics and expected_key in record.metrics:
            expected_scores[record.payload] = float(record.metrics[expected_key])

    assert dict(analysis.derived_scores) == expected_scores
    assert analysis.derived_metric_status == generic.status


def test_derived_analysis_checks_cancellation_around_population_passes() -> None:
    storage = _storage(_parity_rows(20), categorical_keys=("category",))
    spec = BrowseQuerySpec(
        "/gallery",
        True,
        0,
        20,
        derived_metric=DerivedMetricSpec(
            "cancel",
            "Cancel",
            0.0,
            (DerivedMetricNumericTerm("q1", 1.0, "zero", True),),
        ),
    )
    calls = 0

    def cancel_between_passes() -> bool:
        nonlocal calls
        calls += 1
        return calls >= 3

    with pytest.raises(TableQueryCancelled):
        storage.query_engine.analyze_filter(_scope_rows(storage), spec, cancel_between_passes)
    assert calls == 3


def test_derived_filter_and_sort_match_generic_evaluator() -> None:
    storage = _storage(_parity_rows(40), categorical_keys=("category",))
    derived = DerivedMetricSpec(
        "filtered",
        "Filtered",
        0.0,
        (DerivedMetricNumericTerm("q1", 1.0, "invalid", True),),
        (DerivedMetricCategoricalTerm("category", "group-2", 2.0),),
    )
    key = derived_metric_key(derived)
    _assert_query_parity(
        storage,
        BrowseQuerySpec(
            "/gallery",
            True,
            0,
            40,
            filters=BrowseFilterAst((MetricRangeFilter(key, -0.5, 3.0),)),
            sort=MetricSortSpec(key, "desc"),
            derived_metric=derived,
        ),
    )


def test_ordering_matches_generic_semantics_and_random_pages_are_stable() -> None:
    rows = _parity_rows(30)
    for index, row in enumerate(rows):
        row["name"] = "duplicate.jpg" if index < 8 else row["name"]
    storage = _storage(rows, categorical_keys=("category",))
    derived = DerivedMetricSpec(
        "rank",
        "Rank",
        0.0,
        (DerivedMetricNumericTerm("q1", 1.0, "zero"),),
    )
    for sort in (
        BuiltinSortSpec("added", "asc"),
        BuiltinSortSpec("added", "desc"),
        BuiltinSortSpec("name", "asc"),
        BuiltinSortSpec("name", "desc"),
        MetricSortSpec("q1", "asc"),
        MetricSortSpec("q1", "desc"),
        MetricSortSpec(derived_metric_key(derived), "desc"),
        BuiltinSortSpec("random", "asc"),
    ):
        _assert_query_parity(
            storage,
            BrowseQuerySpec(
                "/gallery",
                True,
                0,
                30,
                sort=sort,
                random_seed="stable-seed",
                derived_metric=derived,
            ),
        )

    spec = BrowseQuerySpec(
        "/gallery",
        True,
        0,
        30,
        sort=BuiltinSortSpec("random", "asc"),
        random_seed="stable-seed",
    )
    analysis = storage.query_engine.analyze_filter(_scope_rows(storage), spec)
    first = storage.query_engine.order(analysis, spec.sort, random_seed=spec.random_seed)
    second = storage.query_engine.order(analysis, spec.sort, random_seed=spec.random_seed)
    assert first.ordered_row_ids == second.ordered_row_ids
    assert set(first.ordered_row_ids[:10]).isdisjoint(first.ordered_row_ids[10:20])


def test_ordering_checks_cancellation_before_and_after_sort() -> None:
    storage = _storage(_parity_rows(30), categorical_keys=("category",))
    spec = BrowseQuerySpec("/gallery", True, 0, 30, sort=MetricSortSpec("q1", "asc"))
    analysis = storage.query_engine.analyze_filter(_scope_rows(storage), spec)

    with pytest.raises(TableQueryCancelled):
        storage.query_engine.order(analysis, spec.sort, cancel=lambda: True)

    calls = 0

    def cancel_after_sort() -> bool:
        nonlocal calls
        calls += 1
        return calls >= 2

    with pytest.raises(TableQueryCancelled):
        storage.query_engine.order(analysis, spec.sort, cancel=cancel_after_sort)
    assert calls == 2
