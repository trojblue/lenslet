"""Public table storage package surface."""

from __future__ import annotations

from importlib import import_module

from .input import (
    TableInput,
    TableRow,
    TableRows,
    is_table_input,
    table_input_length,
    table_to_columns,
    validate_table_input,
)

_STORAGE_EXPORTS = frozenset(
    {
        "TABLE_IMAGE_EXTS",
        "TableBrowseIndex",
        "TableBrowseItem",
        "TableStorage",
        "TableStorageOptions",
        "load_parquet_schema",
        "load_parquet_table",
    }
)

__all__ = [
    "TABLE_IMAGE_EXTS",
    "TableBrowseIndex",
    "TableBrowseItem",
    "TableInput",
    "TableRow",
    "TableRows",
    "TableStorage",
    "TableStorageOptions",
    "is_table_input",
    "load_parquet_schema",
    "load_parquet_table",
    "table_input_length",
    "table_to_columns",
    "validate_table_input",
]


def __getattr__(name: str) -> object:
    if name not in _STORAGE_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    storage = import_module(f"{__name__}.storage")
    value = getattr(storage, name)
    globals()[name] = value
    return value
