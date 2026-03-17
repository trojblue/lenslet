"""FastAPI server facade for Lenslet."""

from __future__ import annotations

from . import og
from .web.browse import HotpathTelemetry
from .web.factory import (
    BrowseAppOptions,
    EmbeddingAppOptions,
    create_app,
    create_app_from_datasets,
    create_app_from_storage,
    create_app_from_table,
)
from .web.media import _file_response, _thumb_response_async

__all__ = (
    "BrowseAppOptions",
    "EmbeddingAppOptions",
    "create_app",
    "create_app_from_datasets",
    "create_app_from_storage",
    "create_app_from_table",
    "HotpathTelemetry",
    "_file_response",
    "_thumb_response_async",
    "og",
)
