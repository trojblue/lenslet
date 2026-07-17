import hashlib
import logging
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient
from PIL import Image

import lenslet.web.app.local as local_app
from lenslet.server import (
    LocalAppOptions,
    TableAppOptions,
    create_app,
    create_app_from_storage,
    create_app_from_table,
)
from lenslet.storage.table import TableStorage, TableStorageOptions
from lenslet.storage.table.launch import ParquetRowFieldProvider, TableLaunchRequest, prepare_table_launch
from lenslet.storage.table.launch_sources import detect_source_column
from lenslet.web.context import get_app_context

LOCAL_ORIGIN = "http://localhost:7070"


def _trusted_client(app) -> TestClient:
    return TestClient(app, base_url=LOCAL_ORIGIN, headers={"Origin": LOCAL_ORIGIN})


def _trusted_local_options(**overrides: object) -> LocalAppOptions:
    return LocalAppOptions(trusted_write_origins=(LOCAL_ORIGIN,), **overrides)


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 6), color=(20, 40, 60)).save(path, format="JPEG")


def _write_parquet(path: Path, data: dict) -> None:
    table = pa.table(data)
    pq.write_table(table, path)


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_parquet_items_and_metrics_inline(tmp_path: Path):
    root = tmp_path
    img_a = root / "a.jpg"
    img_b = root / "b.jpg"
    _make_image(img_a)
    _make_image(img_b)

    _write_parquet(root / "items.parquet", {
        "path": ["a.jpg", "b.jpg"],
        "clip_aesthetic": [0.75, 0.12],
    })

    app = create_app(str(root))
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["mode"] == "table"
    assert health.json().get("refresh", {}).get("enabled") is False

    resp = client.get("/folders", params={"path": "/"})
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload["items"]) == 2
    assert payload["metric_keys"] == ["clip_aesthetic"]
    metrics = [item.get("metrics") for item in payload["items"]]
    assert any(m and "clip_aesthetic" in m for m in metrics)
    assert all("__index_level_0__" not in (item_metrics or {}) for item_metrics in metrics)


def test_parquet_folder_payload_exposes_sorted_metric_keys(tmp_path: Path):
    root = tmp_path
    img_a = root / "gallery" / "a.jpg"
    img_b = root / "gallery" / "b.jpg"
    _make_image(img_a)
    _make_image(img_b)

    _write_parquet(root / "items.parquet", {
        "path": ["gallery/a.jpg", "gallery/b.jpg"],
        "quality_score": [0.8, 0.3],
        "clip_aesthetic": [0.4, 0.2],
        "__index_level_0__": [11, 12],
    })

    client = TestClient(create_app(str(root)))

    payload = client.get("/folders", params={"path": "/gallery"}).json()
    recursive_payload = client.get("/folders", params={"path": "/gallery", "recursive": "1"}).json()

    assert payload["metric_keys"] == ["clip_aesthetic", "quality_score"]
    assert recursive_payload["metric_keys"] == ["clip_aesthetic", "quality_score"]
    assert all(
        "__index_level_0__" not in (item.get("metrics") or {})
        for item in payload["items"]
    )
    assert all(
        "__index_level_0__" not in (item.get("metrics") or {})
        for item in recursive_payload["items"]
    )


def test_parquet_q_formula_columns_are_metrics_not_table_fields(tmp_path: Path):
    root = tmp_path
    img_a = root / "a.jpg"
    img_b = root / "b.jpg"
    _make_image(img_a)
    _make_image(img_b)

    _write_parquet(root / "items.parquet", {
        "path": ["a.jpg", "b.jpg"],
        "q1": [0.75, 0.25],
        "q2": [0.10, None],
        "q3": [1, 0],
        "dataset_from": ["gt", "synthetic"],
        "image_id": [101, 102],
    })

    client = TestClient(create_app(str(root)))

    payload = client.get("/folders", params={"path": "/"}).json()

    assert payload["metric_keys"] == ["q1", "q2", "q3"]
    assert payload["categorical_keys"] == ["dataset_from"]
    assert payload["items"][0]["metrics"] == {"q1": 0.75, "q2": 0.1, "q3": 1.0}
    assert payload["items"][1]["metrics"] == {"q1": 0.25, "q3": 0.0}
    assert payload["items"][0]["categoricals"] == {"dataset_from": "gt"}

    item_payload = client.get("/item", params={"path": "/a.jpg"}).json()
    assert item_payload["table_fields"] == {
        "dataset_from": "gt",
        "image_id": 101,
    }


