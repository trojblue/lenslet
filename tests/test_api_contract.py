from __future__ import annotations

import lenslet.api as api
import pytest


def test_launch_datasets_rejects_empty_payload() -> None:
    with pytest.raises(ValueError, match="non-empty dict"):
        api.launch_datasets({})


def test_launch_table_rejects_non_table_payload() -> None:
    with pytest.raises(ValueError, match="table-like object"):
        api.launch_table(object())


def test_launch_table_dispatches_table_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_launch_table_mode(**kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(api, "_launch_table_mode", _fake_launch_table_mode)
    table = [{"path": "gallery/a.jpg", "source": "/tmp/a.jpg"}]

    api.launch_table(table, blocking=True, source_column="source", base_dir="/tmp")

    assert captured["table"] == table
    assert captured["blocking"] is True
    assert captured["source_column"] == "source"
    assert captured["base_dir"] == "/tmp"


def test_launch_delegates_to_dataset_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_launch_datasets(*args, **kwargs) -> None:
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(api, "launch_datasets", _fake_launch_datasets)
    datasets = {"demo": ["a.jpg"]}

    api.launch(datasets, blocking=True, port=8080)

    assert captured["args"] == (datasets,)
    assert captured["kwargs"]["blocking"] is True
    assert captured["kwargs"]["port"] == 8080
