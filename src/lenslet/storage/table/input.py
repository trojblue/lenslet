from __future__ import annotations

from collections.abc import Mapping, Sequence, Sized
from typing import Any, Protocol, TypeAlias, TypeGuard


class PyDictTableInput(Protocol):
    """Table-like input that can expose columns as Python lists."""

    def to_pydict(self) -> dict[str, list[Any]]:
        ...


class PandasColumnInput(Protocol):
    """Subset of a pandas Series used by Lenslet table ingestion."""

    def tolist(self) -> list[Any]:
        ...


class PandasTableInput(Protocol):
    """Subset of pandas.DataFrame used by Lenslet table ingestion."""

    @property
    def columns(self) -> Sequence[Any]:
        ...

    def __getitem__(self, column: str) -> PandasColumnInput:
        ...

    def to_dict(self) -> Mapping[str, Any]:
        ...


TableRow: TypeAlias = Mapping[str, Any]
TableRows: TypeAlias = list[TableRow]
TableInput: TypeAlias = PyDictTableInput | PandasTableInput | TableRows

TABLE_INPUT_DESCRIPTION = "to_pydict table-like, pandas.DataFrame-like, or list of dict rows"


def _has_callable_attr(obj: object, name: str) -> bool:
    return callable(getattr(obj, name, None))


def _is_pydict_table_input(obj: object) -> TypeGuard[PyDictTableInput]:
    return _has_callable_attr(obj, "to_pydict")


def _is_pandas_table_input(obj: object) -> TypeGuard[PandasTableInput]:
    return (
        hasattr(obj, "columns")
        and _has_callable_attr(obj, "to_dict")
        and _has_callable_attr(obj, "__getitem__")
    )


def _column_to_list(column: object) -> list[Any]:
    tolist = getattr(column, "tolist", None)
    if not callable(tolist):
        raise TypeError(f"table must be {TABLE_INPUT_DESCRIPTION}")
    return tolist()


def is_table_input(obj: object) -> TypeGuard[TableInput]:
    """Return whether obj satisfies Lenslet's public table input contract."""
    if isinstance(obj, list):
        return all(isinstance(row, Mapping) for row in obj)
    if _is_pydict_table_input(obj):
        return True
    return _is_pandas_table_input(obj)


def validate_table_input(obj: object) -> TableInput:
    if is_table_input(obj):
        return obj
    raise TypeError(f"table must be {TABLE_INPUT_DESCRIPTION}")


def table_input_length(obj: TableInput) -> int:
    if isinstance(obj, list):
        return len(obj)
    num_rows = getattr(obj, "num_rows", None)
    if num_rows is not None:
        return int(num_rows)
    if isinstance(obj, Sized):
        return len(obj)
    return 0


def table_input_columns(table: TableInput) -> list[str]:
    if _is_pydict_table_input(table):
        schema_names = getattr(getattr(table, "schema", None), "names", None)
        if schema_names is not None:
            return [str(column) for column in schema_names]
        return [str(column) for column in table.to_pydict().keys()]
    if _is_pandas_table_input(table):
        return [str(column) for column in list(table.columns)]
    if isinstance(table, list):
        if not table:
            return []
        columns = list(table[0].keys())
        for row in table[1:]:
            for key in row.keys():
                if key not in columns:
                    columns.append(key)
        return [str(column) for column in columns]
    raise TypeError(f"table must be {TABLE_INPUT_DESCRIPTION}")


def _pydict_table_to_columns(
    table: PyDictTableInput,
    *,
    python_columns: set[str] | None,
) -> tuple[list[str], dict[str, Any], int]:
    schema_names = getattr(getattr(table, "schema", None), "names", None)
    if python_columns is None or schema_names is None or not hasattr(table, "__getitem__"):
        data = table.to_pydict()
        columns = [str(column) for column in (schema_names if schema_names is not None else data.keys())]
        row_count = len(data.get(columns[0], [])) if columns else 0
        return columns, data, row_count

    columns = [str(column) for column in schema_names]
    data: dict[str, Any] = {}
    for column in columns:
        values = table[column]  # type: ignore[index]
        data[column] = _startup_column_values(values) if column in python_columns else values
    return columns, data, table_input_length(table)


def _startup_column_values(values: Any) -> Any:
    if _null_free_numeric_arrow_column(values):
        to_numpy = getattr(values, "to_numpy", None)
        if callable(to_numpy):
            try:
                return to_numpy(zero_copy_only=False)
            except Exception:
                pass
    return values.to_pylist()


def _null_free_numeric_arrow_column(values: Any) -> bool:
    if int(getattr(values, "null_count", 0) or 0) != 0:
        return False
    type_name = str(getattr(values, "type", "")).lower()
    return type_name.startswith(("int", "uint", "float", "double"))


def table_to_columns(
    table: TableInput,
    *,
    python_columns: set[str] | None = None,
) -> tuple[list[str], dict[str, Any], int]:
    if _is_pydict_table_input(table):
        return _pydict_table_to_columns(table, python_columns=python_columns)
    elif _is_pandas_table_input(table):
        raw_columns = list(table.columns)
        columns = [str(column) for column in raw_columns]
        data = {str(column): _column_to_list(table[column]) for column in raw_columns}
    elif isinstance(table, list):
        if not table:
            return [], {}, 0
        columns = list(table[0].keys())
        for row in table[1:]:
            for key in row.keys():
                if key not in columns:
                    columns.append(key)
        data = {column: [] for column in columns}
        for row in table:
            for column in columns:
                data[column].append(row.get(column))
    else:
        raise TypeError(f"table must be {TABLE_INPUT_DESCRIPTION}")

    row_count = len(data.get(columns[0], [])) if columns else 0
    return columns, data, row_count
