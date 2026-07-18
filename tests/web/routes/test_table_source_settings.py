from __future__ import annotations

import os
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient
from PIL import Image

from lenslet.server import (
    LocalAppOptions,
    StorageAppOptions,
    TableAppOptions,
    create_app,
    create_app_from_datasets,
    create_app_from_storage,
    create_app_from_table,
)
from lenslet.storage.table import TableStorage
from lenslet.storage.table.launch import TableLaunchRequest, prepare_table_launch
from lenslet.web.context import get_app_context
from lenslet.web.models import LaunchSessionPayload
from lenslet.workspace import Workspace


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 6), color=(20, 40, 60)).save(path, format="JPEG")


def _write_parquet(path: Path, data: dict) -> None:
    table = pa.table(data)
    pq.write_table(table, path)


def test_table_source_columns_disabled_outside_table_mode() -> None:
    client = TestClient(create_app_from_datasets({"demo": []}))

    response = client.get("/table/source-columns")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "current": None,
        "columns": [],
        "warning": None,
    }


def test_table_source_column_route_switches_read_only_table_source(
    monkeypatch,
) -> None:
    monkeypatch.setattr(TableStorage, "_source_header_is_image", lambda self, source: False)
    rows = [
        {
            "image_url": "https://pages.example.test/report-a",
            "candidate": "https://images.example.test/a.jpg",
            "q1": 0.25,
            "q2": None,
        },
        {
            "image_url": "https://pages.example.test/report-b",
            "candidate": "https://images.example.test/b.jpg",
            "q1": 0.75,
            "q2": None,
        },
    ]
    client = TestClient(
        create_app_from_table(
            rows,
            options=TableAppOptions(
                source_column="image_url",
                allow_local=False,
                skip_dimension_probe=True,
            ),
        )
    )

    current = client.get("/table/source-columns")
    assert current.status_code == 200
    current_payload = current.json()
    assert current_payload["current"] == "image_url"
    assert current_payload["warning"] == "The selected source column produced no loadable gallery entries."

    switched = client.post("/table/source-column", json={"source_column": "candidate"})

    assert switched.status_code == 200
    switched_payload = switched.json()
    assert switched_payload["current"] == "candidate"
    assert switched_payload["warning"] is None

    folder = client.get("/folders", params={"path": "/", "recursive": "1"})
    assert folder.status_code == 200
    folder_payload = folder.json()
    assert len(folder_payload["items"]) == 2
    assert folder_payload["metric_keys"] == ["q1", "q2"]
    assert folder_payload["items"][0]["metrics"] == {"q1": 0.25}
    assert folder_payload["items"][1]["metrics"] == {"q1": 0.75}


def test_health_exposes_redacted_table_launch_status(tmp_path: Path) -> None:
    _make_image(tmp_path / "media" / "a.jpg")
    client = TestClient(
        create_app_from_table(
            [
                {
                    "source": "media/a.jpg",
                    "path": "media/a.jpg",
                    "width": 8,
                    "height": 6,
                },
                {
                    "source": "missing.jpg",
                    "path": "missing.jpg",
                    "width": 0,
                    "height": 0,
                },
            ],
            options=TableAppOptions(
                base_dir=str(tmp_path),
                source_column="source",
                path_column="path",
                skip_dimension_probe=True,
                show_source=False,
            ),
        )
    )

    response = client.get("/health")

    assert response.status_code == 200
    status = response.json()["table_launch_status"]
    assert status["source_column"] == "source"
    assert status["path_column"] == "path"
    assert status["path_mode"] == "explicit"
    assert status["root_policy"] == "base-dir"
    assert status["base_dir"] == "[local path]"
    assert status["source_table_rows"] == 2
    assert status["gallery_rows"] == 1
    assert status["skipped_rows"]["total"] == 1
    assert status["skipped_rows"]["local_missing"] == 1
    assert status["dimension_coverage"] == {"known": 1, "missing": 0, "total": 1}
    assert status["original_media_policy"]["mode"] == "local_streaming"
    assert status["original_media_policy"]["source_kind"] == "local"
    assert status["original_media_policy"]["redacted_origin"] == "[local path]"

    folder = client.get("/folders", params={"path": "/", "recursive": "1"})
    assert folder.status_code == 200
    [item] = folder.json()["items"]
    assert item["original_media"]["mode"] == "local_streaming"
    assert item["original_media"]["redacted_origin"] == "[local path]"

    query = client.post("/folders/query", headers={
        "X-Lenslet-Client-Session": "source-policy-test",
        "X-Lenslet-Query-Revision": "1",
    }, json={
        "path": "/",
        "recursive": True,
        "offset": 0,
        "limit": 1,
        "filters": {"and": []},
        "sort": {"kind": "builtin", "key": "name", "dir": "asc"},
        "projection": {"metric_keys": [], "categorical_keys": []},
    })
    assert query.status_code == 200
    [query_item] = query.json()["items"]
    assert query_item["source"] is None
    assert query_item["original_media"]["mode"] == "local_streaming"


