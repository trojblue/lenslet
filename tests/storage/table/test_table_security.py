from pathlib import Path

from lenslet.storage.table import TableStorage, TableStorageOptions


def test_table_storage_disables_local_sources(tmp_path: Path) -> None:
    local_path = tmp_path / "local.jpg"
    local_path.write_bytes(b"fake")

    rows = [
        {"path": str(local_path)},
        {"path": "https://example.com/remote.jpg"},
        {"path": "https://example.com/remote-2.jpg"},
        {"path": "https://example.com/remote-3.jpg"},
    ]

    storage = TableStorage(rows, options=TableStorageOptions(allow_local=False, skip_dimension_probe=True))

    assert storage.exists("example.com/remote.jpg")
    assert storage.exists("example.com/remote-2.jpg")
    assert storage.get_source_path("/example.com/remote.jpg") == "https://example.com/remote.jpg"
    assert not storage.exists("local.jpg")
