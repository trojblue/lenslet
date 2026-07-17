#!/usr/bin/env python3
"""Measure Lenslet table query and facet latency with stable JSON output."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient

from lenslet.server import BrowseAppOptions, StorageAppOptions, create_app_from_storage
from lenslet.storage.table import TableStorage, TableStorageOptions, load_parquet_table
from lenslet.workspace import Workspace
from scripts.perf.table_query_fixture import (
    DEFAULT_METRIC_COUNT,
    DEFAULT_RATED_COUNT,
    DEFAULT_ROW_COUNT,
    build_synthetic_table_fixture,
    table_query_body,
)
from scripts.smoke_harness import write_json_evidence


SCHEMA_VERSION = 1


class InputMutationError(RuntimeError):
    """Raised when a supposedly read-only source file changes during a probe."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--synthetic", action="store_true", help="Generate the controlled table fixture."
    )
    source.add_argument("--parquet", type=Path, help="Probe an existing Parquet file read-only.")
    parser.add_argument("--source-column", default=None)
    parser.add_argument("--path-column", default=None)
    parser.add_argument("--base-dir", type=Path, default=None)
    parser.add_argument("--rows", type=int, default=DEFAULT_ROW_COUNT)
    parser.add_argument("--metrics", type=int, default=DEFAULT_METRIC_COUNT)
    parser.add_argument("--rated", type=int, default=DEFAULT_RATED_COUNT)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--repetitions", type=int, default=20)
    parser.add_argument("--output-json", type=Path, default=None)
    return parser.parse_args(argv)


def percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be between zero and one")
    ordered = sorted(float(value) for value in values)
    rank = (len(ordered) - 1) * quantile
    lower = int(rank)
    upper = min(len(ordered) - 1, lower + 1)
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def parse_server_timing(header: str) -> dict[str, float]:
    timings: dict[str, float] = {}
    for raw_entry in header.split(","):
        parts = [part.strip() for part in raw_entry.split(";") if part.strip()]
        if not parts:
            continue
        duration = next((part[4:] for part in parts[1:] if part.startswith("dur=")), None)
        if duration is None:
            continue
        try:
            timings[parts[0]] = float(duration)
        except ValueError:
            continue
    return timings


