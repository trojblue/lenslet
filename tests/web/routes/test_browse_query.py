from __future__ import annotations

import asyncio
import math
from pathlib import Path
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

import lenslet.web.browse as browse
import lenslet.web.app.storage as storage_app
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
        rows.append(
            {
                "path": rel_path,
                "source_column": "target" if index in {4, 5} else "other",
                "score": float(index),
            }
        )
    app = create_app_from_table(
        rows,
        options=TableAppOptions(
            base_dir=str(tmp_path),
            source_column="path",
            skip_dimension_probe=True,
        ),
    )
    return TestClient(app, headers={
        "X-Lenslet-Client-Session": "browse-query-tests",
        "X-Lenslet-Query-Revision": "1",
    })


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
    assert payload["analysis_query_key"].startswith("aq_")
    assert payload["generation_token"]
    assert "total_items" not in payload
    assert [item["name"] for item in payload["items"]] == ["img4.jpg", "img5.jpg"]
    assert all(item["metrics"] is None for item in payload["items"])
    assert all(item["categoricals"] is None for item in payload["items"])
    assert payload["folders"] == []
    assert payload["metric_keys"] == []
    assert payload["categorical_keys"] == []
    assert payload["field_capabilities"]["display_metrics"] == []
    assert payload["dependency_manifest"] == {
        "fields": ["name", "notes", "path", "source", "tags", "url"],
        "metric_keys": [],
        "categorical_keys": ["source_column"],
        "unknown": False,
    }

    fields = client.get(
        "/folders/fields",
        params={"path": "/gallery", "recursive": "1"},
    ).json()
    assert fields["path"] == "/gallery"
    assert fields["metric_keys"] == ["score"]
    assert fields["categorical_keys"] == ["source_column"]
    assert fields["field_capabilities"]["metrics"]["score"]["sortable"] is True
    assert fields["field_capabilities"]["categoricals"]["source_column"]["categorical_input"] is True

    next_body = {**body, "offset": 1, "limit": 1}
    next_payload = client.post("/folders/query", json=next_body).json()
    assert [item["name"] for item in next_payload["items"]] == ["img5.jpg"]
    assert next_payload["analysis_query_key"] == payload["analysis_query_key"]

    inactive_seed_payload = client.post(
        "/folders/query", json={**body, "random_seed": "seed-b"}
    ).json()
    assert inactive_seed_payload["request_token"] == payload["request_token"]

    changed_token_body = {
        **body,
        "sort": {"kind": "builtin", "key": "random", "dir": "asc"},
        "random_seed": "seed-b",
    }
    changed_payload = client.post("/folders/query", json=changed_token_body).json()
    assert changed_payload["request_token"] != payload["request_token"]

    projected_payload = client.post(
        "/folders/query",
        json={
            **body,
            "projection": {
                "metric_keys": ["score"],
                "categorical_keys": ["source_column"],
            },
        },
    ).json()
    assert projected_payload["analysis_query_key"] == payload["analysis_query_key"]
    assert projected_payload["request_token"] != payload["request_token"]
    assert projected_payload["items"][0]["metrics"] == {"score": 4.0}
    assert projected_payload["items"][0]["categoricals"] == {"source_column": "target"}
    assert projected_payload["metric_keys"] == ["score"]
    assert projected_payload["categorical_keys"] == ["source_column"]
    assert projected_payload["field_capabilities"]["display_metrics"] == ["score"]

    unanchored = client.post(
        "/folders/query",
        json={
            **body,
            "filters": {"and": []},
            "text_query": None,
        },
    ).json()
    anchored = client.post(
        "/folders/query",
        json={
            **body,
            "filters": {"and": []},
            "text_query": None,
            "anchor_path": "gallery/img4.jpg",
        },
    ).json()
    assert anchored["offset"] == 3
    assert [item["name"] for item in anchored["items"]] == ["img3.jpg", "img4.jpg"]
    assert anchored["analysis_query_key"] == unanchored["analysis_query_key"]
    assert anchored["request_token"] != unanchored["request_token"]


def test_table_query_builds_one_lean_payload_per_returned_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conversions = 0
    original = storage_app.build_table_query_item_payload

    def count_conversion(*args, **kwargs):
        nonlocal conversions
        conversions += 1
        return original(*args, **kwargs)

    def reject_generic_conversion(*_args, **_kwargs):
        raise AssertionError("table query windows must bypass generic payload conversion")

    monkeypatch.setattr(storage_app, "build_table_query_item_payload", count_conversion)
    monkeypatch.setattr(storage_app, "build_item_payload", reject_generic_conversion)
    client = _client_for_six_row_table(tmp_path)

    response = client.post(
        "/folders/query",
        json={
            "path": "/gallery",
            "recursive": True,
            "offset": 0,
            "limit": 2,
            "filters": {"and": []},
            "sort": {"kind": "builtin", "key": "name", "dir": "asc"},
            "projection": {"metric_keys": ["score"], "categorical_keys": []},
        },
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) == 2
    assert conversions == 2