def test_local_table_source_change_publishes_one_restart_transition(tmp_path: Path) -> None:
    source = tmp_path / "items.parquet"
    _write_parquet(source, {
        "source": ["https://example.test/a.jpg"],
        "path": ["a.jpg"],
    })
    launch = prepare_table_launch(
        TableLaunchRequest(
            parquet_path=source,
            base_dir=None,
            source_column="source",
            path_column="path",
            cache_dimensions=False,
            skip_dimension_probe=True,
        )
    )
    launch_session = LaunchSessionPayload(
        kind="local_parquet",
        loaded_from_label="Local Parquet",
        target_label=".../items.parquet",
        title_label="items.parquet",
        detail_label="Table · read-only",
    )
    app = create_app_from_storage(
        launch.storage,
        options=StorageAppOptions(
            workspace=Workspace.for_dataset(None, can_write=False),
            storage_mode="table",
            storage_origin="parquet",
            refresh="static",
            launch_session=launch_session,
        ),
    )

    with TestClient(app) as client:
        context = get_app_context(app)
        client.portal.call(context.runtime.table_source_monitor.close)
        initial = client.get("/health").json()
        replacement = tmp_path / "replacement.parquet"
        _write_parquet(replacement, {
            "source": ["https://example.test/b.jpg", "https://example.test/c.jpg"],
            "path": ["b.jpg", "c.jpg"],
        })
        os.replace(replacement, source)

        assert client.portal.call(context.runtime.table_source_monitor.poll_once) is True
        assert client.portal.call(context.runtime.table_source_monitor.poll_once) is False
        changed = client.get("/health").json()

    assert initial["table_launch_status"]["source_refresh"]["state"] == "current"
    assert changed["table_launch_status"]["source_refresh"] == {
        "state": "restart-required",
        "generation": initial["table_launch_status"]["source_refresh"]["generation"],
        "message": "The source table changed; restart Lenslet to load the new snapshot.",
    }
    assert changed["table_launch_status"]["source_table_rows"] == 1
    assert changed["table_launch_status"]["gallery_rows"] == 1
    assert changed["total_images"] == 1
    assert changed["launch_session"] == initial["launch_session"] == launch_session.model_dump(
        exclude_none=True
    )
    assert changed["refresh"] == {
        "enabled": False,
        "note": "The source table changed; restart Lenslet to load the new snapshot.",
    }
    source_events = [
        event
        for event in context.runtime.broker.replay(0)
        if event["event"] == "table-source"
    ]
    assert len(source_events) == 1
    assert str(tmp_path) not in str(source_events[0])


def test_unversioned_table_source_reports_restart_required() -> None:
    client = TestClient(
        create_app_from_table(
            [{"source": "https://example.test/a.jpg", "path": "a.jpg"}],
            options=TableAppOptions(
                source_column="source",
                path_column="path",
                skip_dimension_probe=True,
                source_refresh="restart-required",
            ),
        )
    )

    health = client.get("/health").json()

    assert health["table_launch_status"]["source_refresh"] == {
        "state": "restart-required",
        "message": "This table source cannot be checked safely; restart Lenslet to reload it.",
    }
    assert health["refresh"]["note"] == (
        "This table source cannot be checked safely; restart Lenslet to reload it."
    )


def test_projected_parquet_source_column_switch_keeps_q_metric_keys(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(TableStorage, "_source_header_is_image", lambda self, source: False)
    _make_image(tmp_path / "unused.jpg")
    _write_parquet(
        tmp_path / "items.parquet",
        {
            "image_url": [
                "https://pages.example.test/report-a",
                "https://pages.example.test/report-b",
            ],
            "candidate": [
                "https://images.example.test/a.jpg",
                "https://images.example.test/b.jpg",
            ],
            "q1": [0.2, 0.8],
            "q2": [None, 0.0],
        },
    )
    client = TestClient(
        create_app(
            str(tmp_path),
            options=LocalAppOptions(
                source_column="image_url",
                skip_dimension_probe=True,
            ),
        )
    )

    current = client.get("/table/source-columns")
    assert current.status_code == 200
    assert {column["name"] for column in current.json()["columns"]} >= {"image_url", "candidate"}

    switched = client.post("/table/source-column", json={"source_column": "candidate"})
    assert switched.status_code == 200
    assert switched.json()["current"] == "candidate"

    folder = client.get("/folders", params={"path": "/", "recursive": "1"})
    assert folder.status_code == 200
    folder_payload = folder.json()
    assert len(folder_payload["items"]) == 2
    assert folder_payload["metric_keys"] == ["q1", "q2"]
    assert folder_payload["items"][0]["metrics"] == {"q1": 0.2}
    assert folder_payload["items"][1]["metrics"] == {"q1": 0.8, "q2": 0.0}
