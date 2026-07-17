"""Composed browse API route registration for Lenslet."""

from __future__ import annotations

from fastapi import FastAPI

from ..browse import ToItemFn
from ..record_update import RecordUpdateFn
from .events import register_event_routes
from .export import register_export_routes
from .folders import register_folder_routes
from .items import register_item_routes
from .media import register_media_routes
from .search import register_search_routes
from .table_settings import register_table_settings_routes


def register_common_api_routes(
    app: FastAPI,
    to_item: ToItemFn,
    *,
    record_update: RecordUpdateFn,
) -> None:
    register_folder_routes(app, to_item)
    register_item_routes(app, record_update=record_update, to_item=to_item)
    register_export_routes(app)
    register_event_routes(app)
    register_media_routes(app)
    register_search_routes(app, to_item)
    register_table_settings_routes(app)
