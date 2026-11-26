"""A folder image's labels follow its file name, up to Unicode normalization."""

from __future__ import annotations

import unicodedata
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from lenslet.server import LocalAppOptions, create_app

ORIGIN = "http://localhost:7070"


def _client(root: Path) -> TestClient:
    app = create_app(str(root), options=LocalAppOptions(trusted_write_origins=(ORIGIN,)))
    return TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})


def _set_notes(client: TestClient, path: str, notes: str) -> None:
    version = client.get("/item", params={"path": path}).json()["version"]
    response = client.patch(
        "/item",
        params={"path": path},
        headers={"Idempotency-Key": f"test-{abs(hash((path, notes)))}", "If-Match": str(version)},
        json={"base_version": version, "set_notes": notes},
    )
    assert response.status_code == 200, response.text


def _notes(client: TestClient, path: str) -> str:
    response = client.get("/item", params={"path": path})
    assert response.status_code == 200, response.text
    return response.json()["notes"]


def test_labels_survive_a_file_name_changing_unicode_normalization(tmp_path: Path) -> None:
    decomposed = unicodedata.normalize("NFD", "café.jpg")
    composed = unicodedata.normalize("NFC", "café.jpg")
    assert decomposed != composed
    Image.new("RGB", (8, 6)).save(tmp_path / decomposed, format="JPEG")
    with _client(tmp_path) as client:
        _set_notes(client, f"/{decomposed}", "labelled on macOS")

    # The dataset is copied to a system that stores the composed form.
    (tmp_path / decomposed).rename(tmp_path / composed)
    with _client(tmp_path) as client:
        assert _notes(client, f"/{composed}") == "labelled on macOS"

