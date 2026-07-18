#!/usr/bin/env python3
"""Measure alternating multi-row-group table detail reads."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from time import perf_counter
from typing import Any, Sequence

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient

from lenslet.server import BrowseAppOptions, StorageAppOptions, create_app_from_storage
from lenslet.storage.table.launch import ParquetRowFieldProvider, TableLaunchRequest, prepare_table_launch
from lenslet.workspace import Workspace
from scripts.perf.table_query_latency import percentile
from scripts.smoke_harness import write_json_evidence


SCHEMA_VERSION = 1
DEFAULT_ROW_COUNT = 4_000
DEFAULT_ROW_GROUP_SIZE = 500
DEFAULT_WARMUP_ROUNDS = 1
DEFAULT_REPETITIONS = 20


class _CountingParquetFile:
    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.calls: list[int] = []

    def read_row_group(self, row_group: int, *, columns: list[str]):
        self.calls.append(row_group)
        return self._inner.read_row_group(row_group, columns=columns)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=DEFAULT_ROW_COUNT)
    parser.add_argument("--row-group-size", type=int, default=DEFAULT_ROW_GROUP_SIZE)
    parser.add_argument("--warmup-rounds", type=int, default=DEFAULT_WARMUP_ROUNDS)
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS)
    parser.add_argument("--max-p95-ms", type=float, default=50.0)
    parser.add_argument("--output-json", type=Path, default=None)
    return parser.parse_args(argv)


def run_probe(
    *,
    row_count: int = DEFAULT_ROW_COUNT,
    row_group_size: int = DEFAULT_ROW_GROUP_SIZE,
    warmup_rounds: int = DEFAULT_WARMUP_ROUNDS,
    repetitions: int = DEFAULT_REPETITIONS,
) -> dict[str, Any]:
    if row_group_size <= 0 or row_count < row_group_size * 4:
        raise ValueError("fixture must contain at least four non-empty row groups")
    if warmup_rounds < 0 or repetitions <= 0:
        raise ValueError("warmup rounds must be non-negative and repetitions must be positive")

    with tempfile.TemporaryDirectory(prefix="lenslet-row-groups-") as temp_dir:
        parquet_path = Path(temp_dir) / "items.parquet"
        _write_fixture(parquet_path, row_count=row_count, row_group_size=row_group_size)
        launch = prepare_table_launch(
            TableLaunchRequest(
                parquet_path=parquet_path,
                base_dir=None,
                source_column="source",
                path_column="path",
                cache_dimensions=False,
                skip_dimension_probe=True,
            )
        )
        provider = launch.storage._row_field_provider
        if not isinstance(provider, ParquetRowFieldProvider):
            raise RuntimeError("fixture did not install the Parquet row-field provider")
        counting = _CountingParquetFile(provider._parquet_file)
        provider._parquet_file = counting
        paths = [f"/group_{group}/item_{group * row_group_size}.jpg" for group in range(4)]
        app = create_app_from_storage(
            launch.storage,
            options=StorageAppOptions(
                browse=BrowseAppOptions(thumb_cache=False),
                workspace=Workspace.for_dataset(None, can_write=False),
                storage_mode="table",
                storage_origin="parquet",
                refresh="static",
            ),
        )

        latencies: list[float] = []
        with TestClient(app) as client:
            for _ in range(warmup_rounds):
                _read_paths(client, paths)
            warmup_reads = len(counting.calls)
            counting.calls.clear()
            for _ in range(repetitions):
                for path in paths:
                    start = perf_counter()
                    response = client.get("/item", params={"path": path})
                    latencies.append((perf_counter() - start) * 1_000)
                    row_index = int(path.rsplit("item_", 1)[1].split(".", 1)[0])
                    table_fields = response.json().get("table_fields") or {}
                    if response.status_code != 200 or table_fields.get("field_0") != f"value-0-{row_index}":
                        raise RuntimeError(f"unexpected detail response for {path}")

        return {
            "schema_version": SCHEMA_VERSION,
            "fixture": f"synthetic-{row_count}-rows-{row_count // row_group_size}-groups",
            "detail_endpoint": "/item",
            "row_count": row_count,
            "row_group_count": row_count // row_group_size,
            "row_group_size": row_group_size,
            "working_set_groups": 4,
            "warmup_rounds": warmup_rounds,
            "repetitions": repetitions,
            "requests": len(latencies),
            "latency_ms": {
                "p50": percentile(latencies, 0.5),
                "p95": percentile(latencies, 0.95),
                "max": max(latencies),
            },
            "row_group_reads": {
                "warmup": warmup_reads,
                "measured": len(counting.calls),
            },
            "cache": {
                "capacity_groups": 4,
                "retained_groups": len(provider._row_group_cache),
            },
        }


def _read_paths(client: TestClient, paths: list[str]) -> None:
    for path in paths:
        response = client.get("/item", params={"path": path})
        if response.status_code != 200:
            raise RuntimeError(f"failed to warm detail path {path}")


def _write_fixture(parquet_path: Path, *, row_count: int, row_group_size: int) -> None:
    columns: dict[str, list[Any]] = {
        "source": [f"https://example.test/media/{index}.jpg" for index in range(row_count)],
        "path": [
            f"group_{index // row_group_size}/item_{index}.jpg"
            for index in range(row_count)
        ],
    }
    for field_index in range(12):
        columns[f"field_{field_index}"] = [
            f"value-{field_index}-{row_index}"
            for row_index in range(row_count)
        ]
    pq.write_table(pa.table(columns), parquet_path, row_group_size=row_group_size)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_probe(
        row_count=args.rows,
        row_group_size=args.row_group_size,
        warmup_rounds=args.warmup_rounds,
        repetitions=args.repetitions,
    )
    if args.output_json is not None:
        write_json_evidence(args.output_json, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["latency_ms"]["p95"] <= args.max_p95_ms else 1


if __name__ == "__main__":
    raise SystemExit(main())
