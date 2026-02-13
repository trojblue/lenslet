from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from lenslet.server import create_app, create_app_from_datasets, create_app_from_table
from lenslet.server_models import MAX_EXPORT_COMPARISON_PATHS_V2
from lenslet.storage.memory import MemoryStorage


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (12, 9), color=(24, 96, 148)).save(path, format="JPEG")


def _wait_for_indexing_state(
    client: TestClient,
    target: str,
    *,
    timeout: float = 2.0,
) -> dict:
    deadline = time.monotonic() + timeout
    last_payload: dict = {}
    while time.monotonic() < deadline:
        payload = client.get("/health").json().get("indexing", {})
        last_payload = payload
        if payload.get("state") == target:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for indexing state={target}; last={last_payload!r}")


def test_memory_health_reports_running_then_ready_indexing_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_image(tmp_path / "gallery" / "a.jpg")
    _make_image(tmp_path / "gallery" / "b.jpg")

    original_build_index = MemoryStorage._build_index
    started = threading.Event()
    release = threading.Event()

    def _blocked_build_index(self: MemoryStorage, path: str, *, lightweight: bool = False):
        started.set()
        if not release.wait(timeout=2.0):
            raise RuntimeError("test timeout waiting to release index build")
        return original_build_index(self, path, lightweight=lightweight)

    monkeypatch.setattr(MemoryStorage, "_build_index", _blocked_build_index)

    app = create_app(str(tmp_path))
    with TestClient(app) as client:
        assert started.wait(timeout=1.0)
        running = client.get("/health").json()["indexing"]
        assert running["state"] == "running"
        assert running["scope"] == "/"
        assert running.get("generation")
        assert running.get("started_at")
        assert "finished_at" not in running

        release.set()
        ready = _wait_for_indexing_state(client, "ready")
        assert ready["scope"] == "/"
        assert ready.get("generation") == running.get("generation")
        assert ready.get("started_at")
        assert ready.get("finished_at")
        assert "error" not in ready


def test_memory_indexing_listener_receives_running_then_ready(
    tmp_path: Path,
) -> None:
    _make_image(tmp_path / "gallery" / "a.jpg")
    _make_image(tmp_path / "gallery" / "b.jpg")

    events: list[dict] = []
    app = create_app(str(tmp_path), indexing_listener=events.append)
    with TestClient(app) as client:
        _wait_for_indexing_state(client, "ready")

    states = [event.get("state") for event in events]
    assert "running" in states
    assert "ready" in states
    assert states.index("running") < states.index("ready")


def test_memory_health_reports_error_when_warm_index_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_image(tmp_path / "broken.jpg")

    def _failing_build_index(self: MemoryStorage, path: str, *, lightweight: bool = False):
        _ = self
        _ = path
        _ = lightweight
        raise RuntimeError("forced warm index failure")

    monkeypatch.setattr(MemoryStorage, "_build_index", _failing_build_index)

    app = create_app(str(tmp_path))
    with TestClient(app) as client:
        errored = _wait_for_indexing_state(client, "error")

    assert errored["scope"] == "/"
    assert errored.get("generation")
    assert "forced warm index failure" in errored.get("error", "")
    assert errored.get("started_at")
    assert errored.get("finished_at")


def test_memory_indexing_listener_receives_error_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _make_image(tmp_path / "broken.jpg")

    def _failing_build_index(self: MemoryStorage, path: str, *, lightweight: bool = False):
        _ = self
        _ = path
        _ = lightweight
        raise RuntimeError("forced warm index failure")

    monkeypatch.setattr(MemoryStorage, "_build_index", _failing_build_index)
    events: list[dict] = []

    app = create_app(str(tmp_path), indexing_listener=events.append)
    with TestClient(app) as client:
        _wait_for_indexing_state(client, "error")

    states = [event.get("state") for event in events]
    assert "running" in states
    assert "error" in states
    assert states.index("running") < states.index("error")


@pytest.mark.parametrize(
    "build_app",
    [
        pytest.param(
            lambda root: create_app_from_table(
                [{"path": "/gallery/a.jpg", "source": str(root / "gallery" / "a.jpg")}],
            ),
            id="table",
        ),
        pytest.param(
            lambda root: create_app_from_datasets({"demo": [str(root / "gallery" / "a.jpg")]}),
            id="dataset",
        ),
    ],
)
def test_static_modes_health_report_ready_indexing_state(
    tmp_path: Path,
    build_app,
) -> None:
    _make_image(tmp_path / "gallery" / "a.jpg")
    app = build_app(tmp_path)

    with TestClient(app) as client:
        health = client.get("/health")

    assert health.status_code == 200
    indexing = health.json().get("indexing", {})
    assert indexing["state"] == "ready"
    assert indexing["scope"] == "/"
    assert indexing.get("generation")
    assert indexing.get("started_at")
    assert indexing.get("finished_at")


def test_health_reports_compare_export_capability_contract(tmp_path: Path) -> None:
    _make_image(tmp_path / "gallery" / "a.jpg")
    app = create_app(str(tmp_path))

    with TestClient(app) as client:
        health = client.get("/health")

    assert health.status_code == 200
    compare_export = health.json().get("compare_export", {})
    assert compare_export.get("supported_versions") == [1, 2]
    assert compare_export.get("max_paths_v2") == MAX_EXPORT_COMPARISON_PATHS_V2
