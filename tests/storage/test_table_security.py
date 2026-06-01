from pathlib import Path

from lenslet.storage.table import TableStorage


def test_table_storage_disables_local_sources(tmp_path: Path) -> None:
    local_path = tmp_path / "local.jpg"
    local_path.write_bytes(b"fake")

    rows = [
        {"path": str(local_path)},
        {"path": "https://example.com/remote.jpg"},
        {"path": "https://example.com/remote-2.jpg"},
        {"path": "https://example.com/remote-3.jpg"},
    ]

    storage = TableStorage(rows, allow_local=False, skip_indexing=True)

    assert "https://example.com/remote.jpg" in storage._items
    assert "https://example.com/remote-2.jpg" in storage._items
    assert "local.jpg" not in storage._items
