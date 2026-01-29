from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

try:
    import numpy as np
except ImportError:  # pragma: no cover - optional dependency until embeddings are used
    np = None  # type: ignore[assignment]
try:
    import faiss  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    faiss = None  # type: ignore[assignment]

from .detect import EmbeddingSpec
from .cache import EmbeddingCache
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
        cache: EmbeddingCache | None = None,
        prefer_faiss: bool = True,
    ) -> None:
        if np is None:  # pragma: no cover - optional dependency
            raise EmbeddingIndexError("numpy is required for embedding search")
        if spec.metric != "cosine":
            raise EmbeddingIndexError(f"Unsupported embedding metric '{spec.metric}'")
        matrix, row_indices, dtype = _load_embedding_data(
            parquet_path=parquet_path,
            spec=spec,
            row_to_path=row_to_path,
            cache=cache,
        )

        self.name = spec.name
        self.metric = spec.metric
        self.dimension = spec.dimension
        self.dtype = dtype
        self._matrix = matrix.astype(np.float32, copy=False)
        self._row_indices = row_indices
        row_indices_list = [int(row) for row in row_indices.tolist()]
        self._row_index_to_pos = {row: idx for idx, row in enumerate(row_indices_list)}
        self._paths = [row_to_path[row] for row in row_indices_list]
        self._faiss_index = _build_faiss_index(self._matrix, prefer_faiss=prefer_faiss)

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
        if self._faiss_index is not None:
            return _search_faiss(self._faiss_index, vec, self._row_indices, self._paths, top_k, min_score)
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
        cache: EmbeddingCache | None = None,
        prefer_faiss: bool = True,
    ) -> None:
        self.parquet_path = parquet_path
        self._specs = {spec.name: spec for spec in detection}
        self._rejected = list(rejected)
        self._row_to_path = row_to_path
        self._cache = cache
        self._prefer_faiss = prefer_faiss
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
                self._indexes[name] = EmbeddingIndex(
                    self.parquet_path,
                    spec,
                    self._row_to_path,
                    cache=self._cache,
                    prefer_faiss=self._prefer_faiss,
                )
            except EmbeddingIOError as exc:
                raise EmbeddingIndexError(str(exc)) from exc
        return self._indexes[name]

    def preload(self) -> None:
        for name in self._specs:
            try:
                _ = self.index_for(name)
            except EmbeddingIndexError as exc:
                print(f"[lenslet] Warning: failed to preload embedding '{name}': {exc}")

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


def _load_embedding_data(
    parquet_path: str,
    spec: EmbeddingSpec,
    row_to_path: dict[int, str],
    cache: EmbeddingCache | None,
) -> tuple["np.ndarray", "np.ndarray", str]:
    if np is None:  # pragma: no cover - optional dependency
        raise EmbeddingIndexError("numpy is required for embedding search")
    if cache is not None:
        cached = cache.load(parquet_path, spec)
        if cached is not None:
            matrix, row_indices = cached
            try:
                matrix, row_indices = _filter_cached_rows(matrix, row_indices, row_to_path)
                return matrix, row_indices, spec.dtype
            except EmbeddingIndexError as exc:
                print(f"[lenslet] Warning: invalid embedding cache: {exc}")

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
    matrix = matrix.astype(np.float32, copy=False)
    if cache is not None:
        try:
            cache.save(parquet_path, spec, matrix, row_indices)
        except Exception as exc:
            print(f"[lenslet] Warning: failed to write embedding cache: {exc}")
    return matrix, row_indices, dtype


def _filter_cached_rows(
    matrix: "np.ndarray",
    row_indices: "np.ndarray",
    row_to_path: dict[int, str],
) -> tuple["np.ndarray", "np.ndarray"]:
    if np is None:  # pragma: no cover - optional dependency
        raise EmbeddingIndexError("numpy is required for embedding search")
    if matrix.ndim != 2:
        raise EmbeddingIndexError("embedding matrix must be 2D")
    if row_indices.ndim != 1:
        raise EmbeddingIndexError("embedding index cache is invalid")
    if matrix.shape[0] != row_indices.shape[0]:
        raise EmbeddingIndexError("embedding index cache is invalid")
    if not np.isfinite(matrix).all():
        raise EmbeddingIndexError("embedding matrix contains NaN or infinity")
    keep_positions: list[int] = []
    for pos, row in enumerate(row_indices.tolist()):
        if int(row) in row_to_path:
            keep_positions.append(pos)
    if not keep_positions:
        raise EmbeddingIndexError("embedding matrix has no valid rows")
    if len(keep_positions) != row_indices.shape[0]:
        matrix = matrix[keep_positions]
        row_indices = row_indices[keep_positions]
    return matrix, row_indices


def _build_faiss_index(matrix: "np.ndarray", prefer_faiss: bool) -> "faiss.Index | None":
    if not prefer_faiss or faiss is None:  # pragma: no cover - optional dependency
        return None
    try:
        matrix = np.ascontiguousarray(matrix, dtype=np.float32)
        index = faiss.IndexFlatIP(matrix.shape[1])
        index.add(matrix)
        return index
    except Exception as exc:  # pragma: no cover - optional dependency
        print(f"[lenslet] Warning: failed to build FAISS index: {exc}")
        return None


def _search_faiss(
    index: "faiss.Index",
    vec: "np.ndarray",
    row_indices: "np.ndarray",
    paths: list[str],
    top_k: int,
    min_score: float | None,
) -> list[EmbeddingMatch]:
    if np is None:  # pragma: no cover - optional dependency
        return []
    total = row_indices.shape[0]
    if total == 0 or top_k <= 0:
        return []
    k = min(top_k, total)
    query = np.ascontiguousarray(vec.reshape(1, -1), dtype=np.float32)
    scores, idxs = index.search(query, k)
    scores = scores.reshape(-1)
    idxs = idxs.reshape(-1)
    results: list[EmbeddingMatch] = []
    for score, pos in zip(scores, idxs):
        if pos < 0:
            continue
        score_val = float(score)
        if min_score is not None and score_val < min_score:
            continue
        results.append(
            EmbeddingMatch(
                row_index=int(row_indices[pos]),
                path=paths[pos],
                score=score_val,
            )
        )
    return results


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
