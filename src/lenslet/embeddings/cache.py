from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING
from zipfile import BadZipFile

from ..atomic_write import atomic_write_path
from ..degraded import report_degraded_feature
from .dependencies import load_numpy
from .detect import EmbeddingSpec

if TYPE_CHECKING:
    import numpy as np

CACHE_VERSION = 1


class EmbeddingCacheError(ValueError):
    pass


def _numpy_or_none():
    try:
        return load_numpy()
    except ImportError:
        return None


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
        np = _numpy_or_none()
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
                    raise EmbeddingCacheError("cache missing matrix or row_indices")
                matrix = np.asarray(matrix, dtype=np.float32)
                row_indices = np.asarray(row_indices, dtype=np.int64)
            if matrix.ndim != 2 or row_indices.ndim != 1:
                raise EmbeddingCacheError("cache arrays have invalid dimensions")
            if matrix.shape[0] != row_indices.shape[0]:
                raise EmbeddingCacheError("cache matrix and row index lengths differ")
            if matrix.shape[1] != spec.dimension:
                raise EmbeddingCacheError("cache embedding dimension mismatch")
            if not np.isfinite(matrix).all():
                raise EmbeddingCacheError("cache matrix contains NaN or infinity")
        except (BadZipFile, EOFError, OSError, TypeError, ValueError) as exc:
            report_degraded_feature("embedding cache", exc, detail=f"failed to load cache: {exc}")
            return None
        return matrix, row_indices

    def save(
        self,
        parquet_path: str,
        spec: EmbeddingSpec,
        matrix: "np.ndarray",
        row_indices: "np.ndarray",
    ) -> None:
        np = _numpy_or_none()
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
        def _write(tmp_path: Path) -> None:
            np.savez_compressed(
                tmp_path,
                matrix=matrix,
                row_indices=row_indices,
                meta=np.array(json.dumps(meta)),
            )

        try:
            atomic_write_path(path, _write, suffix=".tmp.npz")
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
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
