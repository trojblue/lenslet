from __future__ import annotations

from functools import lru_cache
from typing import Any

NUMPY_REQUIRED = "numpy is required for embedding search"
PYARROW_REQUIRED = "pyarrow is required for embedding search"


@lru_cache(maxsize=1)
def load_numpy() -> Any:
    try:
        import numpy as numpy
    except ImportError as exc:  # pragma: no cover - optional embeddings dependency
        raise ImportError(NUMPY_REQUIRED) from exc
    return numpy


@lru_cache(maxsize=1)
def load_faiss() -> Any | None:
    try:
        import faiss
    except ImportError:  # pragma: no cover - optional accelerator
        return None
    return faiss


@lru_cache(maxsize=1)
def load_pyarrow() -> Any:
    try:
        import pyarrow as pyarrow
    except ImportError as exc:  # pragma: no cover - pyarrow is a project dependency
        raise ImportError(PYARROW_REQUIRED) from exc
    return pyarrow


@lru_cache(maxsize=1)
def load_pyarrow_parquet() -> Any:
    try:
        import pyarrow.parquet as parquet
    except ImportError as exc:  # pragma: no cover - pyarrow is a project dependency
        raise ImportError(PYARROW_REQUIRED) from exc
    return parquet
