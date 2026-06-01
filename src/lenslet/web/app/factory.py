"""Public FastAPI app factory facade for Lenslet server modes."""

from __future__ import annotations

from fastapi import FastAPI

from ...storage.base import BrowseAppStorage
from ...storage.table.input import TableInput
from .options import DatasetAppOptions, LocalAppOptions, StorageAppOptions, TableAppOptions


def create_app(
    root_path: str,
    *,
    options: LocalAppOptions | None = None,
) -> FastAPI:
    """Create a local-directory Lenslet app."""
    from .local import create_local_app

    return create_local_app(root_path, options=options)


def create_app_from_datasets(
    datasets: dict[str, list[str]],
    *,
    options: DatasetAppOptions | None = None,
) -> FastAPI:
    """Create a Lenslet app from named in-memory datasets."""
    from .dataset import create_dataset_app

    return create_dataset_app(datasets, options=options)


def create_app_from_table(
    table: TableInput,
    *,
    options: TableAppOptions | None = None,
) -> FastAPI:
    """Create a Lenslet app from table rows or a PyArrow table."""
    from .table import create_table_app

    return create_table_app(table, options=options)


def create_app_from_storage(
    storage: BrowseAppStorage,
    *,
    options: StorageAppOptions | None = None,
) -> FastAPI:
    """Create a Lenslet app around an existing browse storage backend."""
    from .storage import create_storage_app

    return create_storage_app(storage, options=options)
