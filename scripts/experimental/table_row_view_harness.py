#!/usr/bin/env python3
"""Benchmark and small-payload harness for the table row-view backend work."""

from __future__ import annotations

import argparse
import gc
import json
import resource
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from lenslet.server import create_app_from_storage
from lenslet.storage.table import TableStorage, TableStorageOptions
from lenslet.storage.table.launch import TableLaunchRequest, prepare_table_launch


DEFAULT_TARGET = Path(
    "/data/yada/dev_new/pclb2/outputs/"
    "dit03_pretrain_pool_sample_500k_l0l1_multihead_http/"
    "dit03_pretrain_pool_sample_500k_l0l1_multihead_http.parquet"
)


@dataclass(frozen=True, slots=True)
class TimedValue:
    value: Any
    elapsed_seconds: float


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parquet", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--source-column", default="s3key")
    parser.add_argument("--path-column", default=None)
    parser.add_argument("--search-query", default="__lenslet_row_view_no_match__")
    parser.add_argument("--search-repeats", type=int, default=5)
    parser.add_argument("--recursive-limit", type=int, default=5000)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument(
        "--compare-json",
        type=Path,
        default=None,
        help="Compare small-fixture payload hashes against a prior harness JSON and fail on drift.",
    )
    parser.add_argument("--skip-target", action="store_true", help="Only run the small fixture harness.")
    return parser.parse_args()


def _rss_mib() -> float:
    maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return maxrss / (1024 * 1024)
    return maxrss / 1024


def _timed(callable_obj, *args: Any, **kwargs: Any) -> TimedValue:
    start = time.perf_counter()
    value = callable_obj(*args, **kwargs)
    return TimedValue(value=value, elapsed_seconds=time.perf_counter() - start)


def _json_hash(payload: Any) -> str:
    import hashlib

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_fixture_payload(value: Any, root: Path) -> Any:
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, child in value.items():
            if key in {"generated_at", "added_at"} and child:
                normalized[key] = f"<{key}>"
            else:
                normalized[key] = _normalize_fixture_payload(child, root)
        return normalized
    if isinstance(value, list):
        return [_normalize_fixture_payload(child, root) for child in value]
    if isinstance(value, str):
        return value.replace(str(root), "<fixture_root>")
    return value


def _storage_counts(storage: Any) -> dict[str, Any]:
    indexes = getattr(storage, "_indexes", {})
    folder_item_refs = 0
    folder_row_refs = 0
    for index in indexes.values():
        materialized = getattr(index, "_items", None)
        if materialized is not None:
            folder_item_refs += len(materialized)
        folder_row_refs += len(getattr(index, "_item_rows", ()) or ())
    row_store = getattr(storage, "_row_store", None)
    row_to_path = getattr(storage, "_row_to_path", {}) or {}
    if isinstance(row_to_path, dict):
        row_to_path_entries = len(row_to_path)
    else:
        row_to_path_entries = sum(1 for path in row_to_path if path is not None)
    return {
        "dense_items": len(getattr(storage, "_items", {}) or {}),
        "sorted_items": len(getattr(storage, "_sorted_items", []) or []),
        "folder_item_refs": folder_item_refs,
        "folder_row_refs": folder_row_refs,
        "row_to_path_entries": row_to_path_entries,
        "row_store_materialized_items": getattr(row_store, "materialized_item_count", None),
    }