def test_parquet_numeric_scalar_columns_are_metrics_without_name_whitelist(tmp_path: Path):
    root = tmp_path
    img_a = root / "a.jpg"
    img_b = root / "b.jpg"
    _make_image(img_a)
    _make_image(img_b)

    _write_parquet(root / "items.parquet", {
        "path": ["a.jpg", "b.jpg"],
        "fresh_value": [7.0, 4.0],
        "manual_pick": [0.25, 0.75],
        "anatomy_pose": [3, 2],
        "row_number": [1, 2],
        "is_selected": [True, False],
        "string_number": ["0.5", "0.6"],
    })

    client = TestClient(create_app(str(root)))
    payload = client.get("/folders", params={"path": "/"}).json()

    assert payload["metric_keys"] == ["anatomy_pose", "fresh_value", "manual_pick"]
    assert payload["items"][0]["metrics"] == {
        "fresh_value": 7.0,
        "manual_pick": 0.25,
        "anatomy_pose": 3.0,
    }

    item_payload = client.get("/item", params={"path": "/a.jpg"}).json()
    assert "fresh_value" not in item_payload["table_fields"]
    assert item_payload["table_fields"]["row_number"] == 1
    assert item_payload["table_fields"]["is_selected"] is True
    assert item_payload["table_fields"]["string_number"] == "0.5"


def test_parquet_string_q_columns_remain_visible_table_fields(tmp_path: Path):
    root = tmp_path
    img = root / "a.jpg"
    _make_image(img)

    _write_parquet(root / "items.parquet", {
        "path": ["a.jpg"],
        "q1": ["0.75"],
    })

    client = TestClient(create_app(str(root)))

    payload = client.get("/folders", params={"path": "/"}).json()
    assert payload["metric_keys"] == []

    item_payload = client.get("/item", params={"path": "/a.jpg"}).json()
    assert item_payload["table_fields"] == {"q1": "0.75"}


def test_item_route_skips_optional_table_fields_when_row_provider_fails(tmp_path: Path, caplog):
    root = tmp_path
    img = root / "a.jpg"
    _make_image(img)

    def row_provider(_row_idx: int) -> dict:
        raise OSError("Unexpected end of stream")

    storage = TableStorage(
        [
            {
                "source": str(img),
                "path": "a.jpg",
            }
        ],
        options=TableStorageOptions(
            skip_dimension_probe=True,
            row_field_provider=row_provider,
            table_field_columns=("label",),
        ),
    )
    client = TestClient(create_app_from_storage(storage))

    with caplog.at_level(logging.WARNING, logger="lenslet.storage.table.storage"):
        response = client.get("/item", params={"path": "/a.jpg"})

    assert response.status_code == 200
    assert response.json()["table_fields"] is None
    assert "table field enrichment skipped after row provider failure" in caplog.text


def test_parquet_row_field_provider_memoizes_failed_optional_row_group(tmp_path: Path, caplog):
    parquet_path = tmp_path / "items.parquet"
    _write_parquet(parquet_path, {"path": ["a.jpg"], "label": ["kept"]})
    provider = ParquetRowFieldProvider(parquet_path, ("label",))

    class _FailingParquetFile:
        def __init__(self) -> None:
            self.calls = 0

        def read_row_group(self, _row_group: int, *, columns: list[str]):
            _ = columns
            self.calls += 1
            raise OSError("Unexpected end of stream")

    failing = _FailingParquetFile()
    provider._parquet_file = failing

    with caplog.at_level(logging.WARNING, logger="lenslet.storage.table.launch"):
        assert provider(0) == {}
        assert provider(0) == {}

    assert failing.calls == 1
    assert "table field enrichment skipped for parquet row group 0" in caplog.text


