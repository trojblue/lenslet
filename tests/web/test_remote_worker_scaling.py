from __future__ import annotations

import lenslet.storage.table as table_mod
from lenslet.storage.table import TableStorage


def _make_storage() -> TableStorage:
    # Use a remote-looking path and skip indexing to avoid network calls.
    return TableStorage([{"path": "http://example.com/a.jpg"}], skip_indexing=True)


def test_effective_remote_workers_scales_with_cpu(monkeypatch) -> None:
    storage = _make_storage()

    monkeypatch.setattr(table_mod.os, "cpu_count", lambda: 80)
    assert storage._effective_remote_workers(total=200) == 80

    monkeypatch.setattr(table_mod.os, "cpu_count", lambda: 4)
    assert storage._effective_remote_workers(total=200) == storage.REMOTE_DIM_WORKERS

    monkeypatch.setattr(table_mod.os, "cpu_count", lambda: 512)
    # Still respect both the max cap and the total work available.
    assert storage._effective_remote_workers(total=50) == 50

