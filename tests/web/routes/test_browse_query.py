from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

import lenslet.web.browse as browse
from lenslet.browse.query import BrowseQuerySpec
from lenslet.server import TableAppOptions, create_app_from_storage, create_app_from_table
from lenslet.storage.memory import MemoryStorage
from lenslet.storage.table import TableStorage, TableStorageOptions
from lenslet.web.models import BrowseItemPayload


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 6), color=(20, 40, 60)).save(path, format="JPEG")


def _client_for_six_row_table(tmp_path: Path) -> TestClient:
    rows = []
    for index in range(6):
        rel_path = f"gallery/img{index}.jpg"
        _make_image(tmp_path / rel_path)
        rows.append({
            "path": rel_path,
            "source_column": "target" if index in {4, 5} else "other",
            "score": float(index),
        })
    app = create_app_from_table(
        rows,
        options=TableAppOptions(
            base_dir=str(tmp_path),
            source_column="path",
            skip_dimension_probe=True,
        ),
    )
    return TestClient(app)


def test_browse_query_contract_filters_before_windowing(tmp_path: Path) -> None:
    client = _client_for_six_row_table(tmp_path)
    body = {
        "path": "/gallery",
        "recursive": True,
        "offset": 0,
        "limit": 2,
        "filters": {
            "and": [
                {"categoricalIn": {"key": "source_column", "values": ["target"]}},
            ],
        },
        "sort": {"kind": "builtin", "key": "name", "dir": "asc"},
        "text_query": "img",
        "random_seed": "seed-a",
    }

    response = client.post("/folders/query", json=body)

    assert response.status_code == 200
    payload = response.json()
    assert payload["path"] == "/gallery"
    assert payload["scope_total"] == 6
    assert payload["filtered_total"] == 2
    assert payload["offset"] == 0
    assert payload["limit"] == 2
    assert payload["request_token"].startswith("bq_")
    assert payload["generation_token"]
    assert "total_items" not in payload
    assert [item["name"] for item in payload["items"]] == ["img4.jpg", "img5.jpg"]
    assert payload["folders"] == []
    assert payload["metric_keys"] == ["score"]
    assert "source_column" in payload["categorical_keys"]

    next_body = {**body, "offset": 1, "limit": 1}
    next_payload = client.post("/folders/query", json=next_body).json()
    assert [item["name"] for item in next_payload["items"]] == ["img5.jpg"]

    changed_token_body = {**body, "random_seed": "seed-b"}
    changed_payload = client.post("/folders/query", json=changed_token_body).json()
    assert changed_payload["request_token"] != payload["request_token"]