def test_parquet_metric_keys_include_schema_backed_q_columns_for_null_only_folder(tmp_path: Path):
    root = tmp_path
    null_img = root / "nulls" / "a.jpg"
    finite_img = root / "finite" / "b.jpg"
    _make_image(null_img)
    _make_image(finite_img)

    _write_parquet(root / "items.parquet", {
        "path": ["nulls/a.jpg", "finite/b.jpg"],
        "q1": [None, 0.5],
    })

    launch_result = prepare_table_launch(
        TableLaunchRequest(
            parquet_path=root / "items.parquet",
            base_dir=str(root),
            source_column="path",
            cache_dimensions=False,
            skip_dimension_probe=True,
        )
    )
    assert launch_result.storage.metric_keys() == ["q1"]

    client = TestClient(create_app_from_storage(launch_result.storage))
    payload = client.get("/folders", params={"path": "/nulls"}).json()

    assert payload["metric_keys"] == ["q1"]
    assert payload["items"][0]["metrics"] == {}


def test_parquet_item_payload_exposes_non_metric_row_fields(tmp_path: Path):
    root = tmp_path
    img = root / "a.jpg"
    _make_image(img)

    _write_parquet(root / "items.parquet", {
        "path": ["a.jpg"],
        "quality_score": [0.75],
        "image_id": [123],
        "score_reasoning": ["high detail and consistent composition"],
        "__index_level_0__": [7],
    })

    client = TestClient(create_app(str(root)))

    payload = client.get("/item", params={"path": "/a.jpg"}).json()

    assert payload["table_fields"] == {
        "image_id": 123,
        "score_reasoning": "high detail and consistent composition",
    }


def test_parquet_folder_payload_exposes_low_cardinality_string_categoricals(tmp_path: Path):
    root = tmp_path
    img_a = root / "a.jpg"
    img_b = root / "b.jpg"
    _make_image(img_a)
    _make_image(img_b)

    _write_parquet(root / "items.parquet", {
        "path": ["a.jpg", "b.jpg"],
        "l0p_style_family": ["anime", "photographic"],
    })

    client = TestClient(create_app(str(root)))

    payload = client.get("/folders", params={"path": "/"}).json()

    assert payload["metric_keys"] == []
    assert payload["categorical_keys"] == ["l0p_style_family"]
    assert payload["items"][0]["metrics"] == {}
    assert payload["items"][0]["metric_labels"] is None
    assert payload["items"][0]["categoricals"] == {"l0p_style_family": "anime"}
    assert payload["items"][1]["metrics"] == {}
    assert payload["items"][1]["metric_labels"] is None
    assert payload["items"][1]["categoricals"] == {"l0p_style_family": "photographic"}

    item_payload = client.get("/item", params={"path": "/a.jpg"}).json()
    assert item_payload["table_fields"] == {"l0p_style_family": "anime"}


def test_parquet_boolean_columns_are_filterable_categoricals(tmp_path: Path) -> None:
    root = tmp_path
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        _make_image(root / name)

    _write_parquet(root / "items.parquet", {
        "path": ["a.jpg", "b.jpg", "c.jpg"],
        "prev_rated_1star": [True, False, None],
    })

    client = TestClient(create_app(str(root)), headers={
        "X-Lenslet-Client-Session": "parquet-ingestion-tests",
        "X-Lenslet-Query-Revision": "1",
    })
    folder = client.get("/folders", params={"path": "/"}).json()

    assert folder["categorical_keys"] == ["prev_rated_1star"]
    assert folder["items"][0]["categoricals"] == {"prev_rated_1star": "true"}
    assert folder["items"][1]["categoricals"] == {"prev_rated_1star": "false"}
    assert folder["items"][2]["categoricals"] is None

    facets = client.get("/folders/facets", params={"path": "/", "recursive": "1"}).json()
    assert facets["categoricals"]["prev_rated_1star"]["values"] == [
        {"value": "false", "population_count": 1},
        {"value": "true", "population_count": 1},
    ]

    filtered = client.post(
        "/folders/query",
        json={
            "path": "/",
            "recursive": True,
                "filters": {
                "and": [
                    {
                        "categoricalIn": {
                            "key": "prev_rated_1star",
                            "values": ["false"],
                        },
                    },
                    ],
                },
                "projection": {
                    "metric_keys": [],
                    "categorical_keys": ["prev_rated_1star"],
                },
            },
    )
    assert filtered.status_code == 200
    filtered_payload = filtered.json()
    assert [item["name"] for item in filtered_payload["items"]] == ["b.jpg"]
    assert (
        filtered_payload["field_capabilities"]["categoricals"]["prev_rated_1star"][
            "categorical_input"
        ]
        is True
    )


