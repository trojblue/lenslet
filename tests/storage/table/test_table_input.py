from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from lenslet.storage.table.input import (
    TABLE_INPUT_DESCRIPTION,
    is_table_input,
    table_input_length,
    table_to_columns,
    validate_table_input,
)


def test_list_rows_use_union_columns_and_missing_values() -> None:
    rows = [
        {"path": "a.jpg", "score": 0.5},
        {"path": "b.jpg", "label": "keep"},
    ]

    assert is_table_input(rows) is True
    assert table_input_length(rows) == 2
    assert table_to_columns(rows) == (
        ["path", "score", "label"],
        {
            "path": ["a.jpg", "b.jpg"],
            "score": [0.5, None],
            "label": [None, "keep"],
        },
        2,
    )


def test_empty_list_rows_are_valid_empty_table_input() -> None:
    rows: list[dict[str, Any]] = []

    assert validate_table_input(rows) is rows
    assert table_input_length(rows) == 0
    assert table_to_columns(rows) == ([], {}, 0)


def test_pyarrow_like_table_uses_schema_names_and_num_rows() -> None:
    @dataclass(frozen=True)
    class _Schema:
        names: list[str]

    class _Table:
        schema = _Schema(["path", "score"])
        num_rows = 2

        def to_pydict(self) -> dict[str, list[Any]]:
            return {"path": ["a.jpg", "b.jpg"], "score": [0.5, 0.7]}

    table = _Table()

    assert validate_table_input(table) is table
    assert table_input_length(table) == 2
    assert table_to_columns(table) == (
        ["path", "score"],
        {"path": ["a.jpg", "b.jpg"], "score": [0.5, 0.7]},
        2,
    )


def test_to_pydict_only_table_is_valid_input() -> None:
    class _Table:
        def to_pydict(self) -> dict[str, list[Any]]:
            return {"path": ["a.jpg", "b.jpg"], "score": [0.5, 0.7]}

    table = _Table()

    assert is_table_input(table) is True
    assert validate_table_input(table) is table
    assert table_to_columns(table) == (
        ["path", "score"],
        {"path": ["a.jpg", "b.jpg"], "score": [0.5, 0.7]},
        2,
    )


def test_pandas_like_table_reads_columns_by_label() -> None:
    class _Series:
        def __init__(self, values: list[Any]) -> None:
            self._values = values

        def tolist(self) -> list[Any]:
            return list(self._values)

    class _Frame:
        columns = ["path", "score"]

        def __init__(self) -> None:
            self._columns = {"path": _Series(["a.jpg", "b.jpg"]), "score": _Series([0.5, 0.7])}

        def __getitem__(self, column: str) -> _Series:
            return self._columns[column]

        def __len__(self) -> int:
            return 2

        def to_dict(self) -> dict[str, list[Any]]:
            return {column: series.tolist() for column, series in self._columns.items()}

    frame = _Frame()

    assert is_table_input(frame) is True
    assert table_input_length(frame) == 2
    assert table_to_columns(frame) == (
        ["path", "score"],
        {"path": ["a.jpg", "b.jpg"], "score": [0.5, 0.7]},
        2,
    )


def test_to_pydict_member_must_be_callable() -> None:
    class _Table:
        to_pydict = {"path": ["a.jpg"]}

    table = _Table()

    assert is_table_input(table) is False
    with pytest.raises(TypeError, match=TABLE_INPUT_DESCRIPTION):
        validate_table_input(table)
    with pytest.raises(TypeError, match=TABLE_INPUT_DESCRIPTION):
        table_to_columns(table)  # type: ignore[arg-type]


def test_pandas_like_table_methods_must_be_callable() -> None:
    class _NonCallableToDict:
        columns = ["path"]
        to_dict = {"path": ["a.jpg"]}

        def __getitem__(self, column: str) -> object:
            return object()

    class _NonCallableGetItem:
        columns = ["path"]
        __getitem__ = object()

        def to_dict(self) -> dict[str, list[Any]]:
            return {"path": ["a.jpg"]}

    for table in (_NonCallableToDict(), _NonCallableGetItem()):
        assert is_table_input(table) is False
        with pytest.raises(TypeError, match=TABLE_INPUT_DESCRIPTION):
            validate_table_input(table)


def test_pandas_like_column_tolist_must_be_callable() -> None:
    class _Column:
        tolist = ["a.jpg"]

    class _Frame:
        columns = ["path"]

        def __getitem__(self, column: str) -> _Column:
            return _Column()

        def to_dict(self) -> dict[str, list[Any]]:
            return {"path": ["a.jpg"]}

    frame = _Frame()

    assert is_table_input(frame) is True
    assert validate_table_input(frame) is frame
    with pytest.raises(TypeError, match=TABLE_INPUT_DESCRIPTION):
        table_to_columns(frame)


def test_invalid_table_input_raises_contract_error() -> None:
    assert is_table_input(object()) is False
    with pytest.raises(TypeError, match=TABLE_INPUT_DESCRIPTION):
        validate_table_input(object())
    with pytest.raises(TypeError, match=TABLE_INPUT_DESCRIPTION):
        table_to_columns(object())  # type: ignore[arg-type]