def test_item_detail_hydrates_complete_metrics_outside_query_window(tmp_path: Path) -> None:
    client = _client_for_six_row_table(tmp_path)

    detail = client.get("/item/detail", params={"path": "/gallery/img0.jpg"})

    assert detail.status_code == 200
    assert detail.json()["metrics"] == {"score": 0.0}


@pytest.mark.parametrize(
    "projection",
    [
        {"metric_keys": [f"metric_{index}" for index in range(65)], "categorical_keys": []},
        {"metric_keys": [], "categorical_keys": [f"category_{index}" for index in range(33)]},
        {"metric_keys": [""], "categorical_keys": []},
        {"metric_keys": ["score", "score"], "categorical_keys": []},
    ],
)
def test_browse_query_rejects_invalid_projection(
    tmp_path: Path,
    projection: dict[str, list[str]],
) -> None:
    client = _client_for_six_row_table(tmp_path)

    response = client.post(
        "/folders/query",
        json={
            "path": "/gallery",
            "recursive": True,
            "offset": 0,
            "limit": 2,
            "filters": {"and": []},
            "sort": {"kind": "builtin", "key": "name", "dir": "asc"},
            "projection": projection,
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "facet_fields",
    [
        {"metric_keys": [f"metric_{index}" for index in range(25)], "categorical_keys": []},
        {"metric_keys": ["score", "score"], "categorical_keys": []},
        {"metric_keys": [], "categorical_keys": [""]},
    ],
)
def test_browse_facets_reject_invalid_field_batches(
    tmp_path: Path,
    facet_fields: dict[str, list[str]],
) -> None:
    client = _client_for_six_row_table(tmp_path)

    response = client.post(
        "/folders/facets",
        json={
            "path": "/gallery",
            "recursive": True,
            "filters": {"and": []},
            "facet_fields": facet_fields,
        },
    )

    assert response.status_code == 422


def test_table_facets_read_only_requested_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    storage = TableStorage(
        [
            {
                "source": f"https://example.test/gallery/img{index}.jpg",
                "path": f"gallery/img{index}.jpg",
                "score": float(index),
                "unused": float(index + 10),
                "split": "train" if index % 2 else "test",
                "width": 8,
                "height": 6,
            }
            for index in range(6)
        ],
        options=TableStorageOptions(
            source_column="source",
            path_column="path",
            categorical_columns=("split",),
            skip_dimension_probe=True,
            allow_local=False,
        ),
    )
    read_metrics: list[str] = []
    original = storage.query_engine.iter_metric_values

    def track_metric(analysis, key):
        read_metrics.append(key)
        return original(analysis, key)

    monkeypatch.setattr(storage.query_engine, "iter_metric_values", track_metric)
    client = TestClient(create_app_from_storage(storage), headers={
        "X-Lenslet-Client-Session": "browse-query-tests",
        "X-Lenslet-Query-Revision": "1",
    })

    response = client.post(
        "/folders/facets",
        json={
            "path": "/gallery",
            "recursive": True,
            "filters": {"and": []},
            "facet_fields": {
                "metric_keys": ["score"],
                "categorical_keys": ["split"],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert read_metrics == ["score"]
    assert payload["metric_keys"] == ["score"]
    assert payload["categorical_keys"] == ["split"]
    assert set(payload["metrics"]) == {"score"}
    assert set(payload["categoricals"]) == {"split"}


def test_concurrent_table_facet_batches_keep_distinct_results() -> None:
    storage = TableStorage(
        [
            {
                "source": f"https://example.test/gallery/img{index}.jpg",
                "path": f"gallery/img{index}.jpg",
                "score": float(index),
                "unused": float(index + 10),
                "split": "train" if index % 2 else "test",
                "width": 8,
                "height": 6,
            }
            for index in range(50)
        ],
        options=TableStorageOptions(
            source_column="source",
            path_column="path",
            categorical_columns=("split",),
            skip_dimension_probe=True,
            allow_local=False,
        ),
    )
    original = storage.facet_summary_for_query_from_analysis

    def slow_facets(*args, **kwargs):
        time.sleep(0.05)
        return original(*args, **kwargs)

    storage.facet_summary_for_query_from_analysis = slow_facets
    app = create_app_from_storage(storage)
    headers = {
        "X-Lenslet-Client-Session": "facet-batch-tab",
        "X-Lenslet-Query-Revision": "1",
    }
    body = {
        "path": "/gallery",
        "recursive": True,
        "filters": {"and": []},
    }

    async def scenario() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            responses = await asyncio.gather(
                client.post(
                    "/folders/facets",
                    json={
                        **body,
                        "facet_fields": {
                            "metric_keys": ["score"],
                            "categorical_keys": [],
                        },
                    },
                    headers=headers,
                ),
                client.post(
                    "/folders/facets",
                    json={
                        **body,
                        "facet_fields": {
                            "metric_keys": ["unused"],
                            "categorical_keys": ["split"],
                        },
                    },
                    headers=headers,
                ),
            )
        await app.state.lenslet_app_context.runtime.query_coordinator.close()
        return responses

    score_response, other_response = asyncio.run(scenario())

    assert score_response.status_code == other_response.status_code == 200
    assert score_response.json()["metric_keys"] == ["score"]
    assert score_response.json()["categorical_keys"] == []
    assert other_response.json()["metric_keys"] == ["unused"]
    assert other_response.json()["categorical_keys"] == ["split"]


def test_query_and_facets_share_one_table_filter_execution() -> None:
    storage = TableStorage(
        [
            {
                "source": f"https://example.test/gallery/img{index}.jpg",
                "path": f"gallery/img{index}.jpg",
                "score": float(index),
                "width": 8,
                "height": 6,
            }
            for index in range(200)
        ],
        options=TableStorageOptions(
            source_column="source",
            path_column="path",
            skip_dimension_probe=True,
            allow_local=False,
        ),
    )
    original = storage.query_engine.analyze_filter
    calls = 0

    def counted_analysis(*args, **kwargs):
        nonlocal calls
        calls += 1
        time.sleep(0.05)
        return original(*args, **kwargs)

    storage.query_engine.analyze_filter = counted_analysis
    app = create_app_from_storage(storage)
    body = {
        "path": "/gallery",
        "recursive": True,
        "offset": 0,
        "limit": 20,
        "filters": {"and": [{"metricRange": {"key": "score", "min": 10, "max": 150}}]},
        "sort": {"kind": "metric", "key": "score", "dir": "desc"},
    }
    headers = {
        "X-Lenslet-Client-Session": "shared-tab",
        "X-Lenslet-Query-Revision": "1",
    }

    async def scenario() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            query, facets = await asyncio.gather(
                client.post("/folders/query", json=body, headers=headers),
                client.post("/folders/facets", json=body, headers=headers),
            )
            health = await client.get("/health")
        await app.state.lenslet_app_context.runtime.query_coordinator.close()
        return query, facets, health

    query, facets, health = asyncio.run(scenario())

    assert query.status_code == facets.status_code == 200
    assert calls == 1
    assert query.json()["filtered_total"] == facets.json()["total_items"] == 141
    counters = health.json()["hotpath"]["counters"]
    assert counters["analysis_active_work"] == 0
    assert counters["analysis_queued_work"] == 0


def test_analysis_ownership_headers_are_validated_together(tmp_path: Path) -> None:
    client = _client_for_six_row_table(tmp_path)
    client.headers.pop("X-Lenslet-Client-Session")
    client.headers.pop("X-Lenslet-Query-Revision")
    body = {
        "path": "/gallery",
        "recursive": True,
        "offset": 0,
        "limit": 2,
    }

    partial = client.post(
        "/folders/query",
        json=body,
        headers={"X-Lenslet-Client-Session": "tab-a"},
    )
    invalid_revision = client.post(
        "/folders/query",
        json=body,
        headers={
            "X-Lenslet-Client-Session": "tab-a",
            "X-Lenslet-Query-Revision": "01",
        },
    )
    oversized = client.post(
        "/folders/query",
        json=body,
        headers={
            "X-Lenslet-Client-Session": "a" * 129,
            "X-Lenslet-Query-Revision": "1",
        },
    )

    assert partial.status_code == invalid_revision.status_code == oversized.status_code == 400


def test_browse_query_rejects_large_metric_sort_hydration_window(tmp_path: Path) -> None:
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

    assert response.status_code == 422


def test_browse_query_metric_sort_page_stays_bounded(tmp_path: Path) -> None:
    client = _client_for_six_row_table(tmp_path)

    response = client.post(
        "/folders/query",
        json={
            "path": "/gallery",
            "recursive": True,
            "offset": 0,
            "limit": 2,
            "sort": {"kind": "metric", "key": "score", "dir": "desc"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 2
    assert payload["filtered_total"] == 6
    assert [item["name"] for item in payload["items"]] == [
        "img5.jpg",
        "img4.jpg",
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
            "numericTerms": [
                {"key": "score", "weight": 1.0, "missing": "invalid", "zNormalize": True}
            ],
            "categoricalTerms": [{"key": "source_column", "value": "target", "weight": 10.0}],
        },
        "projection": {"metric_keys": ["@derived/rubric_1"], "categorical_keys": []},
    }

    response = client.post("/folders/query", json=body)

    assert response.status_code == 200
    payload = response.json()
    assert payload["filtered_total"] == 2
    assert [item["name"] for item in payload["items"]] == ["img5.jpg"]
    expected_score = 10.0 + (5.0 - 2.5) / math.sqrt(35 / 12)
    assert math.isclose(
        payload["items"][0]["metrics"]["@derived/rubric_1"],
        expected_score,
    )
    assert payload["derived_metric_status"] == {
        "key": "@derived/rubric_1",
        "display_name": "Rubric score",
        "status": "applied",
        "score_scope": "query_filtered",
        "score_population_count": 6,
        "valid_count": 6,
        "invalid_count": 0,
        "missing_numeric_inputs": [],
        "unavailable_categorical_inputs": [],
        "z_stats": {
            "score": {
                "mean": 2.5,
                "std": math.sqrt(35 / 12),
                "count": 6,
            },
        },
    }


def test_browse_facets_include_derived_metric_histogram(tmp_path: Path) -> None:
    client = _client_for_six_row_table(tmp_path)
    body = {
        "path": "/gallery",
        "recursive": True,
        "offset": 0,
        "limit": 1,
        "sort": {"kind": "metric", "key": "@derived/rubric_1", "dir": "desc"},
        "derived_metric": {
            "version": 1,
            "id": "rubric_1",
            "name": "Rubric score",
            "intercept": 0.0,
            "numericTerms": [
                {"key": "score", "weight": 1.0, "missing": "invalid", "zNormalize": True}
            ],
            "categoricalTerms": [{"key": "source_column", "value": "target", "weight": 10.0}],
        },
    }

    response = client.post("/folders/facets", json=body)

    assert response.status_code == 200
    payload = response.json()
    assert "@derived/rubric_1" in payload["metric_keys"]
    assert payload["metrics"]["@derived/rubric_1"]["histogram"]["count"] == 6
    assert payload["field_capabilities"]["metrics"]["@derived/rubric_1"]["source"] == "derived"


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
    client = TestClient(create_app_from_storage(storage), headers={
        "X-Lenslet-Client-Session": "browse-query-tests",
        "X-Lenslet-Query-Revision": "1",
    })

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
    client = TestClient(create_app_from_storage(storage), headers={
        "X-Lenslet-Client-Session": "browse-query-tests",
        "X-Lenslet-Query-Revision": "1",
    })

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
    facets_payload = client.post(
        "/folders/facets",
        json={
            "path": "/gallery",
            "recursive": True,
            "offset": 1,
            "limit": 1,
            "filters": {
                "and": [
                    {"categoricalIn": {"key": "source_column", "values": ["target"]}},
                ],
            },
            "sort": {"kind": "builtin", "key": "name", "dir": "asc"},
        },
    ).json()

    assert [item["name"] for item in query_payload["items"]] == ["img0.jpg", "img1.jpg"]
    assert query_payload["scope_total"] == 6
    assert query_payload["filtered_total"] == 6
    assert row_store.materialized_item_count == 2

    values = facets_payload["categoricals"]["source_column"]["values"]
    assert values == [
        {"value": "target", "population_count": 2},
    ]
    assert facets_payload["total_items"] == 2
    assert facets_payload["count_provenance"] == {
        "scope_total": 6,
        "query_filtered_total": 2,
        "loaded_window_total": None,
        "source": "backend_query",
    }
    assert facets_payload["field_capabilities"]["categorical_inputs"]


def test_query_projection_uses_the_same_annotation_snapshot_as_membership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = TableStorage(
        [{
            "source": "https://example.test/gallery/img0.jpg",
            "path": "gallery/img0.jpg",
            "width": 8,
            "height": 6,
        }],
        options=TableStorageOptions(
            source_column="source",
            path_column="path",
            skip_dimension_probe=True,
            allow_local=False,
        ),
    )
    original_order = storage.query_engine.order

    def mutate_after_analysis(*args, **kwargs):
        ordered = original_order(*args, **kwargs)
        sidecar = storage.ensure_sidecar("/gallery/img0.jpg")
        sidecar["star"] = 5
        storage.set_sidecar("/gallery/img0.jpg", sidecar)
        return ordered

    monkeypatch.setattr(storage.query_engine, "order", mutate_after_analysis)
    client = TestClient(create_app_from_storage(storage), headers={
        "X-Lenslet-Client-Session": "browse-query-tests",
        "X-Lenslet-Query-Revision": "1",
    })

    response = client.post(
        "/folders/query",
        json={
            "path": "/gallery",
            "recursive": True,
            "offset": 0,
            "limit": 10,
            "filters": {"and": [{"starsIn": {"values": [0]}}]},
        },
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["star"] is None
    assert storage.get_sidecar_readonly("/gallery/img0.jpg")["star"] == 5


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
            raise AssertionError(
                f"fallback should not materialize unbounded query scope for {path}"
            )

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
