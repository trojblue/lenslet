from pathlib import Path
import base64

import pytest
import pyarrow as pa
import pyarrow.parquet as pq
from PIL import Image

from lenslet.embeddings.cache import EmbeddingCache
from lenslet.embeddings.config import EmbeddingConfig
from lenslet.embeddings.detect import detect_embeddings
from lenslet.embeddings.index import EmbeddingManager
from lenslet.storage.table import TableStorage
from lenslet.workspace import Workspace

np = pytest.importorskip("numpy")


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 6), color=(20, 40, 60)).save(path, format="JPEG")


def _write_parquet(path: Path, table: pa.Table) -> None:
    pq.write_table(table, path)


def _encode_vec(vec) -> str:
    arr = np.asarray(vec, dtype="<f4")
    return base64.b64encode(arr.tobytes()).decode("ascii")


def _make_table(paths: list[str], embeds: list[list[float]]) -> pa.Table:
    embed_type = pa.list_(pa.float32(), len(embeds[0]))
    embed_array = pa.array(embeds, type=embed_type)
    return pa.Table.from_arrays([pa.array(paths), embed_array], names=["path", "clip"])


def _build_manager(root: Path, table: pa.Table, cache: EmbeddingCache) -> tuple[EmbeddingManager, str]:
    parquet_path = root / "items.parquet"
    _write_parquet(parquet_path, table)
    storage = TableStorage(table=table, root=str(root))
    detection = detect_embeddings(table.schema, EmbeddingConfig())
    manager = EmbeddingManager(
        parquet_path=str(parquet_path),
        detection=detection.available,
        rejected=detection.rejected,
        row_to_path=storage.row_index_map(),
        cache=cache,
    )
    return manager, str(parquet_path)


def test_embedding_cache_write_and_invalidate(tmp_path: Path) -> None:
    root = tmp_path
    _make_image(root / "a.jpg")
    _make_image(root / "b.jpg")

    table = _make_table(
        ["a.jpg", "b.jpg"],
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
    )
    workspace = Workspace.for_dataset(str(root), can_write=True)
    workspace.ensure()
    cache_dir = workspace.embedding_cache_dir()
    assert cache_dir is not None
    cache = EmbeddingCache(cache_dir, allow_write=True)

    manager, parquet_path = _build_manager(root, table, cache)
    vec_b64 = _encode_vec([1.0, 0.0, 0.0])
    _ = manager.search_by_vector("clip", vec_b64, top_k=1, min_score=None)

    cache_files = list(cache_dir.glob("*.npz"))
    assert cache_files

    cached = cache.load(parquet_path, manager.available[0])
    assert cached is not None

    original_cache_path = cache.cache_path(parquet_path, manager.available[0])
    assert original_cache_path is not None

    _make_image(root / "c.jpg")
    table_updated = _make_table(
        ["a.jpg", "b.jpg", "c.jpg"],
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
    )
    _write_parquet(Path(parquet_path), table_updated)
    updated_cache_path = cache.cache_path(parquet_path, manager.available[0])
    assert updated_cache_path is not None
    assert updated_cache_path != original_cache_path


def test_embedding_cache_respects_no_write(tmp_path: Path) -> None:
    root = tmp_path
    _make_image(root / "a.jpg")
    _make_image(root / "b.jpg")

    table = _make_table(
        ["a.jpg", "b.jpg"],
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
    )
    workspace = Workspace.for_dataset(str(root), can_write=True)
    workspace.ensure()
    cache_dir = workspace.embedding_cache_dir()
    assert cache_dir is not None
    cache = EmbeddingCache(cache_dir, allow_write=False)

    manager, _ = _build_manager(root, table, cache)
    vec_b64 = _encode_vec([1.0, 0.0, 0.0])
    _ = manager.search_by_vector("clip", vec_b64, top_k=1, min_score=None)

    assert list(cache_dir.glob("*.npz")) == []
