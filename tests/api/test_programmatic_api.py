from __future__ import annotations

from typing import Any

import lenslet.api as api
import lenslet.server as server
import pytest


def test_launch_blocking_builds_dataset_app_and_runs_uvicorn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    datasets = {"demo": ["a.jpg"]}
    sentinel_app = object()
    created: dict[str, Any] = {}
    banner_calls: list[dict[str, Any]] = []
    uvicorn_calls: dict[str, Any] = {}

    def _fake_create_app_from_datasets(
        payload: dict[str, list[str]],
        *,
        show_source: bool,
        options,
    ) -> object:
        created["datasets"] = payload
        created["show_source"] = show_source
        created["options"] = options
        return sentinel_app

    def _fake_banner(**kwargs: Any) -> None:
        banner_calls.append(kwargs)

    def _fake_uvicorn_run(app: object, *, host: str, port: int, log_level: str) -> None:
        uvicorn_calls["app"] = app
        uvicorn_calls["host"] = host
        uvicorn_calls["port"] = port
        uvicorn_calls["log_level"] = log_level

    monkeypatch.setattr(server, "create_app_from_datasets", _fake_create_app_from_datasets)
    monkeypatch.setattr(api, "_print_dataset_launch_banner", _fake_banner)
    monkeypatch.setattr("uvicorn.run", _fake_uvicorn_run)

    api.launch(
        datasets,
        blocking=True,
        port=8080,
        thumb_size=512,
        thumb_quality=81,
        show_source=False,
        verbose=True,
    )

    assert created["datasets"] == datasets
    assert created["show_source"] is False
    assert created["options"].thumb_size == 512
    assert created["options"].thumb_quality == 81
    assert uvicorn_calls == {
        "app": sentinel_app,
        "host": "127.0.0.1",
        "port": 8080,
        "log_level": "info",
    }
    assert banner_calls == [
        {
            "datasets": datasets,
            "host": "127.0.0.1",
            "port": 8080,
            "process_id": None,
        }
    ]


def test_launch_table_nonblocking_spawns_process_and_runs_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = [{"path": "gallery/a.jpg", "source": "/tmp/a.jpg"}]
    sentinel_app = object()
    created: dict[str, Any] = {}
    banner_calls: list[dict[str, Any]] = []
    uvicorn_calls: dict[str, Any] = {}
    process_state: dict[str, Any] = {}

    def _fake_create_app_from_table(
        *,
        table: object,
        base_dir: str | None,
        source_column: str | None,
        show_source: bool,
        options,
    ) -> object:
        created["table"] = table
        created["base_dir"] = base_dir
        created["source_column"] = source_column
        created["show_source"] = show_source
        created["options"] = options
        return sentinel_app

    def _fake_banner(**kwargs: Any) -> None:
        banner_calls.append(kwargs)

    def _fake_uvicorn_run(app: object, *, host: str, port: int, log_level: str) -> None:
        uvicorn_calls["app"] = app
        uvicorn_calls["host"] = host
        uvicorn_calls["port"] = port
        uvicorn_calls["log_level"] = log_level

    class _FakeProcess:
        def __init__(self, *, target, daemon: bool):
            process_state["daemon"] = daemon
            self._target = target
            self.pid = 4242

        def start(self) -> None:
            process_state["started"] = True
            self._target()

    monkeypatch.setattr(server, "create_app_from_table", _fake_create_app_from_table)
    monkeypatch.setattr(api, "_print_table_launch_banner", _fake_banner)
    monkeypatch.setattr(api.mp, "Process", _FakeProcess)
    monkeypatch.setattr("uvicorn.run", _fake_uvicorn_run)

    api.launch_table(
        table,
        blocking=False,
        host="0.0.0.0",
        port=9090,
        source_column="source",
        base_dir="/data",
    )

    assert created["table"] == table
    assert created["base_dir"] == "/data"
    assert created["source_column"] == "source"
    assert created["show_source"] is True
    assert created["options"].thumb_size == 256
    assert created["options"].thumb_quality == 70
    assert process_state == {"daemon": False, "started": True}
    assert uvicorn_calls == {
        "app": sentinel_app,
        "host": "0.0.0.0",
        "port": 9090,
        "log_level": "warning",
    }
    assert banner_calls == [
        {
            "table": table,
            "host": "0.0.0.0",
            "port": 9090,
            "source_column": "source",
            "process_id": 4242,
        }
    ]
