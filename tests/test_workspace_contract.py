from pathlib import Path

from lenslet.workspace import Workspace


def _views_payload(view_id: str) -> dict:
    return {
        "version": 1,
        "views": [
            {
                "id": view_id,
                "name": view_id.title(),
                "pool": {"kind": "folder", "path": "/"},
                "view": {},
            }
        ],
    }


def test_dataset_workspace_persists_views_to_workspace_root(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    dataset_root.mkdir()
    workspace = Workspace.for_dataset(dataset_root, can_write=True)
    payload = _views_payload("dataset-view")

    workspace.write_views(payload)

    assert workspace.views_path == dataset_root / ".lenslet" / "views.json"
    assert workspace.views_path.exists()
    assert workspace.load_views() == payload


def test_parquet_workspace_uses_sidecar_persistence_contract(tmp_path: Path) -> None:
    parquet_path = tmp_path / "outputs" / "items.parquet"
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    parquet_path.write_text("placeholder", encoding="utf-8")
    workspace = Workspace.for_parquet(parquet_path, can_write=True)
    payload = _views_payload("table-view")

    workspace.write_views(payload)

    assert workspace.views_path == Path(f"{parquet_path}.lenslet.json")
    assert workspace.views_path.exists()
    assert workspace.load_views() == payload
    assert workspace.browse_cache_dir() == tmp_path / "outputs" / "items.parquet.cache" / "browse-cache"
    assert workspace.thumb_cache_dir() == tmp_path / "outputs" / "items.parquet.cache" / "thumbs"
    assert workspace.labels_log_path() == tmp_path / "outputs" / "items.parquet.lenslet.labels.log.jsonl"
    assert workspace.labels_snapshot_path() == tmp_path / "outputs" / "items.parquet.lenslet.labels.snapshot.json"


def test_workspace_labels_snapshot_and_log_round_trip(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    dataset_root.mkdir()
    workspace = Workspace.for_dataset(dataset_root, can_write=True)
    snapshot = {
        "version": 1,
        "last_event_id": 2,
        "items": {
            "/sample.jpg": {"notes": "persisted", "star": 4, "tags": ["keep"], "version": 2},
        },
    }
    log_entries = [
        {"id": 1, "type": "item-updated", "path": "/sample.jpg", "notes": "first"},
        {"id": 2, "type": "item-updated", "path": "/sample.jpg", "notes": "persisted"},
    ]

    workspace.write_labels_snapshot(snapshot)
    for entry in log_entries:
        workspace.append_labels_log(entry)

    assert workspace.read_labels_snapshot() == snapshot
    assert workspace.read_labels_log() == log_entries


def test_workspace_compact_labels_log_keeps_entries_newer_than_snapshot(tmp_path: Path) -> None:
    dataset_root = tmp_path / "dataset"
    dataset_root.mkdir()
    workspace = Workspace.for_dataset(dataset_root, can_write=True)
    entries = [
        {"id": 1, "type": "item-updated", "path": "/a.jpg"},
        {"id": 2, "type": "item-updated", "path": "/b.jpg"},
        {"id": 3, "type": "item-updated", "path": "/c.jpg"},
    ]
    for entry in entries:
        workspace.append_labels_log(entry)

    compacted = workspace.compact_labels_log(last_event_id=2, max_bytes=1)

    assert compacted is True
    assert workspace.read_labels_log() == [entries[-1]]
