from __future__ import annotations

from fastapi.testclient import TestClient

from lenslet.server import TableAppOptions, create_app_from_datasets, create_app_from_table
from lenslet.storage.table import TableStorage


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
        },
        {
            "image_url": "https://pages.example.test/report-b",
            "candidate": "https://images.example.test/b.jpg",
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
    assert len(folder.json()["items"]) == 2
