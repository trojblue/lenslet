from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq

from lenslet.cli.hf_table import (
    load_hf_parquet_table,
    parse_hf_table_uri,
    select_hf_parquet_files,
)


def _write_parquet(path: Path, data: dict[str, list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(data), path)


def test_parse_hf_table_uri_supports_dataset_prefix_path_and_revision() -> None:
    parsed = parse_hf_table_uri("hf://datasets/owner/repo@abc123/data/train.parquet")

    assert parsed.repo_id == "owner/repo"
    assert parsed.revision == "abc123"
    assert parsed.path_in_repo == "data/train.parquet"


def test_select_hf_parquet_files_defaults_to_all_parquet_files() -> None:
    files = [
        "README.md",
        "data/train-00001.parquet",
        "data/train-00000.parquet",
        "notes/example.json",
    ]

    assert select_hf_parquet_files(files, "") == (
        "data/train-00000.parquet",
        "data/train-00001.parquet",
    )
    assert select_hf_parquet_files(files, "data") == (
        "data/train-00000.parquet",
        "data/train-00001.parquet",
    )


def test_load_hf_parquet_table_reads_shards_without_datasets_cast(
    monkeypatch,
    tmp_path: Path,
) -> None:
    shard_a = tmp_path / "train-00000.parquet"
    shard_b = tmp_path / "train-00001.parquet"
    _write_parquet(
        shard_a,
        {
            "s3key": ["https://example.test/r2/a"],
            "path": ["https://example.test/r2/a"],
            "width": [10],
            "score": [0.5],
        },
    )
    _write_parquet(
        shard_b,
        {
            "s3key": ["https://example.test/r2/b"],
            "path": ["https://example.test/r2/b"],
            "width": [12],
            "extra_label": ["kept"],
        },
    )
    calls: list[tuple[str, str | None, str | None, str | None]] = []

    class _FakeHfApi:
        def list_repo_files(self, repo_id, *, repo_type=None, revision=None):
            calls.append(("list", repo_id, repo_type, revision))
            return [
                "README.md",
                "data/train-00000.parquet",
                "data/train-00001.parquet",
            ]

    def _fake_download(repo_id, filename, *, repo_type=None, revision=None):
        calls.append((filename, repo_id, repo_type, revision))
        return {
            "data/train-00000.parquet": str(shard_a),
            "data/train-00001.parquet": str(shard_b),
        }[filename]

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(HfApi=_FakeHfApi, hf_hub_download=_fake_download),
    )

    result = load_hf_parquet_table("hf://owner/repo@rev1")

    assert result.source_column == "s3key"
    assert result.table.num_rows == 2
    assert "score" in result.table.schema.names
    assert "extra_label" in result.table.schema.names
    assert result.table["score"].to_pylist() == [0.5, None]
    assert result.table["extra_label"].to_pylist() == [None, "kept"]
    assert calls == [
        ("list", "owner/repo", "dataset", "rev1"),
        ("data/train-00000.parquet", "owner/repo", "dataset", "rev1"),
        ("data/train-00001.parquet", "owner/repo", "dataset", "rev1"),
    ]


def test_load_hf_parquet_table_prefers_image_url_over_page_source_url(
    monkeypatch,
    tmp_path: Path,
) -> None:
    shard = tmp_path / "train-00000.parquet"
    _write_parquet(
        shard,
        {
            "source_url": [
                "https://example.test/report.html",
                "https://example.test/report.html",
            ],
            "image_url": [
                "https://images.example.test/a.webp",
                "https://images.example.test/r2/encoded-image-key",
            ],
            "width": [10, 12],
            "height": [8, 9],
        },
    )

    class _FakeHfApi:
        def list_repo_files(self, repo_id, *, repo_type=None, revision=None):
            assert repo_id == "owner/repo"
            assert repo_type == "dataset"
            assert revision == "main"
            return ["data/train-00000.parquet"]

    def _fake_download(repo_id, filename, *, repo_type=None, revision=None):
        assert (repo_id, filename, repo_type, revision) == (
            "owner/repo",
            "data/train-00000.parquet",
            "dataset",
            "main",
        )
        return str(shard)

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(HfApi=_FakeHfApi, hf_hub_download=_fake_download),
    )

    result = load_hf_parquet_table("hf://owner/repo")

    assert result.source_column == "image_url"
