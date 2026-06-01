from __future__ import annotations

from pathlib import Path
from typing import Any

import lenslet.cli.browse as cli_browse
import lenslet.web.app.local as local_app
from lenslet.embeddings.config import EmbeddingConfig
from lenslet.server import BrowseAppOptions, EmbeddingAppOptions
from lenslet.storage.table.launch import TableLaunchNotice, TableLaunchRequest, TableLaunchResult
from lenslet.workspace import Workspace


def _browse_args(**overrides: Any) -> cli_browse.BrowseCliArgs:
    base: dict[str, Any] = {
        "directory": "/tmp/gallery",
        "host": "127.0.0.1",
        "port": None,
        "thumb_size": 256,
        "thumb_quality": 70,
        "source_column": None,
        "path_column": None,
        "base_dir": None,
        "cache_dimensions": False,
        "skip_dimension_probe": True,
        "thumb_cache": True,
        "og_preview": False,
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
    return cli_browse.BrowseCliArgs(**base)


def test_share_banner_and_launch_are_read_only() -> None:
    args = _browse_args(share=True, host="0.0.0.0")
    target = cli_browse.BrowseTarget(
        raw_target="/tmp/gallery",
        target=Path("/tmp/gallery"),
        is_table_file=False,
        is_remote_table=False,
    )

    assert cli_browse._workspace_label_for_banner(args, target) == "shared read-only"
    assert cli_browse._trusted_write_origins_for_browse_launch(args, 7070) == ()


def test_local_browse_launch_keeps_trusted_write_origins() -> None:
    origins = cli_browse._trusted_write_origins_for_browse_launch(_browse_args(), 7070)

    assert origins == (
        "http://127.0.0.1:7070",
        "http://localhost:7070",
        "http://[::1]:7070",
    )


def test_directory_items_parquet_launch_result_passed_to_create_app(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    root = tmp_path / "gallery"
    root.mkdir()
    (root / "items.parquet").write_bytes(b"unused by fake launch")
    sentinel_app = object()
    launch_result = TableLaunchResult(
        storage=object(),
        effective_root=str(root),
        default_root=str(root),
        notices=(TableLaunchNotice(kind="test", message="[lenslet] prepared once"),),
    )
    captured: dict[str, Any] = {}

    def _fake_prepare_table_launch(request: TableLaunchRequest) -> TableLaunchResult:
        captured["request"] = request
        return launch_result

    def _fake_create_local_app(root_path: str, *, options, table_launch=None) -> object:
        captured["root_path"] = root_path
        captured["options"] = options
        captured["table_launch"] = table_launch
        return sentinel_app

    monkeypatch.setattr(cli_browse, "prepare_table_launch", _fake_prepare_table_launch)
    monkeypatch.setattr(local_app, "create_local_app", _fake_create_local_app)

    plan = cli_browse.BrowseLaunchPlan(
        args=_browse_args(directory=str(root), cache_dimensions=False),
        target_info=cli_browse.BrowseTarget(
            raw_target=str(root),
            target=root.resolve(),
            is_table_file=False,
            is_remote_table=False,
        ),
        port=7070,
        dataset_workspace=Workspace.for_dataset(str(root), can_write=True),
        preindex_signature=None,
        embedding_config=EmbeddingConfig(),
        browse_options=BrowseAppOptions(),
        embedding_options=EmbeddingAppOptions(),
        trusted_write_origins=(),
    )
    app = cli_browse._create_browse_app_or_exit(plan)

    assert app is sentinel_app
    request = captured["request"]
    assert isinstance(request, TableLaunchRequest)
    assert request.parquet_path == root.resolve() / "items.parquet"
    assert request.base_dir == str(root.resolve())
    assert request.cache_dimensions is False
    assert captured["table_launch"] is launch_result
    assert captured["root_path"] == str(root.resolve())
    assert capsys.readouterr().out.count("[lenslet] prepared once") == 1
