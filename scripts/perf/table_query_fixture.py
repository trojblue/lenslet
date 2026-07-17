from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from lenslet.storage.base import SidecarStorage
from lenslet.workspace import Workspace


DEFAULT_ROW_COUNT = 2_000
DEFAULT_METRIC_COUNT = 30
DEFAULT_RATED_COUNT = 300


@dataclass(frozen=True, slots=True)
class SyntheticTableFixture:
    parquet_path: Path
    row_count: int
    metric_count: int
    rated_count: int

    @property
    def name(self) -> str:
        return f"synthetic-{self.row_count}x{self.metric_count}"


def build_synthetic_table_fixture(
    root: Path,
    *,
    row_count: int = DEFAULT_ROW_COUNT,
    metric_count: int = DEFAULT_METRIC_COUNT,
    rated_count: int = DEFAULT_RATED_COUNT,
) -> SyntheticTableFixture:
    if row_count <= 0:
        raise ValueError("row_count must be positive")
    if metric_count < 3:
        raise ValueError("metric_count must be at least three")
    if rated_count < 0 or rated_count > row_count:
        raise ValueError("rated_count must be between zero and row_count")

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - runtime dependency guard
        raise RuntimeError("pyarrow is required for table latency fixtures") from exc

    root.mkdir(parents=True, exist_ok=True)
    (root / "shared.jpg").write_bytes(_jpeg_payload())
    columns = _fixture_columns(row_count=row_count, metric_count=metric_count)
    parquet_path = root / "items.parquet"
    pq.write_table(pa.table(columns), parquet_path)

    workspace = Workspace.for_parquet(parquet_path, can_write=True)
    workspace.write_labels_snapshot(_labels_snapshot(rated_count))
    return SyntheticTableFixture(
        parquet_path=parquet_path,
        row_count=row_count,
        metric_count=metric_count,
        rated_count=rated_count,
    )


def apply_synthetic_sidecars(storage: SidecarStorage, rated_count: int) -> None:
    for index in range(rated_count):
        storage.set_sidecar(_item_path(index), _rated_sidecar())


def table_query_body(metric_keys: list[str], *, limit: int = 1_000) -> dict[str, Any]:
    if len(metric_keys) < 3:
        raise ValueError("the table latency scenario requires at least three metric keys")
    return {
        "path": "/gallery",
        "recursive": True,
        "offset": 0,
        "limit": limit,
        "filters": {
            "and": [
                {"starsIn": {"values": [0]}},
                *[
                    {
                        "metricRange": {
                            "key": key,
                            "min": -1e308,
                            "max": 1e308,
                        }
                    }
                    for key in metric_keys[:3]
                ],
            ],
        },
        "sort": {"kind": "builtin", "key": "name", "dir": "asc"},
        "projection": {
            "metric_keys": metric_keys[:3],
            "categorical_keys": [],
        },
    }


def _fixture_columns(*, row_count: int, metric_count: int) -> dict[str, list[Any]]:
    columns: dict[str, list[Any]] = {
        "image_path": ["shared.jpg"] * row_count,
        "path": [_item_path(index).lstrip("/") for index in range(row_count)],
        "mtime": [1_700_000_000 + index for index in range(row_count)],
        "width": [24] * row_count,
        "height": [18] * row_count,
        "dataset_split": [f"split-{index % 4}" for index in range(row_count)],
    }
    for metric_index in range(metric_count):
        key = f"metric_{metric_index:03d}"
        columns[key] = [
            ((row_index * (metric_index + 3)) % 1_003) / 1_002 for row_index in range(row_count)
        ]
    return columns


def _labels_snapshot(rated_count: int) -> dict[str, Any]:
    return {
        "version": 1,
        "last_event_id": rated_count,
        "items": {_item_path(index): _rated_sidecar() for index in range(rated_count)},
    }


def _rated_sidecar() -> dict[str, Any]:
    return {
        "tags": [],
        "notes": "",
        "star": 1,
        "version": 2,
        "updated_at": "2026-07-17T00:00:00Z",
        "updated_by": "fixture",
    }


def _item_path(index: int) -> str:
    return f"/gallery/item_{index:05d}.jpg"


def _jpeg_payload() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (24, 18), color=(44, 88, 132)).save(
        buffer,
        format="JPEG",
        quality=80,
    )
    return buffer.getvalue()
