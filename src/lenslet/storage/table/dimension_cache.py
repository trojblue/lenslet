from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ...atomic_write import atomic_write_json
from .index_types import TableCachedRowDimensions


_CACHE_VERSION = 1


@dataclass(frozen=True, slots=True)
class TableDimensionCacheRow:
    row_idx: int
    dimensions: TableCachedRowDimensions


def table_dimension_cache_identity(
    *,
    parquet_path: Path,
    schema: Any,
    row_count: int,
    source_column: str | None,
    path_column: str | None,
    root: str | None,
    base_dir: str | None,
    workspace_cache_dir: Path,
) -> dict[str, Any]:
    stat = parquet_path.stat()
    schema_text = str(schema)
    workspace_id = str(workspace_cache_dir.resolve())
    return {
        "version": _CACHE_VERSION,
        "parquet_path": str(parquet_path.resolve()),
        "parquet_size": stat.st_size,
        "parquet_mtime_ns": stat.st_mtime_ns,
        "schema_hash": hashlib.sha256(schema_text.encode("utf-8")).hexdigest(),
        "row_count": int(row_count),
        "source_column": source_column,
        "path_column": path_column,
        "root": root,
        "base_dir": base_dir,
        "workspace_id": workspace_id,
    }


def dimension_cache_path(cache_dir: Path, identity: dict[str, Any]) -> Path:
    digest = hashlib.sha256(
        repr(sorted(identity.items())).encode("utf-8")
    ).hexdigest()
    return cache_dir / digest[:2] / f"{digest}.json"


def load_dimension_cache(
    cache_dir: Path | None,
    identity: dict[str, Any] | None,
) -> dict[int, TableCachedRowDimensions]:
    if cache_dir is None or identity is None:
        return {}
    path = dimension_cache_path(cache_dir, identity)
    if not path.exists():
        return {}
    try:
        payload = path.read_text(encoding="utf-8")
        import json

        data = json.loads(payload)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("version") != _CACHE_VERSION:
        return {}
    if data.get("identity") != identity:
        return {}
    rows = data.get("rows")
    if not isinstance(rows, list):
        return {}

    loaded: dict[int, TableCachedRowDimensions] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            row_idx = int(row["row"])
            width = int(row["width"])
            height = int(row["height"])
        except (KeyError, TypeError, ValueError):
            continue
        source = str(row.get("source") or "").strip()
        logical_path = str(row.get("path") or "").strip()
        if row_idx < 0 or width <= 0 or height <= 0 or not source or not logical_path:
            continue
        loaded[row_idx] = TableCachedRowDimensions(
            source=source,
            logical_path=logical_path,
            width=width,
            height=height,
        )
    return loaded


def write_dimension_cache(
    cache_dir: Path | None,
    identity: dict[str, Any] | None,
    rows: Iterable[TableDimensionCacheRow],
) -> int:
    if cache_dir is None or identity is None:
        return 0
    payload_rows = [
        {
            "row": row.row_idx,
            "source": row.dimensions.source,
            "path": row.dimensions.logical_path,
            "width": row.dimensions.width,
            "height": row.dimensions.height,
        }
        for row in rows
        if row.dimensions.width > 0 and row.dimensions.height > 0
    ]
    if not payload_rows:
        return 0
    path = dimension_cache_path(cache_dir, identity)
    atomic_write_json(
        path,
        {
            "version": _CACHE_VERSION,
            "identity": identity,
            "rows": payload_rows,
        },
        sort_keys=True,
    )
    return len(payload_rows)
