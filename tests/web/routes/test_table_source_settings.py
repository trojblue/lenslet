from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from fastapi.testclient import TestClient
from PIL import Image

from lenslet.server import LocalAppOptions, TableAppOptions, create_app, create_app_from_datasets, create_app_from_table
from lenslet.storage.table import TableStorage


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
