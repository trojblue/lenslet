from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import lenslet
from PIL import Image
import pytest


def test_public_launch_options_build_browsable_dataset_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    images: list[str] = []
    for index, color in enumerate(((0, 100, 200), (80, 100, 200), (160, 100, 200))):
        image_path = tmp_path / f"test_image_{index}.jpg"
        Image.new("RGB", (80, 60), color=color).save(image_path, "JPEG")
        images.append(str(image_path))

    datasets = {
        "test_set_1": images[:2],
        "test_set_2": [images[2]],
    }
    run_call: dict[str, Any] = {}
    responses: dict[str, Any] = {}

    def _run_app(app: object, *, host: str, port: int, log_level: str) -> None:
        run_call.update({"host": host, "port": port, "log_level": log_level})
        with TestClient(app) as client:
            responses["health"] = client.get("/health")
            responses["root"] = client.get("/folders", params={"path": "/"})
            responses["dataset"] = client.get("/folders", params={"path": "/test_set_1"})
            responses["thumb"] = client.get(
                "/thumb",
                params={"path": "/test_set_1/test_image_0.jpg"},
            )

    monkeypatch.setattr("uvicorn.run", _run_app)

    lenslet.launch(
        datasets,
        lenslet.LaunchOptions(blocking=True, port=7072, verbose=True),
    )

    assert run_call == {"host": "127.0.0.1", "port": 7072, "log_level": "info"}
    assert responses["health"].status_code == 200
    health = responses["health"].json()
    assert health["ok"] is True
    assert health["mode"] == "dataset"
    assert set(health["datasets"]) == set(datasets)
    assert responses["root"].status_code == 200
    assert responses["dataset"].status_code == 200
    assert {item["name"] for item in responses["root"].json()["folders"]} == set(datasets)
    assert len(responses["dataset"].json()["items"]) == 2
    assert responses["thumb"].status_code == 200
    assert responses["thumb"].headers["content-type"] == "image/webp"
