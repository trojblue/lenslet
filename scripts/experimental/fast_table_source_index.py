#!/usr/bin/env python3
"""Standalone table:source index benchmark and fast-path prototype.

This script emulates Lenslet's table index assembly and reports throughput.
It is intentionally not wired into server startup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Allow direct execution from repo root without editable install.
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from lenslet.storage.table import TableStorage, load_parquet_table
from lenslet.storage.table_facade import guess_mime
from lenslet.storage.table_media import read_dimensions_fast
from lenslet.storage.table_paths import (
    compute_local_prefix,
    compute_s3_prefixes,
    dedupe_path,
    derive_logical_path,
    extract_name,
    is_http_url,
    is_s3_uri,
    is_supported_image,
    normalize_item_path,
    normalize_path,
    resolve_local_source,
)
from lenslet.storage.table_schema import coerce_float, coerce_int, coerce_timestamp


@dataclass(slots=True)
class IndexedItem:
    path: str
    name: str
    mime: str
    width: int
    height: int
    size: int
    mtime: float
    url: str | None = None
    source: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class IndexedFolder:
    path: str
    generated_at: str
    items: list[IndexedItem] = field(default_factory=list)
    dirs: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FastBuildResult:
    row_count: int
    items: dict[str, IndexedItem]
    indexes: dict[str, IndexedFolder]
    source_paths: dict[str, str]
    row_dimensions: list[tuple[int, int] | None]
    row_to_path: dict[int, str]
    path_to_row: dict[str, int]
    skipped_local: int
    remote_task_count: int
    elapsed_seconds: float


@dataclass(slots=True)
class BaselineResult:
    row_count: int
    item_count: int
    folder_count: int
    elapsed_seconds: float
    signature: str


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Standalone table:source index benchmark with a preindex-optimized "
            "fast path and optional baseline comparison."
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
        help="Logical path column name (default: path).",
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
        "--skip-indexing",
        action="store_true",
        help="Skip dimension probing for rows with missing width/height.",
    )
    parser.add_argument(
        "--strict-local-validation",
        action="store_true",
        help=(
            "Use the same per-row local path resolution and existence checks as "
            "TableStorage (slower, but strict)."
        ),
    )
    parser.add_argument(
        "--compare-baseline",
        action="store_true",
        help="Also build via TableStorage and compare signatures + throughput.",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Optional path to write metrics JSON.",
    )
    return parser.parse_args()


def _load_table(table_path: str):
    table = load_parquet_table(table_path)
    if not hasattr(table, "schema") or not hasattr(table, "to_pydict"):
        raise TypeError("expected a pyarrow-like table with schema and to_pydict()")
    return table


def _collect_metric_columns(
    *,
    columns: list[str],
    data: dict[str, list[Any]],
    none_values: list[Any],
    source_column: str,
    path_column: str | None,
) -> tuple[tuple[str, list[Any]], ...]:
    used = {
        source_column,
        path_column,
        "name",
        "mime",
        "width",
        "height",
        "size",
        "mtime",
    }
    metric_columns: list[tuple[str, list[Any]]] = []
    for column in columns:
        if column in used:
            continue
        if column.lower() in TableStorage.RESERVED_COLUMNS:
            continue
        metric_columns.append((column, data.get(column, none_values)))
    return tuple(metric_columns)


def _resolve_local_source_fast(
    source: str,
    *,
    root_abs: str | None,
    root_prefix: str | None,
) -> str:
    if os.path.isabs(source) or not root_abs:
        return source
    candidate = os.path.abspath(os.path.join(root_abs, source))
    if root_prefix and candidate != root_abs and not candidate.startswith(root_prefix):
        raise ValueError("path escapes base_dir")
    return candidate


def _encode_scalar(value: Any) -> bytes:
    if value is None:
        return b"<none>"
    return repr(value).encode("utf-8")


def _signature_from_fast(result: FastBuildResult) -> str:
    digest = hashlib.sha256()

    for path in sorted(result.items):
        item = result.items[path]
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_encode_scalar(item.name))
        digest.update(b"\0")
        digest.update(_encode_scalar(item.mime))
        digest.update(b"\0")
        digest.update(_encode_scalar(item.width))
        digest.update(b"\0")
        digest.update(_encode_scalar(item.height))
        digest.update(b"\0")
        digest.update(_encode_scalar(item.size))
        digest.update(b"\0")
        digest.update(_encode_scalar(item.mtime))
        digest.update(b"\0")
        digest.update(_encode_scalar(item.url))
        digest.update(b"\0")
        digest.update(_encode_scalar(item.source))
        digest.update(b"\0")
        for key in sorted(item.metrics):
            digest.update(key.encode("utf-8"))
            digest.update(b"=")
            digest.update(_encode_scalar(item.metrics[key]))
            digest.update(b";")
        digest.update(b"\n")

    for key in sorted(result.indexes):
        folder = result.indexes[key]
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

    for row_idx in sorted(result.row_to_path):
        digest.update(_encode_scalar(row_idx))
        digest.update(b":")
        digest.update(result.row_to_path[row_idx].encode("utf-8"))
        digest.update(b"\n")

    for idx, dims in enumerate(result.row_dimensions):
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


def _signature_from_storage(storage: TableStorage) -> str:
    digest = hashlib.sha256()

    for path in sorted(storage._items):
        item = storage._items[path]
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_encode_scalar(item.name))
        digest.update(b"\0")
        digest.update(_encode_scalar(item.mime))
        digest.update(b"\0")
        digest.update(_encode_scalar(item.width))
        digest.update(b"\0")
        digest.update(_encode_scalar(item.height))
        digest.update(b"\0")
        digest.update(_encode_scalar(item.size))
        digest.update(b"\0")
        digest.update(_encode_scalar(item.mtime))
        digest.update(b"\0")
        digest.update(_encode_scalar(item.url))
        digest.update(b"\0")
        digest.update(_encode_scalar(item.source))
        digest.update(b"\0")
        for key in sorted(item.metrics):
            digest.update(key.encode("utf-8"))
            digest.update(b"=")
            digest.update(_encode_scalar(item.metrics[key]))
            digest.update(b";")
        digest.update(b"\n")

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


def build_fast_indexes(
    *,
    table,
    root: str,
    source_column: str,
    path_column: str | None,
    allow_local: bool,
    skip_indexing: bool,
    strict_local_validation: bool,
) -> tuple[FastBuildResult, str]:
    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    columns = list(table.schema.names)
    data = table.to_pydict()
    row_count = len(data.get(columns[0], [])) if columns else 0
    if row_count <= 0:
        raise ValueError("table is empty")
    if source_column not in data:
        raise ValueError(f"missing source column: {source_column}")

    none_values: list[Any] = [None] * row_count
    source_values = data.get(source_column, none_values)
    path_values = data.get(path_column, none_values) if path_column else none_values
    name_values = data.get("name", none_values)
    mime_values = data.get("mime", none_values)
    width_values = data.get("width", none_values)
    height_values = data.get("height", none_values)
    size_values = data.get("size", none_values)
    mtime_values = data.get("mtime", none_values)
    metrics_values = data.get("metrics", none_values)
    metric_columns = _collect_metric_columns(
        columns=columns,
        data=data,
        none_values=none_values,
        source_column=source_column,
        path_column=path_column,
    )

    s3_prefixes, s3_use_bucket = compute_s3_prefixes(source_values)
    local_prefix = compute_local_prefix(source_values) if allow_local else None
    root_abs = os.path.abspath(root) if root else None
    root_real = os.path.realpath(root) if root else None
    root_prefix = f"{root_abs}{os.sep}" if root_abs else None
    has_path_column = bool(path_column)
    has_metrics_column = "metrics" in data

    items: dict[str, IndexedItem] = {}
    indexes: dict[str, IndexedFolder] = {}
    source_paths: dict[str, str] = {}
    row_dimensions: list[tuple[int, int] | None] = [None] * row_count
    row_to_path: dict[int, str] = {}
    path_to_row: dict[str, int] = {}
    dir_children: dict[str, set[str]] = {}

    seen_paths: set[str] = set()
    skipped_local = 0
    remote_task_count = 0

    start = time.perf_counter()
    for idx in range(row_count):
        source_value = source_values[idx]
        if source_value is None:
            continue
        if isinstance(source_value, os.PathLike):
            source_value = os.fspath(source_value)
        if not isinstance(source_value, str):
            continue

        source = source_value.strip()
        if not source:
            continue

        fallback_name = extract_name(source)
        name_value = name_values[idx]
        name = str(name_value).strip() if name_value else fallback_name
        if not is_supported_image(name, TableStorage.IMAGE_EXTS):
            if is_supported_image(fallback_name, TableStorage.IMAGE_EXTS):
                name = fallback_name
            else:
                continue

        logical_value = path_values[idx] if has_path_column and not is_s3_uri(source) else None
        logical_path = (
            str(logical_value).strip()
            if logical_value
            else derive_logical_path(
                source,
                root=root,
                local_prefix=local_prefix,
                s3_prefixes=s3_prefixes,
                s3_use_bucket=s3_use_bucket,
            )
        )
        logical_path = normalize_item_path(logical_path)
        if not logical_path:
            continue

        logical_path = dedupe_path(logical_path, seen_paths)
        seen_paths.add(logical_path)

        mime_value = mime_values[idx]
        mime = str(mime_value).strip() if mime_value else guess_mime(name or fallback_name or source)

        size = coerce_int(size_values[idx])
        mtime = coerce_timestamp(mtime_values[idx])
        width = coerce_int(width_values[idx])
        height = coerce_int(height_values[idx])

        is_s3 = is_s3_uri(source)
        is_http = is_http_url(source)
        is_local = not is_s3 and not is_http
        resolved_local_source: str | None = None

        if is_local:
            if not allow_local:
                skipped_local += 1
                continue
            try:
                if strict_local_validation:
                    resolved_local_source = resolve_local_source(
                        source,
                        root=root,
                        root_real=root_real,
                        allow_local=allow_local,
                    )
                else:
                    resolved_local_source = _resolve_local_source_fast(
                        source,
                        root_abs=root_abs,
                        root_prefix=root_prefix,
                    )
            except ValueError:
                skipped_local += 1
                continue

            if strict_local_validation and not os.path.exists(resolved_local_source):
                print(f"[fast-index] Warning: File not found: {resolved_local_source}")
                continue

            if size is None:
                try:
                    size = os.path.getsize(resolved_local_source)
                except Exception:
                    size = 0

        if size is None:
            size = 0

        if mtime is None:
            if is_local:
                try:
                    local_source = resolved_local_source or source
                    mtime = os.path.getmtime(local_source)
                except Exception:
                    mtime = time.time()
            else:
                mtime = time.time()

        w = width or 0
        h = height or 0
        if (w == 0 or h == 0) and is_local and not skip_indexing:
            try:
                local_source = resolved_local_source or source
                dims = read_dimensions_fast(local_source)
                if dims:
                    w, h = dims
            except Exception:
                pass

        metrics: dict[str, float] = {}
        for metric_key, metric_values in metric_columns:
            num = coerce_float(metric_values[idx])
            if num is None:
                continue
            metrics[metric_key] = num
        if has_metrics_column:
            raw_metrics = metrics_values[idx]
            if isinstance(raw_metrics, dict):
                for raw_key, raw_value in raw_metrics.items():
                    num = coerce_float(raw_value)
                    if num is None:
                        continue
                    metrics[str(raw_key)] = num

        item = IndexedItem(
            path=logical_path,
            name=name,
            mime=mime,
            width=w,
            height=h,
            size=size,
            mtime=mtime or 0.0,
            url=source if is_http else None,
            source=source,
            metrics=metrics,
        )
        items[logical_path] = item
        source_paths[logical_path] = source
        row_dimensions[idx] = (w, h)
        row_to_path[idx] = logical_path
        path_to_row[logical_path] = idx

        folder = os.path.dirname(logical_path).replace("\\", "/")
        folder_norm = normalize_path(folder)
        folder_path = f"/{folder_norm}" if folder_norm else "/"
        indexes.setdefault(
            folder_norm,
            IndexedFolder(path=folder_path, generated_at=generated_at),
        ).items.append(item)

        parts = folder_norm.split("/") if folder_norm else []
        for depth in range(len(parts)):
            parent = "/".join(parts[:depth])
            child = parts[depth]
            dir_children.setdefault(parent, set()).add(child)

        if (is_s3 or is_http) and (w == 0 or h == 0) and not skip_indexing:
            remote_task_count += 1

    indexes.setdefault("", IndexedFolder(path="/", generated_at=generated_at))
    for parent, children in dir_children.items():
        folder_path = f"/{parent}" if parent else "/"
        folder = indexes.setdefault(parent, IndexedFolder(path=folder_path, generated_at=generated_at))
        folder.dirs = sorted(children)

    elapsed = time.perf_counter() - start
    result = FastBuildResult(
        row_count=row_count,
        items=items,
        indexes=indexes,
        source_paths=source_paths,
        row_dimensions=row_dimensions,
        row_to_path=row_to_path,
        path_to_row=path_to_row,
        skipped_local=skipped_local,
        remote_task_count=remote_task_count,
        elapsed_seconds=elapsed,
    )
    return result, _signature_from_fast(result)


def _run_baseline(
    *,
    table,
    root: str,
    source_column: str,
    path_column: str | None,
    allow_local: bool,
    skip_indexing: bool,
) -> BaselineResult:
    start = time.perf_counter()
    storage = TableStorage(
        table=table,
        root=root,
        source_column=source_column,
        path_column=path_column,
        skip_indexing=skip_indexing,
        allow_local=allow_local,
    )
    elapsed = time.perf_counter() - start
    return BaselineResult(
        row_count=storage._row_count,
        item_count=len(storage._items),
        folder_count=len(storage._indexes),
        elapsed_seconds=elapsed,
        signature=_signature_from_storage(storage),
    )


def _print_summary(
    *,
    fast_result: FastBuildResult,
    fast_signature: str,
    baseline: BaselineResult | None,
) -> dict[str, Any]:
    fast_speed = fast_result.row_count / max(fast_result.elapsed_seconds, 1e-9)
    print(f"[fast-index] table rows: {fast_result.row_count}")
    print(
        "[fast-index] fast scan+assemble: "
        f"{fast_result.elapsed_seconds:.3f}s ({fast_speed:.2f} img/s)"
    )
    print(
        "[fast-index] outputs: "
        f"items={len(fast_result.items)}, folders={len(fast_result.indexes)}, "
        f"row_mapped={len(fast_result.row_to_path)}, "
        f"skipped_local={fast_result.skipped_local}, "
        f"remote_tasks={fast_result.remote_task_count}"
    )
    print(f"[fast-index] fast signature: {fast_signature}")

    payload: dict[str, Any] = {
        "fast": {
            "row_count": fast_result.row_count,
            "item_count": len(fast_result.items),
            "folder_count": len(fast_result.indexes),
            "row_mapped_count": len(fast_result.row_to_path),
            "skipped_local": fast_result.skipped_local,
            "remote_task_count": fast_result.remote_task_count,
            "elapsed_seconds": fast_result.elapsed_seconds,
            "img_per_second": fast_speed,
            "signature": fast_signature,
        }
    }

    if baseline is None:
        return payload

    baseline_speed = baseline.row_count / max(baseline.elapsed_seconds, 1e-9)
    speedup = baseline.elapsed_seconds / max(fast_result.elapsed_seconds, 1e-9)
    matches = baseline.signature == fast_signature

    print(
        "[fast-index] baseline TableStorage: "
        f"{baseline.elapsed_seconds:.3f}s ({baseline_speed:.2f} img/s)"
    )
    print(f"[fast-index] baseline signature: {baseline.signature}")
    print(f"[fast-index] signature match: {matches}")
    print(f"[fast-index] speedup vs baseline: {speedup:.2f}x")

    payload["baseline"] = {
        "row_count": baseline.row_count,
        "item_count": baseline.item_count,
        "folder_count": baseline.folder_count,
        "elapsed_seconds": baseline.elapsed_seconds,
        "img_per_second": baseline_speed,
        "signature": baseline.signature,
    }
    payload["comparison"] = {
        "signature_match": matches,
        "speedup_factor": speedup,
    }
    return payload


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

    table = _load_table(parquet_path)
    fast_result, fast_signature = build_fast_indexes(
        table=table,
        root=root,
        source_column=args.source_column,
        path_column=args.path_column,
        allow_local=args.allow_local,
        skip_indexing=args.skip_indexing,
        strict_local_validation=args.strict_local_validation,
    )

    baseline_result: BaselineResult | None = None
    if args.compare_baseline:
        baseline_result = _run_baseline(
            table=table,
            root=root,
            source_column=args.source_column,
            path_column=args.path_column,
            allow_local=args.allow_local,
            skip_indexing=args.skip_indexing,
        )

    payload = _print_summary(
        fast_result=fast_result,
        fast_signature=fast_signature,
        baseline=baseline_result,
    )

    if args.output_json:
        output_path = Path(args.output_json).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[fast-index] Wrote JSON summary: {output_path}")

    if baseline_result is not None and baseline_result.signature != fast_signature:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
