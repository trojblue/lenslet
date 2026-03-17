from __future__ import annotations

from pathlib import Path

import pytest

from lenslet.workspace import Workspace


def test_workspace_for_parquet_uses_sidecar_and_cache_paths(tmp_path: Path) -> None:
    parquet_path = tmp_path / "items.parquet"
    workspace = Workspace.for_parquet(parquet_path, can_write=True)

    assert workspace.views_path == Path(f"{parquet_path}.lenslet.json")
    assert workspace.thumb_cache_dir() == tmp_path / "items.parquet.cache" / "thumbs"
    assert workspace.browse_cache_dir() == tmp_path / "items.parquet.cache" / "browse-cache"
    assert workspace.embedding_cache_dir() == tmp_path / "items.parquet.cache" / "embeddings_cache"
    assert workspace.og_cache_dir() == tmp_path / "items.parquet.cache" / "og-cache"
    assert workspace.labels_log_path() == tmp_path / "items.parquet.lenslet.labels.log.jsonl"
    assert workspace.labels_snapshot_path() == tmp_path / "items.parquet.lenslet.labels.snapshot.json"


def test_workspace_views_round_trip(tmp_path: Path) -> None:
    workspace = Workspace(root=tmp_path / ".lenslet", can_write=True)

    assert workspace.load_views() == {"version": 1, "views": []}

    payload = {
        "version": 2,
        "views": [
            {"id": "alpha", "name": "Alpha", "pool": {"kind": "folder", "path": "/shots"}},
        ],
    }
    workspace.write_views(payload)

    assert workspace.views_path is not None and workspace.views_path.exists()
    assert workspace.load_views() == payload


def test_workspace_labels_snapshot_round_trip(tmp_path: Path) -> None:
    workspace = Workspace(root=tmp_path / ".lenslet", can_write=True)
    payload = {
        "version": 1,
        "last_event_id": 7,
        "items": {
            "/shots/first.jpg": {
                "tags": ["picked"],
                "notes": "keep",
                "star": 5,
                "version": 3,
                "updated_at": "2026-03-17T00:00:00+00:00",
                "updated_by": "tester",
            }
        },
    }

    workspace.write_labels_snapshot(payload)

    assert workspace.labels_snapshot_path() is not None
    assert workspace.read_labels_snapshot() == payload


def test_workspace_labels_log_compaction_keeps_newer_entries(tmp_path: Path) -> None:
    workspace = Workspace(root=tmp_path / ".lenslet", can_write=True)

    workspace.append_labels_log({"id": 1, "path": "/shots/first.jpg", "version": 2})
    workspace.append_labels_log({"id": 2, "path": "/shots/second.jpg", "version": 4})

    assert [entry["id"] for entry in workspace.read_labels_log()] == [1, 2]
    assert workspace.compact_labels_log(last_event_id=1, max_bytes=1) is True
    assert workspace.read_labels_log() == [{"id": 2, "path": "/shots/second.jpg", "version": 4}]


def test_workspace_read_only_write_operations_raise_permission_error(tmp_path: Path) -> None:
    workspace = Workspace.for_dataset(str(tmp_path / "gallery"), can_write=False)

    with pytest.raises(PermissionError):
        workspace.write_views({"version": 1, "views": []})

    with pytest.raises(PermissionError):
        workspace.write_labels_snapshot({"version": 1, "last_event_id": 1, "items": {}})

    with pytest.raises(PermissionError):
        workspace.append_labels_log({"id": 1})


def test_temp_workspace_key_is_stable_for_same_dataset_root(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    stable_a = Workspace.for_temp_dataset(dataset_root)
    stable_b = Workspace.for_temp_dataset(dataset_root / ".." / "dataset")
    other = Workspace.for_temp_dataset(tmp_path / "other")

    assert stable_a.root == stable_b.root
    assert stable_a.root != other.root
    assert stable_a.is_temp_workspace() is True