def run_probe(
    parquet_path: Path,
    *,
    fixture_name: str,
    source_column: str | None,
    path_column: str | None,
    base_dir: Path,
    rated_count: int | None,
    warmups: int,
    repetitions: int,
) -> dict[str, Any]:
    if warmups < 0 or repetitions <= 0:
        raise ValueError("warmups must be non-negative and repetitions must be positive")
    workspace = Workspace.for_parquet(parquet_path, can_write=False)
    input_paths = _probe_input_paths(parquet_path, workspace)
    input_state = _input_state(input_paths)
    storage = TableStorage(
        load_parquet_table(str(parquet_path)),
        options=TableStorageOptions(
            root=str(base_dir),
            source_column=source_column,
            path_column=path_column,
            skip_dimension_probe=True,
        ),
    )
    metric_keys = storage.metric_keys()
    body = table_query_body(metric_keys)
    app = create_app_from_storage(
        storage,
        options=StorageAppOptions(
            browse=BrowseAppOptions(thumb_cache=False),
            workspace=workspace,
            storage_mode="table",
            storage_origin="latency-probe",
            refresh="static",
        ),
    )
    actual_rated_count = sum(
        1 for _, sidecar in storage.sidecar_items() if sidecar.get("star") is not None
    )
    if rated_count is not None and actual_rated_count != rated_count:
        raise RuntimeError(
            "loaded rated sidecar count does not match fixture: "
            f"{actual_rated_count} != {rated_count}"
        )

    query_ms: list[float] = []
    facets_ms: list[float] = []
    combined_ms: list[float] = []
    query_bytes: list[float] = []
    facets_bytes: list[float] = []
    phase_samples: dict[str, dict[str, list[float]]] = {"query": {}, "facets": {}}
    correctness: dict[str, Any] | None = None

    with TestClient(app) as client:
        for _ in range(warmups):
            _request_pair(client, body)
        for _ in range(repetitions):
            pair_started = time.perf_counter()
            query_response, query_elapsed = _timed_post(client, "/folders/query", body)
            facets_response, facets_elapsed = _timed_post(client, "/folders/facets", body)
            combined_ms.append((time.perf_counter() - pair_started) * 1000.0)
            query_ms.append(query_elapsed)
            facets_ms.append(facets_elapsed)
            query_bytes.append(float(_response_bytes(query_response)))
            facets_bytes.append(float(_response_bytes(facets_response)))
            _collect_phase_samples(
                phase_samples["query"], query_response.headers.get("server-timing", "")
            )
            _collect_phase_samples(
                phase_samples["facets"], facets_response.headers.get("server-timing", "")
            )
            current = _correctness_payload(query_response.json(), facets_response.json())
            if correctness is None:
                correctness = current
            elif correctness != current:
                raise RuntimeError("query/facet correctness counts changed across repetitions")
        health = client.get("/health").json()

    if _input_state(input_paths) != input_state:
        raise InputMutationError(f"input files changed during read-only probe: {parquet_path.name}")

    combined_bytes = [query + facets for query, facets in zip(query_bytes, facets_bytes)]
    counters = health.get("hotpath", {}).get("counters", {})
    return {
        "schema_version": SCHEMA_VERSION,
        "fixture": fixture_name,
        "input_name": parquet_path.name,
        "input_unchanged": True,
        "warmups": warmups,
        "repetitions": repetitions,
        "query_p50_ms": round(percentile(query_ms, 0.50), 3),
        "query_p95_ms": round(percentile(query_ms, 0.95), 3),
        "facets_p50_ms": round(percentile(facets_ms, 0.50), 3),
        "facets_p95_ms": round(percentile(facets_ms, 0.95), 3),
        "combined_p50_ms": round(percentile(combined_ms, 0.50), 3),
        "combined_p95_ms": round(percentile(combined_ms, 0.95), 3),
        "response_bytes_p95": round(percentile(combined_bytes, 0.95)),
        "analysis_started": int(counters.get("analysis_started_total", 0)),
        "analysis_joined": int(counters.get("analysis_joined_total", 0)),
        "analysis_superseded": int(counters.get("analysis_superseded_total", 0)),
        "analysis_cancelled": int(counters.get("analysis_cancelled_total", 0)),
        "latency_ms": {
            "query": _summary(query_ms),
            "facets": _summary(facets_ms),
            "combined": _summary(combined_ms),
        },
        "response_bytes": {
            "query": _summary(query_bytes),
            "facets": _summary(facets_bytes),
            "combined": _summary(combined_bytes),
        },
        "server_timing_ms": {
            endpoint: {phase: _summary(samples) for phase, samples in phases.items()}
            for endpoint, phases in phase_samples.items()
        },
        "sidecars": {"rated": actual_rated_count},
        "correctness": correctness or {},
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    temporary_root: Path | None = None
    try:
        if args.synthetic:
            temporary_root = Path(tempfile.mkdtemp(prefix="lenslet-table-latency-")).resolve()
            fixture = build_synthetic_table_fixture(
                temporary_root,
                row_count=args.rows,
                metric_count=args.metrics,
                rated_count=args.rated,
            )
            parquet_path = fixture.parquet_path
            fixture_name = fixture.name
            source_column = args.source_column or "image_path"
            path_column = args.path_column or "path"
            rated_count = fixture.rated_count
        else:
            parquet_path = args.parquet.resolve()
            fixture_name = f"parquet-{parquet_path.name}"
            source_column = args.source_column
            path_column = args.path_column
            rated_count = None
        if not parquet_path.is_file():
            raise SystemExit(f"Parquet file does not exist: {parquet_path}")
        base_dir = (args.base_dir or parquet_path.parent).resolve()
        result = run_probe(
            parquet_path,
            fixture_name=fixture_name,
            source_column=source_column,
            path_column=path_column,
            base_dir=base_dir,
            rated_count=rated_count,
            warmups=args.warmups,
            repetitions=args.repetitions,
        )
        if args.output_json is not None:
            write_json_evidence(args.output_json, result, sort_keys=False)
        print(json.dumps(result, indent=2))
        return 0
    finally:
        if temporary_root is not None:
            shutil.rmtree(temporary_root, ignore_errors=True)


def _timed_post(client: TestClient, path: str, body: dict[str, Any]):
    started_at = time.perf_counter()
    response = client.post(
        path,
        json=body,
        headers={
            "X-Lenslet-Client-Session": "table-query-latency-probe",
            "X-Lenslet-Query-Revision": "1",
        },
    )
    elapsed_ms = (time.perf_counter() - started_at) * 1000.0
    if response.status_code != 200:
        raise RuntimeError(f"{path} returned {response.status_code}: {response.text[:300]}")
    return response, elapsed_ms


def _request_pair(client: TestClient, body: dict[str, Any]) -> None:
    _timed_post(client, "/folders/query", body)
    _timed_post(client, "/folders/facets", body)


def _response_bytes(response) -> int:
    """Return decoded JSON bytes for comparison with payload-size budgets."""
    return len(response.content)


def _collect_phase_samples(samples: dict[str, list[float]], header: str) -> None:
    for phase, duration_ms in parse_server_timing(header).items():
        samples.setdefault(phase, []).append(duration_ms)


def _correctness_payload(query: dict[str, Any], facets: dict[str, Any]) -> dict[str, Any]:
    filtered_total = int(query["filtered_total"])
    facet_total = int(facets["total_items"])
    if filtered_total != facet_total:
        raise RuntimeError(
            f"query/facet filtered totals disagree: {filtered_total} != {facet_total}"
        )
    return {
        "scope_total": int(query["scope_total"]),
        "filtered_total": filtered_total,
        "facet_total": facet_total,
        "window_items": len(query.get("items", [])),
        "metric_keys": list(query.get("metric_keys", [])),
    }


def _summary(values: Sequence[float]) -> dict[str, float | int]:
    return {
        "count": len(values),
        "min": round(min(values), 3),
        "p50": round(percentile(values, 0.50), 3),
        "p95": round(percentile(values, 0.95), 3),
        "max": round(max(values), 3),
    }


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe_input_paths(parquet_path: Path, workspace: Workspace) -> tuple[Path, ...]:
    paths = [parquet_path]
    for path in (workspace.labels_snapshot_path(), workspace.labels_log_path()):
        if path is not None:
            paths.append(path)
    return tuple(paths)


def _input_state(paths: Sequence[Path]) -> dict[str, str | None]:
    return {str(path): _file_digest(path) if path.is_file() else None for path in paths}


if __name__ == "__main__":
    raise SystemExit(main())
