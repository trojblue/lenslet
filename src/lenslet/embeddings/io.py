from __future__ import annotations

import base64
import binascii
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np
    import pyarrow as pa

from .dependencies import load_numpy, load_pyarrow, load_pyarrow_parquet


class EmbeddingIOError(ValueError):
    pass


def _require_numpy() -> Any:
    try:
        return load_numpy()
    except ImportError as exc:  # pragma: no cover - optional embeddings dependency
        raise EmbeddingIOError("numpy is required for embedding search") from exc


def _require_pyarrow() -> tuple[Any, Any]:
    try:
        return load_pyarrow(), load_pyarrow_parquet()
    except ImportError as exc:  # pragma: no cover - pyarrow is a project dependency
        raise EmbeddingIOError("pyarrow is required for embedding search") from exc


def _fixed_size_list_array(column: "pa.Array | pa.ChunkedArray", pyarrow: Any) -> "pa.Array":
    array = column
    if isinstance(array, pyarrow.ChunkedArray):
        array = array.combine_chunks()
    if not pyarrow.types.is_fixed_size_list(array.type):
        raise EmbeddingIOError("embedding column must be a fixed-size list")
    return array


def load_embedding_matrix(parquet_path: str, column: str) -> tuple["np.ndarray", str]:
    np = _require_numpy()
    pyarrow, parquet = _require_pyarrow()
    table = parquet.read_table(parquet_path, columns=[column])
    if column not in table.column_names:
        raise EmbeddingIOError(f"embedding column '{column}' not found")
    array = _fixed_size_list_array(table[column], pyarrow)
    if array.null_count:
        raise EmbeddingIOError("embedding column contains null rows")
    values = array.values
    if values.null_count:
        raise EmbeddingIOError("embedding column contains null values")
    try:
        np_values = values.to_numpy(zero_copy_only=False)
    except Exception as exc:
        raise EmbeddingIOError(f"failed to convert embedding column to numpy: {exc}") from exc
    dim = array.type.list_size
    expected = len(array) * dim
    if np_values.size != expected:
        raise EmbeddingIOError("embedding column length mismatch")
    matrix = np_values.reshape((len(array), dim))
    return np.asarray(matrix, dtype=np.float32), str(values.type)


def decode_base64_vector(encoded: str, dimension: int) -> "np.ndarray":
    np = _require_numpy()
    if not encoded:
        raise EmbeddingIOError("query.vector_b64 is required")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except binascii.Error as exc:
        raise EmbeddingIOError("invalid base64 for query.vector_b64") from exc
    expected_bytes = dimension * 4
    if len(raw) != expected_bytes:
        raise EmbeddingIOError(
            f"query.vector_b64 length mismatch (expected {expected_bytes} bytes for dim {dimension})"
        )
    vec = np.frombuffer(raw, dtype="<f4")
    if vec.size != dimension:
        raise EmbeddingIOError("query.vector_b64 dimension mismatch")
    vec = vec.astype(np.float32, copy=False)
    if not np.isfinite(vec).all():
        raise EmbeddingIOError("query vector contains NaN or infinity")
    norm = float(np.linalg.norm(vec))
    if norm == 0.0 or not np.isfinite(norm):
        raise EmbeddingIOError("query vector has zero magnitude")
    return vec


def normalize_vector(vec: "np.ndarray") -> "np.ndarray":
    np = _require_numpy()
    norm = float(np.linalg.norm(vec))
    if norm == 0.0 or not np.isfinite(norm):
        raise EmbeddingIOError("vector has zero magnitude")
    return vec / norm
