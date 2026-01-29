from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional dependency until embeddings are used
    np = None  # type: ignore[assignment]

from .detect import EmbeddingSpec

CACHE_VERSION = 1


class EmbeddingCacheError(ValueError):
    pass


@dataclass(frozen=True)
class EmbeddingCache:
    root: Path
    allow_write: bool = True

    def cache_path(self, parquet_path: str, spec: EmbeddingSpec) -> Path | None:
        key = _cache_key(parquet_path, spec)
        if key is None:
            return None
        return self.root / f"{key}.npz"

    def load(self, parquet_path: str, spec: EmbeddingSpec) -> tuple["np.ndarray", "np.ndarray"] | None:
        if np is None:  # pragma: no cover - optional dependency
            return None
        path = self.cache_path(parquet_path, spec)
        if path is None or not path.exists():
            return None
        try:
            with np.load(path, allow_pickle=False) as data:
                matrix = data.get("matrix")
                row_indices = data.get("row_indices")
                if matrix is None or row_indices is None:
                    return None
                matrix = np.asarray(matrix, dtype=np.float32)
                row_indices = np.asarray(row_indices, dtype=np.int64)
        except Exception:
            return None
        if matrix.ndim != 2 or row_indices.ndim != 1:
            return None
        if matrix.shape[0] != row_indices.shape[0]:
            return None
        if matrix.shape[1] != spec.dimension:
            return None
        if not np.isfinite(matrix).all():
            return None
        return matrix, row_indices

    def save(
        self,
        parquet_path: str,
        spec: EmbeddingSpec,
        matrix: "np.ndarray",
        row_indices: "np.ndarray",
    ) -> None:
        if np is None or not self.allow_write:  # pragma: no cover - optional dependency
            return
        path = self.cache_path(parquet_path, spec)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "version": CACHE_VERSION,
            "column": spec.name,
            "dimension": spec.dimension,
            "dtype": spec.dtype,
            "metric": spec.metric,
        }
        temp = path.with_suffix(".tmp.npz")
        np.savez_compressed(
            temp,
            matrix=matrix,
            row_indices=row_indices,
            meta=np.array(json.dumps(meta)),
        )
        try:
            temp.replace(path)
        except Exception as exc:
            raise EmbeddingCacheError(f"failed to write embedding cache: {exc}") from exc


def _cache_key(parquet_path: str, spec: EmbeddingSpec) -> str | None:
    try:
        stat = os.stat(parquet_path)
    except OSError:
        return None
    payload = {
        "path": str(Path(parquet_path).resolve()),
        "column": spec.name,
        "dimension": spec.dimension,
        "dtype": spec.dtype,
        "metric": spec.metric,
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
        "version": CACHE_VERSION,
    }
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
