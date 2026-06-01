"""FastAPI server facade for Lenslet."""

from __future__ import annotations

from .web import og
from .web.app.options import (
    BrowseAppOptions,
    DatasetAppOptions,
    EmbeddingAppOptions,
    LocalAppOptions,
    StorageAppOptions,
    TableAppOptions,
)
from .web.app.factory import (
    create_app,
    create_app_from_datasets,
    create_app_from_storage,
    create_app_from_table,
)
from .web.hotpath import HotpathTelemetry

__all__ = (
    "BrowseAppOptions",
    "DatasetAppOptions",
    "EmbeddingAppOptions",
    "LocalAppOptions",
    "StorageAppOptions",
    "TableAppOptions",
    "create_app",
    "create_app_from_datasets",
    "create_app_from_storage",
    "create_app_from_table",
    "HotpathTelemetry",
    "og",
)
