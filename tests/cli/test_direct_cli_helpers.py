from __future__ import annotations

import os
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest

import lenslet.cli.browse_args as cli_browse_args
import lenslet.cli.common as cli_common
import lenslet.cli.rank as cli_rank
import lenslet.degraded as degraded

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_cli_import_probe(script: str) -> None:
    env = os.environ.copy()
    src_path = str(REPO_ROOT / "src")
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{src_path}{os.pathsep}{existing_pythonpath}" if existing_pythonpath else src_path
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout


def test_cli_common_find_available_port_rejects_empty_range() -> None:
    with pytest.raises(RuntimeError, match="No available port"):
        cli_common._find_available_port("127.0.0.1", start_port=7070, max_tries=0)


def test_browse_cli_import_keeps_optional_runtime_dependencies_lazy() -> None:
    _run_cli_import_probe(
        """
import sys
import lenslet.cli.browse as browse

assert hasattr(browse, "_main_browse")
for name in (
    "unibox",
    "uvicorn",
    "lenslet.embeddings.embedder",
    "lenslet.storage.local.preindex",
    "lenslet.web.og.rendering",
    "pyarrow",
    "pyarrow.parquet",
):
    assert name not in sys.modules, name
pil_modules = [name for name in sys.modules if name == "PIL" or name.startswith("PIL.")]
assert pil_modules == [], pil_modules
"""
    )


def test_browse_parser_populates_table_path_column() -> None:
    parser = cli_browse_args._build_browse_parser()
    namespace = parser.parse_args(
        [
            "/tmp/items.parquet",
            "--source-column",
            "image_uri",
            "--path-column",
            "display_path",
        ]
    )

    args = cli_browse_args.BrowseCliArgs.from_namespace(namespace)

    assert args.source_column == "image_uri"
    assert args.path_column == "display_path"


def test_browse_parser_uses_dimension_probe_vocabulary() -> None:
    parser = cli_browse_args._build_browse_parser()
    namespace = parser.parse_args(
        [
            "/tmp/items.parquet",
            "--no-cache-dimensions",
            "--probe-dimensions",
        ]
    )

    args = cli_browse_args.BrowseCliArgs.from_namespace(namespace)

    assert args.dimension_cache == "none"
    assert args.cache_dimensions is False
    assert args.skip_dimension_probe is False


def test_browse_parser_exposes_source_dimension_write_opt_in() -> None:
    parser = cli_browse_args._build_browse_parser()
    namespace = parser.parse_args(["/tmp/items.parquet", "--write-source-dimensions"])

    args = cli_browse_args.BrowseCliArgs.from_namespace(namespace)

    assert args.dimension_cache == "source"
    assert args.cache_dimensions is True


def test_browse_parser_only_exposes_state_changing_embedding_cache_flag() -> None:
    parser = cli_browse_args._build_browse_parser()

    disabled = cli_browse_args.BrowseCliArgs.from_namespace(
        parser.parse_args(["/tmp/items.parquet", "--no-embedding-cache"])
    )

    assert disabled.embedding_cache is False
    with pytest.raises(SystemExit):
        parser.parse_args(["/tmp/items.parquet", "--embedding-cache"])


def test_browse_parser_version_uses_explicit_version_resolver(monkeypatch, capsys) -> None:
    import lenslet.version as version_module

    monkeypatch.setattr(version_module, "get_version", lambda: "9.8.7-test")

    with pytest.raises(SystemExit) as exc_info:
        cli_browse_args._parse_browse_args_or_exit(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out == "lenslet 9.8.7-test\n"


def test_rank_cli_exits_before_server_start_for_missing_dataset(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli_rank._main_rank(["/definitely/missing/ranking.json"])

    assert exc_info.value.code == 1
    assert "dataset file does not exist" in capsys.readouterr().err


def test_degraded_report_returns_structured_notice() -> None:
    stream = StringIO()

    notice = degraded.report_degraded_feature(
        "embedding detection",
        detail="schema unavailable",
        impact="search disabled",
        stream=stream,
    )

    assert notice == degraded.DegradedFeature(
        feature="embedding detection",
        detail="schema unavailable",
        startup_continues=True,
    )
    assert "embedding detection degraded: schema unavailable; search disabled" in stream.getvalue()