def test_parquet_facets_include_categorical_values_outside_first_page(tmp_path: Path):
    root = tmp_path
    for name in ("a.jpg", "b.jpg", "c.jpg", "d.jpg"):
        _make_image(root / name)

    _write_parquet(root / "items.parquet", {
        "path": ["a.jpg", "b.jpg", "c.jpg", "d.jpg"],
        "original_source": ["ptv03", "gt", "synthetic", "rapidata"],
        "quality_score": [0.1, 0.2, 0.7, 0.9],
    })

    client = TestClient(create_app(str(root)), headers={
        "X-Lenslet-Client-Session": "parquet-ingestion-tests",
        "X-Lenslet-Query-Revision": "1",
    })

    page = client.get(
        "/folders",
        params={"path": "/", "recursive": "1", "offset": "0", "limit": "2"},
    ).json()
    assert [item["categoricals"]["original_source"] for item in page["items"]] == ["ptv03", "gt"]

    facets = client.get("/folders/facets", params={"path": "/", "recursive": "1"}).json()
    values = facets["categoricals"]["original_source"]["values"]
    assert {entry["value"] for entry in values} == {"ptv03", "gt", "synthetic", "rapidata"}
    assert facets["metrics"]["quality_score"]["histogram"]["count"] == 4


def test_table_app_payload_infers_low_cardinality_string_categoricals():
    rows = [
        {
            "image": "https://example.test/images/a.jpg",
            "path": "a.jpg",
            "width": 8,
            "height": 6,
            "categorical": "anime",
            "reviewed": True,
            "image_id": "id-a",
            "prompt": "a long prompt should stay a table field",
        },
        {
            "image": "https://example.test/images/b.jpg",
            "path": "b.jpg",
            "width": 8,
            "height": 6,
            "categorical": "photographic",
            "reviewed": False,
            "image_id": "id-b",
            "prompt": "another long prompt should stay a table field",
        },
    ]

    app = create_app_from_table(
        rows,
        options=TableAppOptions(
            source_column="image",
            path_column="path",
            skip_dimension_probe=True,
            allow_local=False,
        ),
    )
    payload = TestClient(app).get("/folders", params={"path": "/"}).json()

    assert payload["metric_keys"] == []
    assert payload["categorical_keys"] == ["categorical", "reviewed"]
    assert payload["items"][0]["categoricals"] == {
        "categorical": "anime",
        "reviewed": "true",
    }
    assert payload["items"][1]["categoricals"] == {
        "categorical": "photographic",
        "reviewed": "false",
    }


def test_parquet_folder_payload_rejects_sixty_value_string_categoricals(tmp_path: Path):
    root = tmp_path
    paths = []
    values = []
    for idx in range(60):
        image_path = root / f"img_{idx:02d}.jpg"
        _make_image(image_path)
        paths.append(image_path.name)
        values.append(f"value_{idx:02d}")

    _write_parquet(root / "items.parquet", {
        "path": paths,
        "review_bucket": values,
    })

    client = TestClient(create_app(str(root)))

    payload = client.get("/folders", params={"path": "/"}).json()

    assert payload["categorical_keys"] == []
    assert all(item.get("categoricals") is None for item in payload["items"])