def _sampled_sequence_profile(values: Any) -> dict[str, Any]:
    import sys

    try:
        length = len(values)
    except TypeError:
        length = None
    profile: dict[str, Any] = {
        "type": type(values).__name__,
        "length": length,
        "container_bytes": sys.getsizeof(values),
    }
    nbytes = getattr(values, "nbytes", None)
    if isinstance(nbytes, int):
        profile["arrow_or_numpy_nbytes"] = nbytes
    if not length:
        return profile
    sample_count = min(int(length), 1024)
    step = max(1, int(length) // sample_count)
    sampled = [values[idx] for idx in range(0, int(length), step)][:sample_count]
    if not sampled:
        return profile
    profile["sample_count"] = len(sampled)
    profile["sample_item_avg_bytes"] = sum(sys.getsizeof(item) for item in sampled) / len(sampled)
    profile["estimated_items_bytes"] = int(profile["sample_item_avg_bytes"] * int(length))
    return profile


def _mapping_profile(values: Any) -> dict[str, Any]:
    import sys

    try:
        length = len(values)
    except TypeError:
        length = None
    return {
        "type": type(values).__name__,
        "length": length,
        "container_bytes": sys.getsizeof(values),
    }


def _row_store_profile(row_store: Any) -> dict[str, Any]:
    if row_store is None:
        return {}
    folder_rows = getattr(row_store, "folder_rows", {}) or {}
    folder_children = getattr(row_store, "folder_children", {}) or {}
    return {
        "row_count": getattr(row_store, "row_count", None),
        "paths": _sampled_sequence_profile(getattr(row_store, "paths", ())),
        "sources": _sampled_sequence_profile(getattr(row_store, "sources", ())),
        "names": _sampled_sequence_profile(getattr(row_store, "names", ())),
        "sorted_paths": _sampled_sequence_profile(getattr(row_store, "sorted_paths", ())),
        "sorted_rows": _sampled_sequence_profile(getattr(row_store, "sorted_rows", ())),
        "path_to_row": _mapping_profile(getattr(row_store, "path_to_row", {})),
        "row_to_path": _sampled_sequence_profile(getattr(row_store, "row_to_path", ())),
        "row_to_slot": _sampled_sequence_profile(getattr(row_store, "row_to_slot", ())),
        "folder_count": len(folder_rows),
        "folder_row_refs": sum(len(rows) for rows in folder_rows.values()),
        "folder_children_count": len(folder_children),
        "folder_child_refs": sum(len(children) for children in folder_children.values()),
        "row_dimensions": _sampled_sequence_profile(getattr(row_store, "row_dimensions", ())),
        "dimension_overlays": len(getattr(row_store, "dimensions", {}) or {}),
        "size_overlays": len(getattr(row_store, "size_overrides", {}) or {}),
        "materialized_item_count": getattr(row_store, "materialized_item_count", None),
    }


def _data_column_profile(storage: Any) -> dict[str, Any]:
    data = getattr(storage, "_data", {}) or {}
    columns: dict[str, Any] = {}
    for name, values in data.items():
        columns[str(name)] = _sampled_sequence_profile(values)
    return {
        "column_count": len(data),
        "columns": columns,
    }


def _storage_profile(storage: Any) -> dict[str, Any]:
    return {
        "data_columns": _data_column_profile(storage),
        "row_store": _row_store_profile(getattr(storage, "_row_store", None)),
        "search_caches": {
            "paths_lower": _sampled_sequence_profile(
                getattr(storage, "_search_paths_lower", None) or ()
            ),
            "names_lower": _sampled_sequence_profile(
                getattr(storage, "_search_names_lower", None) or ()
            ),
            "sources_lower": _sampled_sequence_profile(
                getattr(storage, "_search_sources_lower", None) or ()
            ),
        },
        "sidecars": _mapping_profile(getattr(storage, "_sidecars", {}) or {}),
        "thumbnail_cache": {
            "entries": len(getattr(storage, "_thumbnails", {}) or {}),
            "bytes": sum(
                len(value) for value in (getattr(storage, "_thumbnails", {}) or {}).values()
            ),
        },
    }


def _make_image(path: Path, size: tuple[int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=(60, 100, 140)).save(path, format="JPEG")


def _small_fixture_payloads() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="lenslet-row-view-fixture-") as tmp:
        root = Path(tmp)
        _make_image(root / "src" / "cat.jpg", (8, 6))
        _make_image(root / "src" / "dog.jpg", (10, 7))
        storage = TableStorage(
            [
                {
                    "source": str(root / "src" / "cat.jpg"),
                    "path": "gallery/cat.jpg",
                    "label": "cat",
                    "quality_score": 0.91,
                },
                {
                    "source": str(root / "src" / "dog.jpg"),
                    "path": "gallery/dog.jpg",
                    "label": "dog",
                    "quality_score": 0.42,
                },
            ],
            options=TableStorageOptions(root=None, skip_dimension_probe=True),
        )
        app = create_app_from_storage(storage)
        with TestClient(app) as client:
            payloads = {
                "root_browse": client.get("/folders", params={"path": "/"}).json(),
                "recursive_window": client.get(
                    "/folders",
                    params={"path": "/gallery", "recursive": "1", "offset": 0, "limit": 1},
                ).json(),
                "search_hit": client.get("/search", params={"q": "cat", "path": "/"}).json(),
                "search_miss": client.get("/search", params={"q": "not-present", "path": "/"}).json(),
                "media_metadata": client.get("/metadata", params={"path": "/gallery/cat.jpg"}).json(),
                "sidecar_item": client.get("/item", params={"path": "/gallery/cat.jpg"}).json(),
            }
        payloads["embedding_row_lookup"] = {
            "cat": storage.row_index_for_path("/gallery/cat.jpg"),
            "row_index_map": storage.row_index_map(),
        }
        normalized_payloads = {
            name: _normalize_fixture_payload(payload, root)
            for name, payload in payloads.items()
        }
        return {
            "payloads": normalized_payloads,
            "payload_hashes": {name: _json_hash(payload) for name, payload in normalized_payloads.items()},
            "storage_counts": _storage_counts(storage),
        }


def _launch_target(parquet: Path, *, source_column: str, path_column: str | None) -> TimedValue:
    return _timed(
        prepare_table_launch,
        TableLaunchRequest(
            parquet_path=parquet,
            base_dir=None,
            source_column=source_column,
            path_column=path_column,
            cache_dimensions=False,
            skip_dimension_probe=True,
            auto_detect_root=True,
        ),
    )


def _measure_recursive_window(storage: Any, limit: int) -> TimedValue:
    app = create_app_from_storage(storage)
    with TestClient(app) as client:
        return _timed(
            client.get,
            "/folders",
            params={"path": "/", "recursive": "1", "offset": 0, "limit": limit},
        )


def _measure_search_miss(storage: Any, query: str, repeats: int) -> dict[str, Any]:
    durations: list[float] = []
    hit_counts: list[int] = []
    for _idx in range(max(1, repeats)):
        measured = _timed(storage.search, query=query, path="/", limit=100)
        durations.append(measured.elapsed_seconds)
        hit_counts.append(len(measured.value))
    return {
        "query": query,
        "repeats": len(durations),
        "hit_counts": hit_counts,
        "seconds": durations,
        "median_seconds": statistics.median(durations),
        "min_seconds": min(durations),
    }


def _target_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    if not args.parquet.exists():
        return {"skipped": True, "reason": f"parquet not found: {args.parquet}"}
    gc.collect()
    rss_before = _rss_mib()
    launched = _launch_target(args.parquet, source_column=args.source_column, path_column=args.path_column)
    storage = launched.value.storage
    rss_after_launch = _rss_mib()
    profile_after_launch = _storage_profile(storage)
    recursive = _measure_recursive_window(storage, args.recursive_limit)
    search = _measure_search_miss(storage, args.search_query, args.search_repeats)
    rss_after_checks = _rss_mib()
    profile_after_checks = _storage_profile(storage)
    response = recursive.value
    return {
        "skipped": False,
        "parquet": str(args.parquet),
        "source_column": args.source_column,
        "path_column": args.path_column,
        "prepare_table_launch_seconds": launched.elapsed_seconds,
        "rss_mib": {
            "before": rss_before,
            "after_launch": rss_after_launch,
            "after_checks": rss_after_checks,
            "peak": max(rss_before, rss_after_launch, rss_after_checks),
        },
        "storage_counts": _storage_counts(storage),
        "storage_profile": {
            "after_launch": profile_after_launch,
            "after_checks": profile_after_checks,
        },
        "recursive_window": {
            "limit": args.recursive_limit,
            "elapsed_seconds": recursive.elapsed_seconds,
            "status_code": response.status_code,
            "item_count": len(response.json().get("items", [])) if response.status_code == 200 else None,
            "total_items": response.json().get("total_items") if response.status_code == 200 else None,
        },
        "search_miss": search,
    }


def _compare_small_fixture_hashes(payload: dict[str, Any], baseline_path: Path) -> dict[str, Any]:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    expected = baseline.get("small_fixture", {}).get("payload_hashes", {})
    actual = payload.get("small_fixture", {}).get("payload_hashes", {})
    keys = sorted(set(expected) | set(actual))
    mismatches = {
        key: {"expected": expected.get(key), "actual": actual.get(key)}
        for key in keys
        if expected.get(key) != actual.get(key)
    }
    return {
        "baseline": str(baseline_path),
        "ok": not mismatches,
        "mismatches": mismatches,
    }


def main() -> int:
    args = _parse_args()
    payload = {
        "small_fixture": _small_fixture_payloads(),
        "target_500k": None if args.skip_target else _target_benchmark(args),
    }
    exit_code = 0
    if args.compare_json is not None:
        comparison = _compare_small_fixture_hashes(payload, args.compare_json)
        payload["comparison"] = comparison
        if not comparison["ok"]:
            exit_code = 1
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(text + "\n", encoding="utf-8")
    print(text)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
