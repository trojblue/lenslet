from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

PYARROW_REQUIRED = "pyarrow is required for Parquet datasets. Install with: pip install pyarrow"


@dataclass(frozen=True, slots=True)
class PyArrowRuntime:
    pyarrow: Any
    parquet: Any
    arrow_errors: tuple[type[BaseException], ...]


@lru_cache(maxsize=1)
def load_pyarrow_runtime() -> PyArrowRuntime:
    try:
        import pyarrow as pyarrow
        import pyarrow.parquet as parquet
        from pyarrow.lib import ArrowException
    except ImportError as exc:  # pragma: no cover - pyarrow is a project dependency
        raise ImportError(PYARROW_REQUIRED) from exc
    return PyArrowRuntime(
        pyarrow=pyarrow,
        parquet=parquet,
        arrow_errors=(ArrowException,),
    )


def require_pyarrow() -> tuple[Any, Any]:
    runtime = load_pyarrow_runtime()
    return runtime.pyarrow, runtime.parquet


def require_pyarrow_parquet() -> Any:
    return load_pyarrow_runtime().parquet


def pyarrow_exception_types() -> tuple[type[BaseException], ...]:
    try:
        return load_pyarrow_runtime().arrow_errors
    except ImportError:
        return ()
