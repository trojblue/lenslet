"""Table labels belong to the image (its source), never to a derived display path."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from lenslet.server import TableAppOptions, create_app_from_table
from lenslet.workspace import Workspace

ORIGIN = "http://localhost:7070"


def _image(path: Path, color: tuple[int, int, int]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 6), color=color).save(path, format="JPEG")
    return str(path)


def _client(tmp_path: Path, rows: list[dict[str, str]], **options) -> TestClient:
    app = create_app_from_table(
        rows,
        options=TableAppOptions(
            workspace=Workspace.for_parquet(tmp_path / "items.parquet", True),
            trusted_write_origins=(ORIGIN,),
            skip_dimension_probe=True,
            **options,
        ),
    )
    return TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})


def _notes(client: TestClient, path: str) -> str:
    return client.get("/item", params={"path": path}).json()["notes"]


def _set_notes(client: TestClient, path: str, notes: str) -> None:
    version = client.get("/item", params={"path": path}).json()["version"]
    response = client.patch(
        "/item",
        params={"path": path},
        headers={"Idempotency-Key": f"{path}-{notes}", "If-Match": str(version)},
        json={"base_version": version, "set_notes": notes},
    )
    assert response.status_code == 200, response.text


def _paths(client: TestClient) -> list[str]:
    return sorted(item["path"] for item in client.get("/folders", params={"path": "/"}).json()["items"])


def test_a_reused_display_path_never_shows_another_images_labels(tmp_path: Path) -> None:
    first = _image(tmp_path / "one" / "p.jpg", (200, 0, 0))
    second = _image(tmp_path / "two" / "p.jpg", (0, 0, 200))

    with _client(tmp_path, [{"path": "p.jpg", "source": first}]) as client:
        _set_notes(client, "/p.jpg", "first image")

    # While both images share the name, each row shows only its own labels.
    rows = [{"path": "p.jpg", "source": first}, {"path": "p.jpg", "source": second}]
    with _client(tmp_path, rows) as client:
        notes = {path: _notes(client, path) for path in _paths(client)}
        assert sorted(notes.values()) == ["", "first image"]

    # The name now belongs to the other image, which has no labels.
    with _client(tmp_path, [{"path": "p.jpg", "source": second}]) as client:
        assert _notes(client, "/p.jpg") == ""

    # The labelled image comes back with its labels.
    with _client(tmp_path, [{"path": "p.jpg", "source": first}]) as client:
        assert _notes(client, "/p.jpg") == "first image"


def test_switching_source_columns_moves_labels_with_their_image(tmp_path: Path) -> None:
    a = _image(tmp_path / "x" / "a.jpg", (200, 0, 0))
    b = _image(tmp_path / "x" / "b.jpg", (0, 200, 0))
    c = _image(tmp_path / "y" / "a.jpg", (0, 0, 200))
    d = _image(tmp_path / "y" / "b.jpg", (200, 200, 0))
    # Both columns derive the names a.jpg/b.jpg, but for different files.
    rows = [
        {"path": "a.jpg", "original": a, "edited": d},
        {"path": "b.jpg", "original": b, "edited": c},
    ]
    with _client(tmp_path, rows, source_column="original", path_column="path") as client:
        _set_notes(client, "/a.jpg", "original a")
        assert client.post("/table/source-column", json={"source_column": "edited"}).status_code == 200
        assert _notes(client, "/a.jpg") == ""
        assert _notes(client, "/b.jpg") == ""
        _set_notes(client, "/b.jpg", "edited c")

        assert client.post("/table/source-column", json={"source_column": "original"}).status_code == 200
        assert _notes(client, "/a.jpg") == "original a"
        assert _notes(client, "/b.jpg") == ""

    # Labels on the column that is not shown survive a restart too.
    with _client(tmp_path, rows, source_column="edited", path_column="path") as client:
        assert _notes(client, "/b.jpg") == "edited c"
        assert _notes(client, "/a.jpg") == ""


def test_one_image_in_two_named_rows_keeps_separate_labels(tmp_path: Path) -> None:
    shared = _image(tmp_path / "shared.jpg", (10, 10, 10))
    rows = [{"path": "caption-a.jpg", "source": shared}, {"path": "caption-b.jpg", "source": shared}]
    with _client(tmp_path, rows) as client:
        _set_notes(client, "/caption-a.jpg", "first caption")
    with _client(tmp_path, list(reversed(rows))) as client:
        assert _notes(client, "/caption-a.jpg") == "first caption"
        assert _notes(client, "/caption-b.jpg") == ""