def test_table_recursive_large_listing_requires_bounded_window() -> None:
    rows = [
        {
            "source": f"https://example.com/gallery/img_{idx:05d}.jpg",
            "path": f"gallery/img_{idx:05d}.jpg",
            "width": 8,
            "height": 6,
            "size": idx + 1,
            "mtime": 1_700_000_000 + idx,
            "quality_score": float(idx) / 10_000.0,
        }
        for idx in range(10_001)
    ]

    storage = TableStorage(rows, options=TableStorageOptions(skip_dimension_probe=True, allow_local=False))
    client = TestClient(create_app_from_storage(storage))

    resp = client.get("/folders", params={"path": "/gallery", "recursive": "1"})

    assert resp.status_code == 413
    assert "safety limit" in resp.json()["detail"]

    window = client.get(
        "/folders",
        params={"path": "/gallery", "recursive": "1", "offset": "100", "limit": "20"},
    )

    assert window.status_code == 200
    payload = window.json()
    assert payload["total_items"] == 10_001
    assert payload["offset"] == 100
    assert payload["limit"] == 20
    assert len(payload["items"]) == 20
    assert payload["metric_keys"] == ["quality_score"]
    assert payload["items"][0]["path"] == "/gallery/img_00100.jpg"
    assert payload["items"][-1]["path"] == "/gallery/img_00119.jpg"


