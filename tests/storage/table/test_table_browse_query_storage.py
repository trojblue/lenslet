from __future__ import annotations

from lenslet.browse.query import (
    BrowseFilterAst,
    BrowseQuerySpec,
    BuiltinSortSpec,
    CategoricalInFilter,
    NotesContainsFilter,
    StarsInFilter,
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
    assert result.metric_keys == ("score",)
    assert "source_column" in result.categorical_keys


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