def test_browse_query_accepts_large_metric_sort_hydration_window(tmp_path: Path) -> None:
    client = _client_for_six_row_table(tmp_path)

    response = client.post(
        "/folders/query",
        json={
            "path": "/gallery",
            "recursive": True,
            "offset": 0,
            "limit": 50_000,
            "sort": {"kind": "metric", "key": "score", "dir": "desc"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 50_000
    assert payload["filtered_total"] == 6
    assert [item["name"] for item in payload["items"]] == [
        "img5.jpg",
        "img4.jpg",
        "img3.jpg",
        "img2.jpg",
        "img1.jpg",
        "img0.jpg",
    ]


def test_browse_query_accepts_derived_metric_for_backend_sort_and_filter(tmp_path: Path) -> None:
    client = _client_for_six_row_table(tmp_path)
    body = {
        "path": "/gallery",
        "recursive": True,
        "offset": 0,
        "limit": 1,
        "filters": {
            "and": [
                {"metricRange": {"key": "@derived/rubric_1", "min": 8.0, "max": 20.0}},
            ],
        },
        "sort": {"kind": "metric", "key": "@derived/rubric_1", "dir": "desc"},
        "derived_metric": {
            "version": 1,
            "id": "rubric_1",
            "name": "Rubric score",
            "intercept": 0.0,
            "numericTerms": [{"key": "score", "weight": 1.0, "missing": "invalid"}],
            "categoricalTerms": [{"key": "source_column", "value": "target", "weight": 10.0}],
        },
    }

    response = client.post("/folders/query", json=body)

    assert response.status_code == 200
    payload = response.json()
    assert payload["filtered_total"] == 2
    assert [item["name"] for item in payload["items"]] == ["img5.jpg"]


def test_browse_query_rejects_malformed_filter_ast(tmp_path: Path) -> None:
    client = _client_for_six_row_table(tmp_path)

    response = client.post(
        "/folders/query",
        json={
            "path": "/gallery",
            "filters": {
                "and": [
                    {
                        "nameContains": {"value": "img"},
                        "categoricalIn": {"key": "source_column", "values": ["target"]},
                    },
                ],
            },
        },
    )

    assert response.status_code == 422


def test_browse_query_rejects_invalid_sort_spec(tmp_path: Path) -> None:
    client = _client_for_six_row_table(tmp_path)

    response = client.post(
        "/folders/query",
        json={
            "path": "/gallery",
            "sort": {"kind": "builtin", "key": "unknown", "dir": "asc"},
        },
    )

    assert response.status_code == 422


def test_browse_query_rejects_invalid_date_filter(tmp_path: Path) -> None:
    client = _client_for_six_row_table(tmp_path)

    response = client.post(
        "/folders/query",
        json={
            "path": "/gallery",
            "filters": {"and": [{"dateRange": {"from": "not-a-date"}}]},
        },
    )

    assert response.status_code == 422


def test_browse_query_rejects_blank_categorical_key(tmp_path: Path) -> None:
    client = _client_for_six_row_table(tmp_path)

    response = client.post(
        "/folders/query",
        json={
            "path": "/gallery",
            "filters": {"and": [{"categoricalIn": {"key": " ", "values": ["target"]}}]},
        },
    )

    assert response.status_code == 422


def test_browse_query_text_search_includes_sidecar_source_fields(tmp_path: Path) -> None:
    image_path = tmp_path / "cat.jpg"
    _make_image(image_path)
    storage = MemoryStorage(str(tmp_path))
    storage.load_index("/")
    sidecar = storage.ensure_sidecar("/cat.jpg")
    sidecar["source"] = "source-token"
    storage.set_sidecar("/cat.jpg", sidecar)
    client = TestClient(create_app_from_storage(storage))

    response = client.post(
        "/folders/query",
        json={
            "path": "/",
            "recursive": True,
            "offset": 0,
            "limit": 10,
            "text_query": "source-token",
        },
    )

    assert response.status_code == 200
    assert [item["path"] for item in response.json()["items"]] == ["/cat.jpg"]


def test_table_query_totals_and_facets_are_separate_backend_truth() -> None:
    rows = [
        {
            "source": f"https://example.test/gallery/img{index}.jpg",
            "path": f"gallery/img{index}.jpg",
            "width": 8,
            "height": 6,
            "source_column": "target" if index in {4, 5} else "other",
            "score": float(index),
        }
        for index in range(6)
    ]
    storage = TableStorage(
        rows,
        options=TableStorageOptions(
            source_column="source",
            path_column="path",
            skip_dimension_probe=True,
            allow_local=False,
        ),
    )
    row_store = storage._row_store
    assert row_store is not None
    client = TestClient(create_app_from_storage(storage))

    query_payload = client.post(
        "/folders/query",
        json={
            "path": "/gallery",
            "recursive": True,
            "offset": 0,
            "limit": 2,
            "sort": {"kind": "builtin", "key": "name", "dir": "asc"},
        },
    ).json()
    facets_payload = client.get(
        "/folders/facets",
        params={"path": "/gallery", "recursive": "1"},
    ).json()

    assert [item["name"] for item in query_payload["items"]] == ["img0.jpg", "img1.jpg"]
    assert query_payload["scope_total"] == 6
    assert query_payload["filtered_total"] == 6
    assert row_store.materialized_item_count == 2

    values = facets_payload["categoricals"]["source_column"]["values"]
    assert values == [
        {"value": "other", "population_count": 4},
        {"value": "target", "population_count": 2},
    ]
    assert facets_payload["total_items"] == 6


def test_browse_query_fallback_refuses_unbounded_recursive_materialization() -> None:
    class _Storage:
        def load_recursive_index(self, path: str):
            assert path == "/huge"
            return SimpleNamespace(
                generated_at="2026-06-09T00:00:00+00:00",
                dirs=[],
                items=[],
            )

        def count_in_scope(self, path: str) -> int:
            assert path == "/huge"
            return browse.BROWSE_QUERY_FALLBACK_MAX_ITEMS + 1

        def recursive_items_hard_limit(self) -> None:
            return None

        def items_in_scope(self, path: str):
            raise AssertionError(f"fallback should not materialize unbounded query scope for {path}")

    with pytest.raises(HTTPException) as exc_info:
        browse.build_folder_query(
            _Storage(),
            BrowseQuerySpec(path="/huge", recursive=True, offset=0, limit=10),
            lambda _storage, _item: BrowseItemPayload(
                path="/unused.jpg",
                name="unused.jpg",
                mime="image/jpeg",
                width=1,
                height=1,
                size=1,
            ),
        )

    assert exc_info.value.status_code == 413
    assert "browse query fallback exceeds server safety limit" in exc_info.value.detail
