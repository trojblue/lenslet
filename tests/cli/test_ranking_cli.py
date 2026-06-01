from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image
import pytest

import lenslet.cli as cli
import lenslet.ranking.app as ranking_app
import lenslet.server as server


def _make_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (8, 8), color=(50, 100, 150)).save(path, format="JPEG")


def _write_dataset(tmp_path: Path) -> Path:
    _make_image(tmp_path / "images" / "sample.jpg")
    dataset_path = tmp_path / "ranking_dataset.json"
    dataset_path.write_text(
        json.dumps(
            [
                {
                    "instance_id": "1",
                    "images": ["images/sample.jpg"],
                }
            ]
        ),
        encoding="utf-8",
    )
    return dataset_path


def _browse_args(**overrides: Any) -> cli.BrowseCliArgs:
    base: dict[str, Any] = {
        "directory": "/tmp/gallery",
        "host": "127.0.0.1",
        "port": None,
        "thumb_size": 256,
        "thumb_quality": 70,
        "source_column": None,
        "base_dir": None,
        "cache_wh": True,
        "skip_indexing": True,
        "thumb_cache": True,
        "og_preview": True,
        "reload": False,
        "no_write": False,
        "embedding_column": None,
        "embedding_metric": None,
        "embed": False,
        "batch_size": 32,
        "parquet_batch_size": 256,
        "num_workers": 8,
        "embedding_preload": False,
        "embedding_cache": True,
        "embedding_cache_dir": None,
        "verbose": False,
        "share": False,
    }
    base.update(overrides)
    return cli.BrowseCliArgs(**base)


def test_cli_rank_subcommand_dispatch(monkeypatch, tmp_path: Path) -> None:
    dataset_path = _write_dataset(tmp_path)
    captured: dict[str, Any] = {}

    def _fake_create_ranking_app(
        dataset_json_path: str | Path,
        *,
        results_path: str | Path | None = None,
    ) -> object:
        captured["dataset_json_path"] = Path(dataset_json_path)
        captured["results_path"] = results_path
        class _State:
            ranking_results_path = tmp_path / "out" / "results.jsonl"
        class _App:
            state = _State()
        return _App()

    def _fake_uvicorn_run(app, host: str, port: int, reload: bool, log_level: str) -> None:
        captured["uvicorn_app"] = app
        captured["host"] = host
        captured["port"] = port
        captured["reload"] = reload
        captured["log_level"] = log_level

    monkeypatch.setattr(ranking_app, "create_ranking_app", _fake_create_ranking_app)
    monkeypatch.setattr("uvicorn.run", _fake_uvicorn_run)

    cli.main(
        [
            "rank",
            str(dataset_path),
            "--host",
            "127.0.0.1",
            "--port",
            "7099",
            "--reload",
            "--results-path",
            "out/results.jsonl",
        ]
    )

    assert captured["dataset_json_path"] == dataset_path.resolve()
    assert captured["results_path"] == "out/results.jsonl"
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 7099
    assert captured["reload"] is True
    assert captured["log_level"] == "warning"


def test_cli_browse_invocation_still_routes_to_existing_factory(monkeypatch, tmp_path: Path) -> None:
    target_dir = tmp_path / "gallery"
    target_dir.mkdir(parents=True)
    sentinel_app = object()
    captured: dict[str, Any] = {}

    def _fake_create_app(root_path: str, **kwargs) -> object:
        captured["root_path"] = root_path
        captured["kwargs"] = kwargs
        return sentinel_app

    def _fake_uvicorn_run(app, host: str, port: int, reload: bool, log_level: str) -> None:
        captured["uvicorn_app"] = app
        captured["host"] = host
        captured["port"] = port
        captured["reload"] = reload
        captured["log_level"] = log_level

    monkeypatch.setattr(server, "create_app", _fake_create_app)
    monkeypatch.setattr("uvicorn.run", _fake_uvicorn_run)
    monkeypatch.setattr(cli, "_find_available_port", lambda host, start_port=7070: 7070)

    cli.main([str(target_dir)])

    assert captured["root_path"] == str(target_dir.resolve())
    assert captured["uvicorn_app"] is sentinel_app
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 7070
    assert captured["reload"] is False
    assert captured["log_level"] == "warning"


def test_normalize_browse_args_disables_cache_write_for_no_write(
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = _browse_args(no_write=True, cache_wh=True)

    normalized = cli._normalize_browse_args(args)

    assert normalized.cache_wh is False
    assert args.cache_wh is True
    captured = capsys.readouterr()
    assert "--no-write disables parquet caching" in captured.out


def test_cli_browse_reports_factory_init_failure(monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target_dir = tmp_path / "gallery"
    target_dir.mkdir(parents=True)

    def _raise_create_app(root_path: str, **kwargs) -> object:
        _ = root_path, kwargs
        raise RuntimeError("broken startup")

    monkeypatch.setattr(server, "create_app", _raise_create_app)
    monkeypatch.setattr(cli, "_find_available_port", lambda host, start_port=7070: 7070)

    with pytest.raises(SystemExit) as exc_info:
        cli.main([str(target_dir)])

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Error: failed to initialize browse mode: broken startup" in captured.err
