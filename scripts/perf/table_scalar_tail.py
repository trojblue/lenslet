#!/usr/bin/env python3
"""Profile conditional scalar table-query tails on a deterministic 2,000-row fixture."""

from __future__ import annotations

import argparse
import cProfile
import json
import pstats
import sys
import time
from pathlib import Path
from typing import Any, Callable, Sequence

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lenslet.browse.query import (
    BrowseFilterAst,
    BrowseQuerySpec,
    BuiltinSortSpec,
    DateRangeFilter,
)
from lenslet.storage.table import TableStorage, TableStorageOptions
from scripts.smoke_harness import write_json_evidence


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=2_000)
    parser.add_argument("--repetitions", type=int, default=20)
    parser.add_argument("--output-json", type=Path, default=None)
    return parser.parse_args(argv)


def run_profile(*, row_count: int, repetitions: int) -> dict[str, Any]:
    if row_count <= 0 or repetitions <= 0:
        raise ValueError("rows and repetitions must be positive")
    storage = _build_storage(row_count)
    engine = storage.query_engine
    scope = storage._require_row_store().rows_in_scope("gallery")
    base_spec = BrowseQuerySpec("/gallery", True, 0, row_count)
    analysis = engine.analyze_filter(scope, base_spec)
    date_spec = BrowseQuerySpec(
        "/gallery",
        True,
        0,
        row_count,
        BrowseFilterAst((DateRangeFilter("2023-11-01", "2024-01-31"),)),
        BuiltinSortSpec("name", "asc"),
    )
    return {
        "schema_version": 1,
        "fixture": f"scalar-http-{row_count}",
        "repetitions": repetitions,
        "cases": {
            "date_filter": _profile_case(
                lambda: engine.analyze_filter(scope, date_spec), repetitions
            ),
            "name_desc_order": _profile_case(
                lambda: engine.order(analysis, BuiltinSortSpec("name", "desc")),
                repetitions,
            ),
            "added_desc_order": _profile_case(
                lambda: engine.order(analysis, BuiltinSortSpec("added", "desc")),
                repetitions,
            ),
        },
    }


def _build_storage(row_count: int) -> TableStorage:
    rows = [
        {
            "source": f"https://example.test/assets/item_{index:05d}.jpg",
            "path": f"gallery/item_{index:05d}.jpg",
            "mtime": 1_700_000_000 + index * 60,
        }
        for index in range(row_count)
    ]
    return TableStorage(
        rows,
        options=TableStorageOptions(
            source_column="source",
            path_column="path",
            skip_dimension_probe=True,
            allow_local=False,
        ),
    )


def _profile_case(callback: Callable[[], object], repetitions: int) -> dict[str, Any]:
    profiler = cProfile.Profile()
    started_at = time.perf_counter()
    profiler.enable()
    for _ in range(repetitions):
        callback()
    profiler.disable()
    stats = pstats.Stats(profiler)
    tracked = _tracked_stats(stats)
    return {
        "wall_ms": round((time.perf_counter() - started_at) * 1_000.0, 3),
        "profiler_total_ms": round(stats.total_tt * 1_000.0, 3),
        "functions": tracked,
    }


def _tracked_stats(stats: pstats.Stats) -> dict[str, dict[str, float | int]]:
    tracked_names = {
        "__lt__",
        "_matches_date",
        "_prepare_date_bounds",
        "_reverse_text",
        "analyze_filter",
        "order",
        "parse_query_date_bound",
    }
    tracked: dict[str, dict[str, float | int]] = {}
    for (filename, _line, name), values in stats.stats.items():
        if name not in tracked_names or not filename.endswith(
            ("browse/query.py", "query_engine.py")
        ):
            continue
        _primitive_calls, total_calls, self_seconds, cumulative_seconds, _callers = values
        tracked[f"{Path(filename).name}:{name}"] = {
            "calls": total_calls,
            "self_ms": round(self_seconds * 1_000.0, 3),
            "cumulative_ms": round(cumulative_seconds * 1_000.0, 3),
        }
    return dict(sorted(tracked.items()))


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_profile(row_count=args.rows, repetitions=args.repetitions)
    if args.output_json is not None:
        write_json_evidence(args.output_json, result, sort_keys=False)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
