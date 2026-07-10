from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, TypeAlias

import pyarrow as pa
import pyarrow.parquet as pq
from PIL import Image

from ...atomic_write import atomic_write_json, atomic_write_path
from ...workspace import Workspace
from ..image_media import read_dimensions_fast
from ..progress import ProgressBar
from ..source.backed import guess_mime
from ..source.paths import normalize_item_path
from ..table.storage import load_parquet_table as load_table_parquet

PREINDEX_SCHEMA_VERSION = 1
PREINDEX_PATH_COLUMN = "path"
PREINDEX_SOURCE_COLUMN = "source"
PREINDEX_COLUMNS = (
    PREINDEX_PATH_COLUMN,
    PREINDEX_SOURCE_COLUMN,
    "name",
    "mime",
    "width",
    "height",
    "size",
    "mtime",
)

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
INDEX_WORKERS = 16
INDEX_PARALLEL_MIN_IMAGES = 24
_PREINDEX_META_READ_ERRORS = (OSError, json.JSONDecodeError, TypeError, ValueError)
_IMAGE_PROBE_ERRORS = (Image.DecompressionBombError, OSError, SyntaxError, TypeError, ValueError)
PREINDEX_SKIP_EXAMPLE_LIMIT = 5
PreindexRow: TypeAlias = dict[str, int | float | str]
PreindexMeta: TypeAlias = dict[str, Any]


@dataclass(frozen=True)
class LocalImageEntry:
    rel_path: str
    abs_path: Path
    name: str
    size: int
    mtime: float
    mtime_ns: int


@dataclass(frozen=True)
class PreindexPaths:
    root: Path
    parquet_path: Path
    json_path: Path
    meta_path: Path


@dataclass(frozen=True)
class PreindexSkippedImage:
    path: str
    reason: str


@dataclass(frozen=True)
class PreindexBuildResult:
    rows: list[PreindexRow]
    skipped: tuple[PreindexSkippedImage, ...]


@dataclass(frozen=True)
class PreindexResult:
    workspace: Workspace
    paths: PreindexPaths
    signature: str
    image_count: int
    format: str
    reused: bool
    skipped_image_count: int = 0
    skipped_image_examples: tuple[PreindexSkippedImage, ...] = ()


def preindex_paths(workspace: Workspace) -> PreindexPaths | None:
    root = workspace.preindex_dir()
    if root is None:
        return None
    return PreindexPaths(
        root=root,
        parquet_path=root / "items.parquet",
        json_path=root / "items.json",
        meta_path=root / "meta.json",
    )


def ensure_local_preindex(
    root: Path,
    workspace: Workspace,
    *,
    progress: ProgressBar | None = None,
) -> PreindexResult | None:
    print("[lenslet] Scanning files...", flush=True)
    entries = scan_local_images(root)
    if not entries:
        return None

    entries.sort(key=lambda entry: entry.rel_path)
    signature = compute_signature(root, entries)
    effective_workspace = _resolve_preindex_workspace(root, workspace, signature)
    paths = preindex_paths(effective_workspace)
    if paths is None:
        return None

    meta = load_preindex_meta(paths.meta_path)
    if meta and _meta_signature_matches(meta, signature):
        if _preindex_payload_exists(paths, meta):
            skipped_image_count, skipped_image_examples = _preindex_skips_from_meta(meta)
            _print_preindex_skip_summary(skipped_image_count, skipped_image_examples)
            return PreindexResult(
                workspace=effective_workspace,
                paths=paths,
                signature=signature,
                image_count=int(meta.get("image_count", len(entries))),
                format=str(meta.get("format", "parquet")),
                reused=True,
                skipped_image_count=skipped_image_count,
                skipped_image_examples=skipped_image_examples,
            )

    progress = progress or ProgressBar()
    build = build_preindex_rows(entries, progress=progress)
    _print_preindex_skip_summary(len(build.skipped), build.skipped)
    if not build.rows:
        return None

    fmt = write_preindex(build.rows, paths)
    write_preindex_meta(
        paths.meta_path,
        signature=signature,
        image_count=len(build.rows),
        fmt=fmt,
        root=root,
        skipped_images=build.skipped,
    )
    return PreindexResult(
        workspace=effective_workspace,
        paths=paths,
        signature=signature,
        image_count=len(build.rows),
        format=fmt,
        reused=False,
        skipped_image_count=len(build.skipped),
        skipped_image_examples=build.skipped[:PREINDEX_SKIP_EXAMPLE_LIMIT],
    )


