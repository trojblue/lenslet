from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lenslet.storage.table.index import TableIndexData, TableIndexInput, TableIndexPolicy, TableSourceResolver
from lenslet.storage.table.row_scan import CategoricalMetricColumn, IndexColumns, scan_rows


@dataclass
class _Item:
    path: str
    name: str
    mime: str
    width: int
    height: int
    size: int
    mtime: float
    url: str | None
    source: str
    metrics: dict[str, float]
    metric_labels: dict[str, str]


def _item_factory(**kwargs: Any) -> _Item:
    return _Item(**kwargs)


def _context() -> TableIndexInput:
    return TableIndexInput(
        table=TableIndexData(
            root=None,
            row_count=1,
            column_values={},
            columns=["source", "path", "quality"],
            source_column="source",
            path_column="path",
            name_column=None,
            mime_column=None,
            width_column=None,
            height_column=None,
            size_column=None,
            mtime_column=None,
            metrics_column=None,
            reserved_columns={"source", "path"},
            local_prefix=None,
            s3_prefixes={},
            s3_use_bucket=False,
            image_exts=(".jpg", ".png"),
        ),
        policy=TableIndexPolicy(
            allow_local=True,
            skip_dimension_probe=True,
            skip_local_realpath_validation=True,
        ),
        source_resolver=TableSourceResolver(
            guess_mime=lambda _name: "image/jpeg",
            allows_extensionless_source_image=lambda _source: False,
            resolve_local_source=lambda source: source,
            resolve_local_source_lexical=lambda source: source,
        ),
        progress=lambda _done, _total, _label: None,
    )


def test_scan_rows_builds_scanned_rows_and_metrics() -> None:
    columns = IndexColumns(
        source_values=["/data/cat.jpg"],
        path_values=["animals/cat.jpg"],
        name_values=[None],
        mime_values=[None],
        width_values=[12],
        height_values=[9],
        size_values=[100],
        mtime_values=[7.5],
        metrics_values=[None],
        metric_columns=(("quality", [0.75]),),
        categorical_metric_columns=(),
    )

    result = scan_rows(_context(), columns, item_factory=_item_factory)

    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.logical_path == "animals/cat.jpg"
    assert row.folder_norm == "animals"
    assert row.item.name == "cat.jpg"
    assert row.item.metrics == {"quality": 0.75}
    assert result.remote_tasks == []


def test_scan_rows_normalizes_table_supplied_mime_values() -> None:
    columns = IndexColumns(
        source_values=["/data/cat.png"],
        path_values=["animals/cat.png"],
        name_values=[None],
        mime_values=["application/octet-stream"],
        width_values=[12],
        height_values=[9],
        size_values=[100],
        mtime_values=[7.5],
        metrics_values=[None],
        metric_columns=(),
        categorical_metric_columns=(),
    )

    result = scan_rows(_context(), columns, item_factory=_item_factory)

    assert result.rows[0].item.mime == "image/png"


def test_scan_rows_collects_categorical_metric_labels() -> None:
    columns = IndexColumns(
        source_values=["/data/cat.jpg"],
        path_values=["animals/cat.jpg"],
        name_values=[None],
        mime_values=[None],
        width_values=[12],
        height_values=[9],
        size_values=[100],
        mtime_values=[7.5],
        metrics_values=[None],
        metric_columns=(),
        categorical_metric_columns=(
            CategoricalMetricColumn(
                key="style_family",
                values=["anime"],
                code_by_label={"anime": 0.0},
            ),
        ),
    )

    result = scan_rows(_context(), columns, item_factory=_item_factory)

    item = result.rows[0].item
    assert item.metrics == {"style_family": 0.0}
    assert item.metric_labels == {"style_family": "anime"}
