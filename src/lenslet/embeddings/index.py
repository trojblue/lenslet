from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional dependency until embeddings are used
    np = None  # type: ignore[assignment]

from .detect import EmbeddingSpec
from .io import EmbeddingIOError, decode_base64_vector, load_embedding_matrix, normalize_vector


class EmbeddingIndexError(ValueError):
    pass


@dataclass(frozen=True)
class EmbeddingMatch:
    row_index: int
    path: str
    score: float


class EmbeddingIndex:
    def __init__(
        self,
        parquet_path: str,
        spec: EmbeddingSpec,
        row_to_path: dict[int, str],
    ) -> None:
        if np is None:  # pragma: no cover - optional dependency
            raise EmbeddingIndexError("numpy is required for embedding search")
        if spec.metric != "cosine":
            raise EmbeddingIndexError(f"Unsupported embedding metric '{spec.metric}'")
        matrix, dtype = load_embedding_matrix(parquet_path, spec.name)
        if matrix.ndim != 2:
            raise EmbeddingIndexError("embedding matrix must be 2D")
        if matrix.shape[1] != spec.dimension:
            raise EmbeddingIndexError("embedding dimension mismatch")
        if not np.isfinite(matrix).all():
            raise EmbeddingIndexError("embedding matrix contains NaN or infinity")

        norms = np.linalg.norm(matrix, axis=1)
        valid_rows = _valid_row_indices(norms, row_to_path)
        if not valid_rows:
            raise EmbeddingIndexError("embedding matrix has no valid rows")
        row_indices_list = sorted(valid_rows)
        row_indices = np.array(row_indices_list, dtype=np.int64)
        matrix = matrix[row_indices]
        norms = norms[row_indices]
        matrix = matrix / norms[:, None]

        self.name = spec.name
        self.metric = spec.metric
        self.dimension = spec.dimension
        self.dtype = dtype
        self._matrix = matrix.astype(np.float32, copy=False)
        self._row_indices = row_indices
        self._row_index_to_pos = {row: idx for idx, row in enumerate(row_indices_list)}
        self._paths = [row_to_path[row] for row in row_indices_list]

    def search_by_vector(
        self,
        vector: np.ndarray,
        top_k: int,
        min_score: float | None = None,
        normalized: bool = False,
    ) -> list[EmbeddingMatch]:
        if np is None:  # pragma: no cover - optional dependency
            raise EmbeddingIndexError("numpy is required for embedding search")
        if vector.size != self.dimension:
            raise EmbeddingIndexError("query vector dimension mismatch")
        vec = vector.astype(np.float32, copy=False)
        if not np.isfinite(vec).all():
            raise EmbeddingIndexError("query vector contains NaN or infinity")
        if not normalized:
            vec = normalize_vector(vec)
        scores = self._matrix @ vec
        return _top_k_matches(scores, self._row_indices, self._paths, top_k, min_score)

    def search_by_row_index(
        self,
        row_index: int,
        top_k: int,
        min_score: float | None = None,
    ) -> list[EmbeddingMatch]:
        pos = self._row_index_to_pos.get(int(row_index))
        if pos is None:
            raise EmbeddingIndexError("query path has no embedding vector")
        vector = self._matrix[pos]
        return self.search_by_vector(vector, top_k=top_k, min_score=min_score, normalized=True)


class EmbeddingManager:
    def __init__(
        self,
        parquet_path: str,
        detection: Iterable[EmbeddingSpec],
        rejected: Iterable,
        row_to_path: dict[int, str],
    ) -> None:
        self.parquet_path = parquet_path
        self._specs = {spec.name: spec for spec in detection}
        self._rejected = list(rejected)
        self._row_to_path = row_to_path
        self._indexes: dict[str, EmbeddingIndex] = {}

    @property
    def available(self) -> list[EmbeddingSpec]:
        return list(self._specs.values())

    @property
    def rejected(self) -> list:
        return list(self._rejected)

    def get_spec(self, name: str) -> EmbeddingSpec | None:
        return self._specs.get(name)

    def index_for(self, name: str) -> EmbeddingIndex:
        spec = self._specs.get(name)
        if spec is None:
            raise EmbeddingIndexError("embedding not found")
        if name not in self._indexes:
            try:
                self._indexes[name] = EmbeddingIndex(self.parquet_path, spec, self._row_to_path)
            except EmbeddingIOError as exc:
                raise EmbeddingIndexError(str(exc)) from exc
        return self._indexes[name]

    def search_by_path(
        self,
        name: str,
        row_index: int,
        top_k: int,
        min_score: float | None,
    ) -> list[EmbeddingMatch]:
        index = self.index_for(name)
        return index.search_by_row_index(row_index=row_index, top_k=top_k, min_score=min_score)

    def search_by_vector(
        self,
        name: str,
        vector_b64: str,
        top_k: int,
        min_score: float | None,
    ) -> list[EmbeddingMatch]:
        index = self.index_for(name)
        try:
            vector = decode_base64_vector(vector_b64, index.dimension)
        except EmbeddingIOError as exc:
            raise EmbeddingIndexError(str(exc)) from exc
        return index.search_by_vector(vector, top_k=top_k, min_score=min_score)


def _valid_row_indices(norms: "np.ndarray", row_to_path: dict[int, str]) -> list[int]:
    if np is None:  # pragma: no cover - optional dependency
        return []
    valid: list[int] = []
    for row_index in row_to_path:
        if row_index < 0 or row_index >= norms.shape[0]:
            continue
        norm = norms[row_index]
        if not np.isfinite(norm) or norm == 0.0:
            continue
        valid.append(int(row_index))
    return valid


def _top_k_matches(
    scores: "np.ndarray",
    row_indices: "np.ndarray",
    paths: list[str],
    top_k: int,
    min_score: float | None,
) -> list[EmbeddingMatch]:
    if np is None:  # pragma: no cover - optional dependency
        return []
    total = scores.shape[0]
    if total == 0 or top_k <= 0:
        return []
    k = min(top_k, total)
    if k == total:
        candidates = np.argsort(scores)[::-1]
    else:
        idx = np.argpartition(scores, -k)[-k:]
        candidates = idx[np.argsort(scores[idx])[::-1]]
    results: list[EmbeddingMatch] = []
    for pos in candidates:
        score = float(scores[pos])
        if min_score is not None and score < min_score:
            continue
        results.append(
            EmbeddingMatch(
                row_index=int(row_indices[pos]),
                path=paths[pos],
                score=score,
            )
        )
    return results