def test_table_direct_count_only_does_not_materialize_folder_items() -> None:
    rows = [
        {
            "source": f"https://example.com/gallery/img_{idx:04d}.jpg",
            "path": f"gallery/img_{idx:04d}.jpg",
            "width": 8,
            "height": 6,
        }
        for idx in range(25)
    ]
    storage = TableStorage(rows, options=TableStorageOptions(skip_dimension_probe=True, allow_local=False))
    row_store = storage._row_store
    assert row_store is not None

    client = TestClient(create_app_from_storage(storage))
    response = client.get("/folders", params={"path": "/gallery", "count_only": "1"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["total_items"] == 25
    assert row_store.materialized_item_count == 0


def test_views_no_write_mode(tmp_path: Path):
    root = tmp_path
    _make_image(root / "only.jpg")
    _write_parquet(root / "items.parquet", {"image_id": [1], "path": ["only.jpg"]})

    app = create_app(str(root), options=_trusted_local_options(no_write=True))
    client = _trusted_client(app)

    get_views = client.get("/views")
    assert get_views.status_code == 200
    assert get_views.json()["views"] == []

    payload = {"version": 1, "views": [{"id": "demo", "name": "Demo", "pool": {"kind": "folder", "path": "/"}, "view": {"filters": {"and": []}, "sort": {"kind": "builtin", "key": "added", "dir": "desc"}}}]}
    put_views = client.put("/views", json=payload)
    assert put_views.status_code == 200
    assert not (root / ".lenslet").exists()
    saved = client.get("/views")
    assert saved.status_code == 200
    assert saved.json()["views"] == payload["views"]


def test_views_persist(tmp_path: Path):
    root = tmp_path
    _make_image(root / "only.jpg")
    _write_parquet(root / "items.parquet", {"image_id": [1], "path": ["only.jpg"]})

    app = create_app(str(root), options=_trusted_local_options(no_write=False))
    client = _trusted_client(app)

    payload = {"version": 1, "views": [{"id": "demo", "name": "Demo", "pool": {"kind": "folder", "path": "/"}, "view": {"filters": {"and": []}, "sort": {"kind": "builtin", "key": "added", "dir": "desc"}}}]}
    put_views = client.put("/views", json=payload)
    assert put_views.status_code == 200

    views_path = root / ".lenslet" / "views.json"
    assert views_path.exists()
    saved = client.get("/views")
    assert saved.status_code == 200
    assert saved.json()["views"][0]["id"] == "demo"


def test_standalone_parquet_auto_detects_safe_absolute_source_root(tmp_path: Path):
    outputs = tmp_path / "outputs"
    dataset = tmp_path / "dataset"
    outputs.mkdir(parents=True, exist_ok=True)

    img_a = dataset / "a.jpg"
    img_b = dataset / "b.jpg"
    _make_image(img_a)
    _make_image(img_b)

    parquet_path = outputs / "items.parquet"
    _write_parquet(parquet_path, {
        "path": [str(img_a), str(img_b)],
        "quality_score": [0.9, 0.4],
    })

    launch_result = prepare_table_launch(
        TableLaunchRequest(
            parquet_path=parquet_path,
            base_dir=None,
            source_column=None,
            cache_dimensions=False,
            skip_dimension_probe=True,
            auto_detect_root=True,
        )
    )
    storage = launch_result.storage

    assert storage.root == str(dataset)
    assert storage.total_items() == 2

    client = TestClient(create_app_from_storage(storage))
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["total_images"] == 2


def test_prepare_table_launch_honors_explicit_logical_path_column(tmp_path: Path) -> None:
    img_a = tmp_path / "images" / "a.jpg"
    img_b = tmp_path / "images" / "b.jpg"
    _make_image(img_a)
    _make_image(img_b)

    parquet_path = tmp_path / "items.parquet"
    _write_parquet(
        parquet_path,
        {
            "image_uri": [str(img_a), str(img_b)],
            "display_path": ["logical/alpha.jpg", "logical/nested/beta.jpg"],
        },
    )

    launch_result = prepare_table_launch(
        TableLaunchRequest(
            parquet_path=parquet_path,
            base_dir=None,
            source_column="image_uri",
            path_column="display_path",
            cache_dimensions=False,
            skip_dimension_probe=True,
        )
    )

    assert [item.path for item in launch_result.storage.items_in_scope("/")] == [
        "logical/alpha.jpg",
        "logical/nested/beta.jpg",
    ]
    assert launch_result.storage.path_for_row_index(0) == "logical/alpha.jpg"
    assert launch_result.storage.path_for_row_index(1) == "logical/nested/beta.jpg"


def test_create_app_uses_retained_cache_dimensions_launch_result(tmp_path: Path) -> None:
    image_path = tmp_path / "images" / "a.jpg"
    _make_image(image_path)
    parquet_path = tmp_path / "items.parquet"
    _write_parquet(
        parquet_path,
        {
            "source": ["images/a.jpg"],
            "path": ["gallery/a.jpg"],
        },
    )

    launch_result = prepare_table_launch(
        TableLaunchRequest(
            parquet_path=parquet_path,
            base_dir=str(tmp_path),
            source_column="source",
            path_column="path",
            cache_dimensions=True,
            skip_dimension_probe=True,
        )
    )
    app = local_app.create_local_app(str(tmp_path), options=LocalAppOptions(), table_launch=launch_result)

    context = get_app_context(app)
    cached_table = pq.read_table(parquet_path)

    assert context.storage is launch_result.storage
    assert context.storage_mode == "table"
    assert context.storage_origin == "parquet"
    assert cached_table["width"].to_pylist() == [8]
    assert cached_table["height"].to_pylist() == [6]


def test_prepare_table_launch_uses_workspace_dimension_cache_without_source_write(
    tmp_path: Path,
    monkeypatch,
) -> None:
    image_path = tmp_path / "images" / "a.jpg"
    _make_image(image_path)
    parquet_path = tmp_path / "items.parquet"
    _write_parquet(
        parquet_path,
        {
            "source": ["images/a.jpg"],
            "path": ["gallery/a.jpg"],
        },
    )
    source_hash = _file_hash(parquet_path)
    dimension_cache_dir = tmp_path / "items.parquet.cache" / "dimensions"

    launch_result = prepare_table_launch(
        TableLaunchRequest(
            parquet_path=parquet_path,
            base_dir=str(tmp_path),
            source_column="source",
            path_column="path",
            cache_dimensions=False,
            dimension_cache_dir=dimension_cache_dir,
            skip_dimension_probe=True,
        )
    )

    assert _file_hash(parquet_path) == source_hash
    assert "width" not in pq.read_table(parquet_path).schema.names
    assert launch_result.storage.row_dimensions() == [(8, 6)]
    assert {notice.kind for notice in launch_result.notices} >= {
        "dimension_cache_requires_probe",
        "workspace_dimensions_cached",
    }
    assert list(dimension_cache_dir.rglob("*.json"))

    def _fail_dimension_probe(_path: str):
        raise AssertionError("workspace dimension cache should avoid source probing")

    monkeypatch.setattr(
        "lenslet.storage.table.row_scan.read_dimensions_fast",
        _fail_dimension_probe,
    )

    cached_launch = prepare_table_launch(
        TableLaunchRequest(
            parquet_path=parquet_path,
            base_dir=str(tmp_path),
            source_column="source",
            path_column="path",
            cache_dimensions=False,
            dimension_cache_dir=dimension_cache_dir,
            skip_dimension_probe=True,
        )
    )

    assert cached_launch.storage.row_dimensions() == [(8, 6)]
    assert _file_hash(parquet_path) == source_hash


def test_workspace_dimension_cache_is_namespaced_by_source_column(tmp_path: Path) -> None:
    image_a = tmp_path / "images" / "a.jpg"
    image_b = tmp_path / "images" / "b.jpg"
    image_a.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 6), color=(20, 40, 60)).save(image_a, format="JPEG")
    Image.new("RGB", (5, 4), color=(60, 40, 20)).save(image_b, format="JPEG")
    parquet_path = tmp_path / "items.parquet"
    _write_parquet(
        parquet_path,
        {
            "source_a": ["images/a.jpg"],
            "source_b": ["images/b.jpg"],
            "path": ["gallery/item.jpg"],
        },
    )
    dimension_cache_dir = tmp_path / "items.parquet.cache" / "dimensions"

    first = prepare_table_launch(
        TableLaunchRequest(
            parquet_path=parquet_path,
            base_dir=str(tmp_path),
            source_column="source_a",
            path_column="path",
            cache_dimensions=False,
            dimension_cache_dir=dimension_cache_dir,
            skip_dimension_probe=True,
        )
    )
    second = prepare_table_launch(
        TableLaunchRequest(
            parquet_path=parquet_path,
            base_dir=str(tmp_path),
            source_column="source_b",
            path_column="path",
            cache_dimensions=False,
            dimension_cache_dir=dimension_cache_dir,
            skip_dimension_probe=True,
        )
    )

    assert first.storage.row_dimensions() == [(8, 6)]
    assert second.storage.row_dimensions() == [(5, 4)]
    assert len(list(dimension_cache_dir.rglob("*.json"))) == 2