def scan_local_images(root: Path) -> list[LocalImageEntry]:
    root = root.resolve()
    entries: list[LocalImageEntry] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _should_skip_dir(d)]
        for name in filenames:
            if _should_skip_file(name):
                continue
            if not _is_supported_image(name):
                continue
            abs_path = Path(dirpath) / name
            try:
                stat = abs_path.stat()
            except OSError as exc:
                print(f"[lenslet] Warning: skipped unreadable image during preindex scan: {abs_path}: {exc}")
                continue
            rel_path = os.path.relpath(abs_path, root)
            rel_path = normalize_item_path(rel_path)
            if not rel_path:
                continue
            entries.append(
                LocalImageEntry(
                    rel_path=rel_path,
                    abs_path=abs_path,
                    name=name,
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                    mtime_ns=getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1e9)),
                )
            )
    return entries


def compute_signature(root: Path, entries: Iterable[LocalImageEntry]) -> str:
    digest = hashlib.sha256()
    digest.update(str(root.resolve()).encode("utf-8"))
    for entry in entries:
        digest.update(entry.rel_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(entry.size).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(entry.mtime_ns).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def build_preindex_rows(
    entries: list[LocalImageEntry],
    *,
    progress: ProgressBar,
) -> PreindexBuildResult:
    total = len(entries)
    if total <= 0:
        return PreindexBuildResult(rows=[], skipped=())

    progress.update(0, total, "preindex")
    rows: list[PreindexRow | None] = [None] * total
    skipped: list[PreindexSkippedImage | None] = [None] * total
    workers = _effective_workers(total)

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(_entry_to_row, idx, entry)
                for idx, entry in enumerate(entries)
            ]
            done = 0
            for future in as_completed(futures):
                idx, row, skip = future.result()
                rows[idx] = row
                skipped[idx] = skip
                done += 1
                progress.update(done, total, "preindex")
    else:
        done = 0
        for idx, entry in enumerate(entries):
            _, row, skip = _entry_to_row(idx, entry)
            rows[idx] = row
            skipped[idx] = skip
            done += 1
            progress.update(done, total, "preindex")

    return PreindexBuildResult(
        rows=[row for row in rows if row is not None],
        skipped=tuple(skip for skip in skipped if skip is not None),
    )


def write_preindex(rows: list[PreindexRow], paths: PreindexPaths) -> str:
    paths.root.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows)
    atomic_write_path(
        paths.parquet_path,
        lambda tmp_path: pq.write_table(table, str(tmp_path)),
        suffix=".parquet.tmp",
    )
    return "parquet"


def write_preindex_meta(
    meta_path: Path,
    *,
    signature: str,
    image_count: int,
    fmt: str,
    root: Path,
    skipped_images: tuple[PreindexSkippedImage, ...] = (),
) -> None:
    payload: PreindexMeta = {
        "version": PREINDEX_SCHEMA_VERSION,
        "signature": signature,
        "image_count": int(image_count),
        "format": fmt,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root.resolve()),
        "columns": list(PREINDEX_COLUMNS),
        "skipped_image_count": len(skipped_images),
        "skipped_image_examples": [
            {"path": skipped.path, "reason": skipped.reason}
            for skipped in skipped_images[:PREINDEX_SKIP_EXAMPLE_LIMIT]
        ],
    }
    atomic_write_json(meta_path, payload, indent=2, sort_keys=True)


def load_preindex_meta(path: Path) -> PreindexMeta | None:
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        version = int(data.get("version", 0))
    except _PREINDEX_META_READ_ERRORS:
        return None
    if version != PREINDEX_SCHEMA_VERSION:
        return None
    return data


def load_preindex_table(paths: PreindexPaths) -> tuple[object, str]:
    meta = load_preindex_meta(paths.meta_path)
    fmt = str(meta.get("format")) if meta else ""
    if fmt == "json" and paths.json_path.is_file():
        return _load_json_rows(paths.json_path), "json"
    if fmt == "parquet" and paths.parquet_path.is_file():
        return _load_parquet_table(paths.parquet_path), "parquet"

    if paths.parquet_path.is_file():
        return _load_parquet_table(paths.parquet_path), "parquet"
    if paths.json_path.is_file():
        return _load_json_rows(paths.json_path), "json"
    raise FileNotFoundError("preindex table missing")


def _load_parquet_table(path: Path):
    return load_table_parquet(str(path))


def _load_json_rows(path: Path) -> list[PreindexRow]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("preindex json must be a list of row objects")
    if not all(isinstance(row, dict) for row in data):
        raise ValueError("preindex json rows must be objects")
    return [dict(row) for row in data]


