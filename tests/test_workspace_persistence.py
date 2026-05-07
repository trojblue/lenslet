from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from lenslet.web.factory import create_app
from lenslet.web.sync import _load_label_state
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


def test_workspace_read_results_distinguish_missing_and_invalid_views(tmp_path: Path) -> None:
    workspace = Workspace(root=tmp_path / ".lenslet", can_write=True)

    missing = workspace.load_views_result()
    assert missing.status == "missing"
    assert missing.value == {"version": 1, "views": []}

    workspace.ensure()
    assert workspace.views_path is not None
    workspace.views_path.write_text("{invalid json", encoding="utf-8")

    invalid = workspace.load_views_result()
    assert invalid.status == "invalid"
    assert invalid.value == {"version": 1, "views": []}


def test_workspace_read_results_distinguish_missing_and_invalid_snapshot(tmp_path: Path) -> None:
    workspace = Workspace(root=tmp_path / ".lenslet", can_write=True)

    missing = workspace.read_labels_snapshot_result()
    assert missing.status == "missing"
    assert missing.value is None

    workspace.ensure()
    snapshot_path = workspace.labels_snapshot_path()
    assert snapshot_path is not None
    snapshot_path.write_text("{invalid json", encoding="utf-8")

    invalid = workspace.read_labels_snapshot_result()
    assert invalid.status == "invalid"
    assert invalid.value is None


def test_workspace_read_results_report_partial_log_corruption(tmp_path: Path) -> None:
    workspace = Workspace(root=tmp_path / ".lenslet", can_write=True)
    workspace.ensure()
    log_path = workspace.labels_log_path()
    assert log_path is not None
    log_path.write_text(
        "\n".join(
            [
                '{"id":1,"path":"/shots/first.jpg","version":2}',
                "not-json",
                '{"id":2,"path":"/shots/second.jpg","version":3}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = workspace.read_labels_log_result()

    assert result.status == "partial"
    assert result.invalid_entries == 1
    assert [entry["id"] for entry in result.value] == [1, 2]


def test_load_label_state_fails_on_corrupt_workspace_persistence(tmp_path: Path) -> None:
    workspace = Workspace(root=tmp_path / ".lenslet", can_write=True)
    workspace.ensure()
    snapshot_path = workspace.labels_snapshot_path()
    assert snapshot_path is not None
    snapshot_path.write_text("{invalid json", encoding="utf-8")

    class _Storage:
        def ensure_metadata(self, _path: str) -> dict:
            return {"version": 1}

        def set_metadata(self, _path: str, _meta: dict) -> None:
            return None

    with pytest.raises(RuntimeError, match="workspace labels snapshot is unreadable"):
        _load_label_state(_Storage(), workspace)


def test_views_route_fails_when_workspace_views_are_corrupt(tmp_path: Path) -> None:
    root = tmp_path / "gallery"
    root.mkdir()
    Image.new("RGB", (4, 4), color=(32, 64, 128)).save(root / "sample.jpg", format="JPEG")
    views_path = root / ".lenslet" / "views.json"
    views_path.parent.mkdir(parents=True, exist_ok=True)
    views_path.write_text("{invalid json", encoding="utf-8")

    client = TestClient(create_app(str(root)))

    response = client.get("/views")

    assert response.status_code == 500
    assert response.json()["detail"] == "workspace views are unreadable"
