from pathlib import Path

import pytest

from lenslet.storage.base import StorageWriteUnsupportedError
from lenslet.storage.local import LocalStorage
from lenslet.storage.memory import MemoryStorage


def test_read_only_storages_raise_on_raw_write(tmp_path: Path) -> None:
    root = tmp_path / "gallery"
    root.mkdir()

    for storage in (LocalStorage(str(root)), MemoryStorage(str(root))):
        with pytest.raises(StorageWriteUnsupportedError):
            storage.write_bytes("/notes.txt", b"hello")
