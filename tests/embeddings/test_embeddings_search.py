from pathlib import Path
import base64
from dataclasses import replace

import pytest
import pyarrow as pa
import pyarrow.parquet as pq
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from lenslet.embeddings.config import EmbeddingConfig
from lenslet.embeddings.detect import columns_without_embeddings, detect_embeddings
from lenslet.embeddings.embedder import EmbedConfig
from lenslet.embeddings.index import EmbeddingMatch
from lenslet.indexing_status import IndexingLifecycle
from lenslet.web.context import AppContext, set_app_context
from lenslet.web.routes.embeddings import register_embedding_routes
from lenslet.web.runtime import AppRuntime
from lenslet.web.sync.events import EventBroker, IdempotencyCache
from lenslet.web.sync.labels import SnapshotWriter
from lenslet.web.sync.presence import PresenceMetrics, PresenceTracker
from lenslet.web.thumbs import ThumbnailScheduler
from lenslet.storage.table import TableStorage, TableStorageOptions, load_parquet_table
from lenslet.server import create_app
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


class _StubEmbeddingManager:
    available = [type("Spec", (), {"name": "clip", "dimension": 3, "dtype": "float32", "metric": "cosine"})()]
    rejected: list[object] = []

    def __init__(self) -> None:
        self.row_indices: list[int] = []

    @staticmethod
    def get_spec(name: str):
        return _StubEmbeddingManager.available[0] if name == "clip" else None

    def search_by_row_index(self, name: str, *, row_index: int, top_k: int, min_score: float | None):
        assert name == "clip"
        assert top_k == 1
        assert min_score is None
        self.row_indices.append(row_index)
        return [EmbeddingMatch(row_index=row_index, path="updated.jpg", score=1.0)]


def _runtime_stub(workspace: Workspace) -> AppRuntime:
    thumb_queue: ThumbnailScheduler[bytes] = ThumbnailScheduler(max_workers=1)
    return AppRuntime(
        sidecar_lock=None,
        log_lock=None,
        broker=EventBroker(),
        idempotency_cache=IdempotencyCache(),
        snapshotter=SnapshotWriter(workspace),
        sync_state={"last_event_id": 0},
        presence=PresenceTracker(view_ttl=1.0, edit_ttl=1.0),
        presence_metrics=PresenceMetrics(),
        presence_prune_interval=1.0,
        thumb_queue=thumb_queue,
        thumb_cache=None,
        hotpath_metrics=type("Metrics", (), {"snapshot": lambda self, storage=None: {"counters": {}, "timers_ms": {}}})(),
    )


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
    storage = TableStorage(table_loaded, options=TableStorageOptions(root=str(root)))
    assert "embed_fixed" not in storage.sidecar_enrichment_for_path("a.jpg").get("table_fields", {})


def test_embedding_search_uses_current_request_context_storage(tmp_path: Path) -> None:
    old_image = tmp_path / "old.jpg"
    updated_image = tmp_path / "updated.jpg"
    _make_image(old_image)
    _make_image(updated_image)

    initial_storage = TableStorage(
        [{"path": "old.jpg", "source": str(old_image)}],
        options=TableStorageOptions(skip_dimension_probe=True),
    )
    updated_storage = TableStorage(
        [{"path": "updated.jpg", "source": str(updated_image)}],
        options=TableStorageOptions(skip_dimension_probe=True),
    )
    workspace = Workspace(root=tmp_path / ".lenslet", can_write=False)
    runtime = _runtime_stub(workspace)
    context = AppContext(
        storage=initial_storage,
        workspace=workspace,
        runtime=runtime,
        recursive_browse_cache=None,
        og_cache=None,
        storage_mode="table",
        storage_origin="test",
        indexing=IndexingLifecycle.ready(scope="/"),
    )
    app = FastAPI()
    manager = _StubEmbeddingManager()
    set_app_context(app, context)
    register_embedding_routes(app, manager)
    set_app_context(app, replace(context, storage=updated_storage))

    try:
        with TestClient(app) as client:
            response = client.post(
                "/embeddings/search",
                json={"embedding": "clip", "query": {"kind": "path", "path": "/updated.jpg"}, "top_k": 1},
            )
    finally:
        runtime.thumb_queue.close()

    assert response.status_code == 200
    assert response.json()["items"][0]["path"] == "/updated.jpg"
    assert manager.row_indices == [0]


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
        json={"embedding": "clip", "query": {"kind": "path", "path": "/a.jpg"}, "top_k": 2},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items[0]["path"] == "/a.jpg"
    assert items[0]["score"] == pytest.approx(1.0, rel=1e-5)

    vec_b64 = _encode_vec([0.0, 1.0, 0.0])
    resp = client.post(
        "/embeddings/search",
        json={"embedding": "clip", "query": {"kind": "vector", "vector_b64": vec_b64}, "top_k": 2},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items[0]["path"] == "/b.jpg"

    resp = client.post(
        "/embeddings/search",
        json={"embedding": "clip", "query": {"kind": "vector", "vector_b64": "not-base64"}},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_embedding_query"

    bad_vec = _encode_vec([0.0, 1.0])
    resp = client.post(
        "/embeddings/search",
        json={"embedding": "clip", "query": {"kind": "vector", "vector_b64": bad_vec}},
    )
    assert resp.status_code == 400

    nan_vec = np.array([np.nan, 0.0, 1.0], dtype="<f4")
    resp = client.post(
        "/embeddings/search",
        json={
            "embedding": "clip",
            "query": {"kind": "vector", "vector_b64": base64.b64encode(nan_vec.tobytes()).decode("ascii")},
        },
    )
    assert resp.status_code == 400


def test_embedding_search_requires_discriminated_query_payload() -> None:
    app = FastAPI()
    register_embedding_routes(app, _StubEmbeddingManager())

    with TestClient(app) as client:
        legacy_response = client.post(
            "/embeddings/search",
            json={"embedding": "clip", "query_path": "/a.jpg", "top_k": 1},
        )
        missing_kind_response = client.post(
            "/embeddings/search",
            json={"embedding": "clip", "query": {"path": "/a.jpg"}, "top_k": 1},
        )

    assert legacy_response.status_code == 422
    assert missing_kind_response.status_code == 422


def test_embedding_search_app_failures_use_error_response_envelope() -> None:
    app = FastAPI()
    register_embedding_routes(app, None)

    schema = app.openapi()
    responses = schema["paths"]["/embeddings/search"]["post"]["responses"]
    assert responses["400"]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")
    assert responses["404"]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")

    with TestClient(app) as client:
        response = client.post(
            "/embeddings/search",
            json={"embedding": "clip", "query": {"kind": "vector", "vector_b64": _encode_vec([1, 0, 0])}},
        )

    assert response.status_code == 404
    assert response.json() == {
        "error": "embedding_search_unavailable",
        "message": "embedding search unavailable",
    }


def test_embedding_generation_defaults_to_fail_fast_load_errors() -> None:
    assert EmbedConfig().error_policy == "raise"
