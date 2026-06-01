#!/usr/bin/env python3
"""Standalone table source-index benchmark.

This script compares the normal strict table-indexing path with the fast
lexical local-path path used for preindexed startup data. The indexing
implementation lives in ``lenslet.storage``; this file is intentionally just a
CLI/reporting wrapper.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lenslet.storage.table import TableStorage, TableStorageOptions, load_parquet_table
from lenslet.storage.source.paths import is_http_url, is_s3_uri


@dataclass(slots=True)
class IndexBuildResult:
    row_count: int
    item_count: int
    folder_count: int
    row_mapped_count: int
    unresolved_remote_dimensions: int
    elapsed_seconds: float
    signature: str


@dataclass(slots=True)
class TableBuildRequest:
    table: Any
    root: str
    source_column: str
    path_column: str | None
    allow_local: bool
    skip_dimension_probe: bool


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark strict TableStorage indexing against the fast local-path "
            "validation mode used for preindexed table startup."
        )
    )
    parser.add_argument(
        "root",
        help="Dataset root used for local source resolution (same value passed to lenslet).",
    )
    parser.add_argument(
        "--parquet",
        default=None,
        help=(
            "Parquet table to index. Defaults to ROOT/.lenslet/preindex/items.parquet "
            "(the startup preindex payload)."
        ),
    )
    parser.add_argument(
        "--source-column",
        default="source",
        help="Source column name (default: source).",
    )
    parser.add_argument(
        "--path-column",
        default="path",
        help="Logical path column name (default: path). Pass an empty value to disable.",
    )
    parser.add_argument(
        "--allow-local",
        action="store_true",
        default=True,
        help="Allow local file sources (default: enabled).",
    )
    parser.add_argument(
        "--no-allow-local",
        action="store_false",
        dest="allow_local",
        help="Disable local file sources.",
    )
    parser.add_argument(
        "--skip-dimension-probe",
        action="store_true",
        help="Skip dimension probing for rows with missing width/height.",
    )
    parser.add_argument(
        "--strict-local-validation",
        action="store_true",
        help="Run the fast build with full realpath and existence checks.",
    )
    parser.add_argument(
        "--compare-baseline",
        action="store_true",
        help="Also build with strict TableStorage validation and compare signatures.",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Optional path to write metrics JSON.",
    )
    return parser.parse_args()


def _load_table(table_path: str) -> Any:
    table = load_parquet_table(table_path)
    if not hasattr(table, "schema") or not hasattr(table, "to_pydict"):
        raise TypeError("expected a pyarrow-like table with schema and to_pydict()")
    return table


def _optional_column(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _encode_scalar(value: Any) -> bytes:
    if value is None:
        return b"<none>"
    return repr(value).encode("utf-8")


def _update_item_signature(digest: Any, item: Any) -> None:
    for value in (
        item.name,
        item.mime,
        item.width,
        item.height,
        item.size,
        item.mtime,
        item.url,
        item.source,
    ):
        digest.update(_encode_scalar(value))
        digest.update(b"\0")

    for key in sorted(item.metrics):
        digest.update(key.encode("utf-8"))
        digest.update(b"=")
        digest.update(_encode_scalar(item.metrics[key]))
        digest.update(b";")
    digest.update(b"\n")


def _storage_signature(storage: TableStorage) -> str:
    digest = hashlib.sha256()

    for path in sorted(storage._items):
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        _update_item_signature(digest, storage._items[path])

    for key in sorted(storage._indexes):
        folder = storage._indexes[key]
        digest.update(key.encode("utf-8"))
        digest.update(b"\0")
        digest.update(folder.path.encode("utf-8"))
        digest.update(b"\0")
        for item in folder.items:
            digest.update(item.path.encode("utf-8"))
            digest.update(b"|")
        digest.update(b"\0")
        for name in folder.dirs:
            digest.update(name.encode("utf-8"))
            digest.update(b"|")
        digest.update(b"\n")

    for row_idx in sorted(storage._row_to_path):
        digest.update(_encode_scalar(row_idx))
        digest.update(b":")
        digest.update(storage._row_to_path[row_idx].encode("utf-8"))
        digest.update(b"\n")

    for idx, dims in enumerate(storage._row_dimensions):
        digest.update(_encode_scalar(idx))
        digest.update(b":")
        if dims is None:
            digest.update(b"<none>")
        else:
            digest.update(_encode_scalar(dims[0]))
            digest.update(b",")
            digest.update(_encode_scalar(dims[1]))
        digest.update(b"\n")

    return digest.hexdigest()


def _unresolved_remote_dimensions(storage: TableStorage, *, skip_dimension_probe: bool) -> int:
    if skip_dimension_probe:
        return 0
    count = 0
    for item in storage._items.values():
        source = item.source or ""
        if (is_s3_uri(source) or is_http_url(source)) and (item.width == 0 or item.height == 0):
            count += 1
    return count


def _build_storage(
    request: TableBuildRequest,
    *,
    strict_local_validation: bool,
) -> TableStorage:
    return TableStorage(
        table=request.table,
        options=TableStorageOptions(
            root=request.root,
            source_column=request.source_column,
            path_column=request.path_column,
            skip_dimension_probe=request.skip_dimension_probe,
            allow_local=request.allow_local,
            skip_local_realpath_validation=not strict_local_validation,
        ),
    )


def _build_result(
    request: TableBuildRequest,
    *,
    strict_local_validation: bool,
) -> IndexBuildResult:
    start = time.perf_counter()
    storage = _build_storage(request, strict_local_validation=strict_local_validation)
    elapsed = time.perf_counter() - start
    return IndexBuildResult(
        row_count=storage._row_count,
        item_count=len(storage._items),
        folder_count=len(storage._indexes),
        row_mapped_count=len(storage._row_to_path),
        unresolved_remote_dimensions=_unresolved_remote_dimensions(
            storage,
            skip_dimension_probe=request.skip_dimension_probe,
        ),
        elapsed_seconds=elapsed,
        signature=_storage_signature(storage),
    )


def _run_baseline(request: TableBuildRequest) -> IndexBuildResult:
    return _build_result(request, strict_local_validation=True)


def _result_payload(result: IndexBuildResult) -> dict[str, Any]:
    speed = result.row_count / max(result.elapsed_seconds, 1e-9)
    return {
        "row_count": result.row_count,
        "item_count": result.item_count,
        "folder_count": result.folder_count,
        "row_mapped_count": result.row_mapped_count,
        "unresolved_remote_dimensions": result.unresolved_remote_dimensions,
        "elapsed_seconds": result.elapsed_seconds,
        "img_per_second": speed,
        "signature": result.signature,
    }


def _print_result(label: str, result: IndexBuildResult) -> None:
    speed = result.row_count / max(result.elapsed_seconds, 1e-9)
    print(f"[fast-index] {label}: {result.elapsed_seconds:.3f}s ({speed:.2f} img/s)")
    print(
        "[fast-index] outputs: "
        f"items={result.item_count}, folders={result.folder_count}, "
        f"row_mapped={result.row_mapped_count}, "
        f"unresolved_remote_dims={result.unresolved_remote_dimensions}"
    )
    print(f"[fast-index] {label} signature: {result.signature}")


def _print_summary(
    *,
    fast_result: IndexBuildResult,
    baseline: IndexBuildResult | None,
) -> dict[str, Any]:
    print(f"[fast-index] table rows: {fast_result.row_count}")
    _print_result("fast TableStorage", fast_result)

    payload: dict[str, Any] = {"fast": _result_payload(fast_result)}
    if baseline is None:
        return payload

    speedup = baseline.elapsed_seconds / max(fast_result.elapsed_seconds, 1e-9)
    matches = baseline.signature == fast_result.signature
    _print_result("strict TableStorage", baseline)
    print(f"[fast-index] signature match: {matches}")
    print(f"[fast-index] speedup vs strict: {speedup:.2f}x")
    payload["baseline"] = _result_payload(baseline)
    payload["comparison"] = {
        "signature_match": matches,
        "speedup_factor": speedup,
    }
    return payload


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    replaced = False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, path)
        replaced = True
    finally:
        if not replaced:
            with contextlib.suppress(OSError):
                os.unlink(temp_name)


def main() -> int:
    args = _parse_args()
    root = str(Path(args.root).resolve())
    parquet_path = (
        args.parquet
        if args.parquet
        else str(Path(root) / ".lenslet" / "preindex" / "items.parquet")
    )
    parquet_path = str(Path(parquet_path).resolve())
    if not Path(parquet_path).is_file():
        print(f"[fast-index] Error: parquet table not found: {parquet_path}", file=sys.stderr)
        return 2

    request = TableBuildRequest(
        table=_load_table(parquet_path),
        root=root,
        source_column=args.source_column,
        path_column=_optional_column(args.path_column),
        allow_local=args.allow_local,
        skip_dimension_probe=args.skip_dimension_probe,
    )
    fast_result = _build_result(
        request,
        strict_local_validation=args.strict_local_validation,
    )
    baseline = _run_baseline(request) if args.compare_baseline else None
    payload = _print_summary(fast_result=fast_result, baseline=baseline)

    if args.output_json:
        output_path = Path(args.output_json).resolve()
        _write_json_atomic(output_path, payload)
        print(f"[fast-index] Wrote JSON summary: {output_path}")

    if baseline is not None and baseline.signature != fast_result.signature:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
