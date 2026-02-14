from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from PIL import Image

from .storage.progress import ProgressBar
from .storage.table_facade import guess_mime
from .storage.table_media import read_dimensions_fast
from .storage.table_paths import normalize_item_path
from .workspace import Workspace

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
class PreindexResult:
    workspace: Workspace
    paths: PreindexPaths
    signature: str
    image_count: int
    format: str
    reused: bool


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
            return PreindexResult(
                workspace=effective_workspace,
                paths=paths,
                signature=signature,
                image_count=int(meta.get("image_count", len(entries))),
                format=str(meta.get("format", "parquet")),
                reused=True,
            )

    progress = progress or ProgressBar()
    rows = build_preindex_rows(entries, progress=progress)
    fmt = write_preindex(rows, paths)
    write_preindex_meta(
        paths.meta_path,
        signature=signature,
        image_count=len(rows),
        fmt=fmt,
        root=root,
    )
    return PreindexResult(
        workspace=effective_workspace,
        paths=paths,
        signature=signature,
        image_count=len(rows),
        format=fmt,
        reused=False,
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
            except OSError:
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
) -> list[dict]:
    total = len(entries)
    if total <= 0:
        return []

    progress.update(0, total, "preindex")
    rows: list[dict | None] = [None] * total
    workers = _effective_workers(total)

    if workers > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(_entry_to_row, idx, entry)
                for idx, entry in enumerate(entries)
            ]
            done = 0
            for future in as_completed(futures):
                idx, row = future.result()
                rows[idx] = row
                done += 1
                progress.update(done, total, "preindex")
    else:
        done = 0
        for idx, entry in enumerate(entries):
            _, row = _entry_to_row(idx, entry)
            rows[idx] = row
            done += 1
            progress.update(done, total, "preindex")

    return [row for row in rows if row is not None]


def write_preindex(rows: list[dict], paths: PreindexPaths) -> str:
    paths.root.mkdir(parents=True, exist_ok=True)
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except Exception:
        _write_json_atomic(paths.json_path, rows)
        return "json"

    table = pa.Table.from_pylist(rows)
    tmp = paths.parquet_path.with_suffix(".parquet.tmp")
    pq.write_table(table, str(tmp))
    tmp.replace(paths.parquet_path)
    return "parquet"


def write_preindex_meta(
    meta_path: Path,
    *,
    signature: str,
    image_count: int,
    fmt: str,
    root: Path,
) -> None:
    payload = {
        "version": PREINDEX_SCHEMA_VERSION,
        "signature": signature,
        "image_count": int(image_count),
        "format": fmt,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(root.resolve()),
        "columns": list(PREINDEX_COLUMNS),
    }
    _write_json_atomic(meta_path, payload)


def load_preindex_meta(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if int(data.get("version", 0)) != PREINDEX_SCHEMA_VERSION:
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
    from .storage.table import load_parquet_table

    return load_parquet_table(str(path))


def _load_json_rows(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError("preindex json must be a list of row objects")
    return data


def _entry_to_row(idx: int, entry: LocalImageEntry) -> tuple[int, dict]:
    width, height = _probe_dimensions(entry.abs_path)
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
    return idx, row


def _probe_dimensions(path: Path) -> tuple[int, int]:
    dims = read_dimensions_fast(str(path))
    if dims:
        return dims
    try:
        with Image.open(path) as im:
            w, h = im.size
            return int(w), int(h)
    except Exception:
        return 0, 0


def _meta_signature_matches(meta: dict, signature: str) -> bool:
    try:
        return str(meta.get("signature", "")) == signature
    except Exception:
        return False


def _preindex_payload_exists(paths: PreindexPaths, meta: dict) -> bool:
    fmt = str(meta.get("format", "parquet"))
    if fmt == "json":
        return paths.json_path.is_file()
    if fmt == "parquet":
        return paths.parquet_path.is_file()
    return paths.parquet_path.is_file() or paths.json_path.is_file()


def _resolve_preindex_workspace(root: Path, workspace: Workspace, signature: str) -> Workspace:
    if workspace.can_write:
        try:
            workspace.ensure()
            return workspace
        except Exception:
            workspace.can_write = False

    temp_root = Workspace.TEMP_ROOT / signature
    temp_workspace = Workspace(root=temp_root, can_write=True, is_temp=True)
    temp_workspace.ensure()
    return temp_workspace


def _write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


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
