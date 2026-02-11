from __future__ import annotations

import lenslet.server as server
import lenslet.storage.table as table


SERVER_SYMBOLS = (
    "create_app",
    "create_app_from_datasets",
    "create_app_from_table",
    "create_app_from_storage",
    "HotpathTelemetry",
    "_file_response",
    "_thumb_response_async",
    "og",
)

TABLE_SYMBOLS = (
    "TableStorage",
    "load_parquet_table",
    "load_parquet_schema",
)


def test_server_import_contract_symbols() -> None:
    for symbol in SERVER_SYMBOLS:
        assert hasattr(server, symbol), f"missing lenslet.server import-contract symbol: {symbol}"
    assert hasattr(server.og, "subtree_image_count"), "missing lenslet.server.og.subtree_image_count"


def test_table_import_contract_symbols() -> None:
    for symbol in TABLE_SYMBOLS:
        assert hasattr(table, symbol), f"missing lenslet.storage.table import-contract symbol: {symbol}"