def _entry_to_row(
    idx: int,
    entry: LocalImageEntry,
) -> tuple[int, PreindexRow | None, PreindexSkippedImage | None]:
    dimensions, reason = _probe_dimensions(entry.abs_path)
    if dimensions is None:
        return idx, None, PreindexSkippedImage(
            path=entry.rel_path,
            reason=reason or "could not read image dimensions",
        )
    width, height = dimensions
    if width <= 0 or height <= 0:
        return idx, None, PreindexSkippedImage(
            path=entry.rel_path,
            reason="could not read image dimensions",
        )
    row = {
        PREINDEX_PATH_COLUMN: entry.rel_path,
        PREINDEX_SOURCE_COLUMN: entry.rel_path,
        "name": entry.name,
        "mime": guess_mime(entry.name),
        "width": int(width),
        "height": int(height),
        "size": int(entry.size),
        "mtime": float(entry.mtime),
    }
    return idx, row, None


def _probe_dimensions(path: Path) -> tuple[tuple[int, int] | None, str | None]:
    fast_error: str | None = None
    try:
        dims = read_dimensions_fast(str(path))
    except _IMAGE_PROBE_ERRORS as exc:
        fast_error = _format_probe_error(exc)
    else:
        if dims and dims[0] > 0 and dims[1] > 0:
            return dims, None
    try:
        with Image.open(path) as im:
            w, h = im.size
            if w > 0 and h > 0:
                return (int(w), int(h)), None
    except _IMAGE_PROBE_ERRORS as exc:
        return None, _format_probe_error(exc) or fast_error
    return None, fast_error or "could not read image dimensions"


def _format_probe_error(exc: BaseException) -> str:
    detail = str(exc).strip()
    return detail or exc.__class__.__name__


def _meta_signature_matches(meta: PreindexMeta, signature: str) -> bool:
    return str(meta.get("signature", "")) == signature


def _preindex_payload_exists(paths: PreindexPaths, meta: PreindexMeta) -> bool:
    fmt = str(meta.get("format", "parquet"))
    if fmt == "json":
        return paths.json_path.is_file()
    if fmt == "parquet":
        return paths.parquet_path.is_file()
    return paths.parquet_path.is_file() or paths.json_path.is_file()


def _preindex_skips_from_meta(meta: PreindexMeta) -> tuple[int, tuple[PreindexSkippedImage, ...]]:
    try:
        skipped_image_count = int(meta.get("skipped_image_count", 0))
    except (TypeError, ValueError):
        skipped_image_count = 0
    examples: list[PreindexSkippedImage] = []
    raw_examples = meta.get("skipped_image_examples", [])
    if isinstance(raw_examples, list):
        for raw in raw_examples[:PREINDEX_SKIP_EXAMPLE_LIMIT]:
            if not isinstance(raw, dict):
                continue
            path = str(raw.get("path", "")).strip()
            if not path:
                continue
            reason = str(raw.get("reason", "")).strip()
            examples.append(PreindexSkippedImage(path=path, reason=reason))
    return max(0, skipped_image_count), tuple(examples)


def _print_preindex_skip_summary(
    skipped_image_count: int,
    skipped_image_examples: tuple[PreindexSkippedImage, ...],
) -> None:
    if skipped_image_count <= 0:
        return
    examples = skipped_image_examples[:PREINDEX_SKIP_EXAMPLE_LIMIT]
    print(f"[lenslet] Preindex skipped {skipped_image_count} unreadable/corrupt image(s).")
    for skipped in examples:
        detail = f": {skipped.reason}" if skipped.reason else ""
        print(f"[lenslet]   - {skipped.path}{detail}")
    remaining = skipped_image_count - len(examples)
    if remaining > 0:
        print(f"[lenslet]   ... {remaining} more")


def _resolve_preindex_workspace(root: Path, workspace: Workspace, signature: str) -> Workspace:
    if workspace.can_write:
        workspace.ensure()
        return workspace

    temp_root = Workspace.temp_root() / signature
    temp_workspace = Workspace(root=temp_root, can_write=True, is_temp=True)
    temp_workspace.ensure()
    return temp_workspace


def _effective_workers(total: int) -> int:
    if total < INDEX_PARALLEL_MIN_IMAGES:
        return 1
    cpu = os.cpu_count() or 1
    return max(1, min(INDEX_WORKERS, cpu, total))


def _is_supported_image(name: str) -> bool:
    return name.lower().endswith(IMAGE_EXTS)


def _should_skip_dir(name: str) -> bool:
    return name.startswith(".") or name.startswith("_")


def _should_skip_file(name: str) -> bool:
    return name.startswith((".", "_"))