def test_prepare_table_launch_caches_extensionless_remote_dimensions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_url = "https://images.example.test/r2/encoded-image-key"
    parquet_path = tmp_path / "items.parquet"
    _write_parquet(parquet_path, {"url": [source_url]})

    monkeypatch.setattr(TableStorage, "_source_header_is_image", lambda self, source: True)
    monkeypatch.setattr(
        TableStorage,
        "_get_remote_header_info",
        lambda self, url, name: ((21, 13), 456),
    )

    launch_result = prepare_table_launch(
        TableLaunchRequest(
            parquet_path=parquet_path,
            base_dir=None,
            source_column=None,
            cache_dimensions=True,
            skip_dimension_probe=True,
        )
    )

    cached_table = pq.read_table(parquet_path)
    assert launch_result.storage.table_source_column_state().current == "url"
    assert launch_result.storage.row_dimensions() == [(21, 13)]
    assert cached_table["width"].to_pylist() == [21]
    assert cached_table["height"].to_pylist() == [13]
    assert {notice.kind for notice in launch_result.notices} >= {
        "dimension_cache_requires_probe",
        "dimensions_cached",
    }


def test_parquet_source_detection_ignores_nested_leaf_field_names(tmp_path: Path):
    root = tmp_path
    img_a = root / "dataset" / "a.jpg"
    img_b = root / "dataset" / "b.jpg"
    _make_image(img_a)
    _make_image(img_b)

    themes_type = pa.list_(pa.field("element", pa.string()))
    table = pa.table(
        {
            "themes": pa.array([["portrait"], ["landscape"]], type=themes_type),
            "path": pa.array([str(img_a), str(img_b)]),
        }
    )
    parquet_path = root / "items.parquet"
    pq.write_table(table, parquet_path)

    assert detect_source_column(str(parquet_path), str(root)) == "path"


def test_explicit_remote_source_column_does_not_report_default_root_as_auto_detected(
    tmp_path: Path,
    capsys,
):
    parquet_path = tmp_path / "items.parquet"
    _write_parquet(
        parquet_path,
        {
            "s3key": [
                "https://example.test/images/a.jpg",
                "https://example.test/images/b.jpg",
            ],
        },
    )

    launch_result = prepare_table_launch(
        TableLaunchRequest(
            parquet_path=parquet_path,
            base_dir=None,
            source_column="s3key",
            cache_dimensions=False,
            skip_dimension_probe=True,
            auto_detect_root=True,
        )
    )

    assert all(notice.kind != "auto_detected_root" for notice in launch_result.notices)
    assert "Auto-detected local source root" not in capsys.readouterr().out
