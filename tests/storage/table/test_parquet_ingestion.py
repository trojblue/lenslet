from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient
from PIL import Image

import lenslet.web.app.local as local_app
from lenslet.server import LocalAppOptions, create_app, create_app_from_storage
from lenslet.storage.table import TableStorage, TableStorageOptions
from lenslet.storage.table.launch import TableLaunchRequest, prepare_table_launch
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
