from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request

from ...storage.table.storage import TableSourceColumnState, TableStorage
from ..context import get_request_context
from ..models import (
    TableSourceColumnOptionPayload,
    TableSourceColumnSwitchRequest,
    TableSourceColumnsPayload,
)


def _payload_from_state(state: TableSourceColumnState) -> TableSourceColumnsPayload:
    return TableSourceColumnsPayload(
        enabled=state.enabled,
        current=state.current,
        warning=state.warning,
        columns=[
            TableSourceColumnOptionPayload(
                name=column.name,
                selected=column.selected,
                sample_total=column.sample_total,
                sample_loadable=column.sample_loadable,
                sample_usable=column.sample_usable,
                warning=column.warning,
            )
            for column in state.columns
        ],
    )


def _table_storage_from_request(request: Request) -> TableStorage | None:
    storage = get_request_context(request).storage
    return storage if isinstance(storage, TableStorage) else None


def register_table_settings_routes(app: FastAPI) -> None:
    @app.get("/table/source-columns", response_model=TableSourceColumnsPayload)
    def get_table_source_columns(request: Request) -> TableSourceColumnsPayload:
        storage = _table_storage_from_request(request)
        if storage is None:
            return TableSourceColumnsPayload(enabled=False)
        return _payload_from_state(storage.table_source_column_state())

    @app.post("/table/source-column", response_model=TableSourceColumnsPayload)
    def switch_table_source_column(
        payload: TableSourceColumnSwitchRequest,
        request: Request,
    ) -> TableSourceColumnsPayload:
        context = get_request_context(request)
        storage = context.storage
        if not isinstance(storage, TableStorage):
            raise HTTPException(404, "table source switching is only available in table mode")
        try:
            state = storage.switch_source_column(payload.source_column)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if context.recursive_browse_cache is not None:
            context.recursive_browse_cache.invalidate_path("/")
        return _payload_from_state(state)
