from pathlib import Path
import base64

import pytest
import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient
from PIL import Image

from lenslet.embeddings.config import EmbeddingConfig
from lenslet.embeddings.detect import columns_without_embeddings, detect_embeddings
from lenslet.storage.table import TableStorage, load_parquet_table
from lenslet.server import create_app

np = pytest.importorskip("numpy")


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 6), color=(20, 40, 60)).save(path, format="JPEG")


def _write_parquet(path: Path, table: pa.Table) -> None:
    pq.write_table(table, path)


def _encode_vec(vec) -> str:
    arr = np.asarray(vec, dtype="<f4")
    return base64.b64encode(arr.tobytes()).decode("ascii")


def test_embedding_detection_and_exclusion(tmp_path: Path):
    root = tmp_path
    _make_image(root / "a.jpg")
    _make_image(root / "b.jpg")

    embed_type = pa.list_(pa.float32(), 3)
    fixed = pa.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], type=embed_type)
    variable = pa.array([[1.0], [2.0, 3.0]], type=pa.list_(pa.float32()))

    table = pa.Table.from_arrays(
        [pa.array(["a.jpg", "b.jpg"]), fixed, variable],
        names=["path", "embed_fixed", "embed_var"],
    )
    parquet_path = root / "items.parquet"
    _write_parquet(parquet_path, table)

    schema = table.schema
    detection = detect_embeddings(schema, EmbeddingConfig())
    assert any(spec.name == "embed_fixed" for spec in detection.available)
    assert any(rej.name == "embed_var" for rej in detection.rejected)

    columns = columns_without_embeddings(schema, detection)
    table_loaded = load_parquet_table(str(parquet_path), columns=columns)
    storage = TableStorage(table=table_loaded, root=str(root))
    assert "embed_fixed" not in storage._columns


def test_embedding_search_by_path_and_vector(tmp_path: Path):
    root = tmp_path
    _make_image(root / "a.jpg")
    _make_image(root / "b.jpg")
    _make_image(root / "c.jpg")

    embed_type = pa.list_(pa.float32(), 3)
    embeds = pa.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        type=embed_type,
    )
    table = pa.Table.from_arrays(
        [pa.array(["a.jpg", "b.jpg", "c.jpg"]), embeds],
        names=["path", "clip"],
    )
    parquet_path = root / "items.parquet"
    _write_parquet(parquet_path, table)

    app = create_app(str(root))
    client = TestClient(app)

    resp = client.get("/embeddings")
    assert resp.status_code == 200
    payload = resp.json()
    assert any(item["name"] == "clip" for item in payload["embeddings"])

    resp = client.post(
        "/embeddings/search",
        json={"embedding": "clip", "query_path": "/a.jpg", "top_k": 2},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items[0]["path"] == "/a.jpg"
    assert items[0]["score"] == pytest.approx(1.0, rel=1e-5)

    vec_b64 = _encode_vec([0.0, 1.0, 0.0])
    resp = client.post(
        "/embeddings/search",
        json={"embedding": "clip", "query_vector_b64": vec_b64, "top_k": 2},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items[0]["path"] == "/b.jpg"

    resp = client.post(
        "/embeddings/search",
        json={"embedding": "clip", "query_vector_b64": "not-base64"},
    )
    assert resp.status_code == 400

    bad_vec = _encode_vec([0.0, 1.0])
    resp = client.post(
        "/embeddings/search",
        json={"embedding": "clip", "query_vector_b64": bad_vec},
    )
    assert resp.status_code == 400

    nan_vec = np.array([np.nan, 0.0, 1.0], dtype="<f4")
    resp = client.post(
        "/embeddings/search",
        json={"embedding": "clip", "query_vector_b64": base64.b64encode(nan_vec.tobytes()).decode("ascii")},
    )
    assert resp.status_code == 400
