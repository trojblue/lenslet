"""Table-backed browse app mode."""

from __future__ import annotations

from fastapi import FastAPI

from ...storage.table.input import TableInput
from ...storage.table.storage import TableStorage, TableStorageOptions
from .options import StorageAppOptions, TableAppOptions
from .storage import create_storage_app


def create_table_app(
    table: TableInput,
    *,
    options: TableAppOptions | None = None,
) -> FastAPI:
    """Create a browse app for an in-memory or file-backed table."""
    options = options or TableAppOptions()
    browse_options = options.browse
    storage = TableStorage(
        table=table,
        options=TableStorageOptions(
            root=options.base_dir,
            thumb_size=browse_options.thumb_size,
            thumb_quality=browse_options.thumb_quality,
            source_column=options.source_column,
            path_column=options.path_column,
            skip_dimension_probe=options.skip_dimension_probe,
            allow_local=options.allow_local,
        ),
    )
    return create_storage_app(
        storage,
        options=StorageAppOptions(
            browse=browse_options,
            embedding=options.embedding,
            show_source=options.show_source,
            og_preview=options.og_preview,
            workspace=options.workspace,
            embedding_table_path=options.embedding_table_path,
            launch_session=options.launch_session,
            storage_mode="table",
            storage_origin="table",
            refresh="static",
            trusted_write_origins=options.trusted_write_origins,
        ),
    )
