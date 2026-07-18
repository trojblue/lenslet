from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

import lenslet.storage.table.launch as table_launch_module
from lenslet.storage.table.launch import (
    ParquetRowFieldProvider,
    TableLaunchRequest,
    prepare_table_launch,
)
from lenslet.storage.table.source_refresh import (
    TableSourceChangedError,
    TableSourceRefreshTracker,
)
from lenslet.storage.table.storage import TableStorage, TableStorageOptions
from lenslet.web.source_monitor import TableSourceMonitor
from lenslet.web.sync.events import EventBroker

pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")


def test_local_source_tracker_detects_one_atomic_replacement(tmp_path: Path) -> None:
    source = tmp_path / "items.parquet"
    source.write_bytes(b"old-table")
    tracker = TableSourceRefreshTracker.for_local_file(source)

    current = tracker.status()
    assert current.state == "current"
    assert current.generation is not None
    assert tracker.poll() == (current, False)

    replacement = tmp_path / "replacement.parquet"
    replacement.write_bytes(b"new-table-with-different-content")
    os.replace(replacement, source)

    changed, transitioned = tracker.poll()
    assert transitioned is True
    assert changed.state == "restart-required"
    assert changed.generation == current.generation
    assert changed.message == "The source table changed; restart Lenslet to load the new snapshot."
    assert str(tmp_path) not in str(changed.event_payload())
    assert tracker.poll() == (changed, False)


def test_local_source_tracker_reports_missing_source_without_path_leak(tmp_path: Path) -> None:
    source = tmp_path / "items.parquet"
    source.write_bytes(b"table")
    tracker = TableSourceRefreshTracker.for_local_file(source)
    source.unlink()

    status, transitioned = tracker.poll()

    assert transitioned is True
    assert status.state == "restart-required"
    assert status.message == "The source table is unavailable; restart Lenslet after restoring it."
    assert str(source) not in str(status.event_payload())


def test_unversioned_source_is_explicitly_restart_required() -> None:
    tracker = TableSourceRefreshTracker.restart_required(
        "This table source cannot be checked safely; restart Lenslet to reload it."
    )

    status = tracker.status()
    assert status.state == "restart-required"
    assert status.generation is None
    assert tracker.poll() == (status, False)
    assert tracker.is_pollable() is False


def test_local_source_tracker_detects_repointed_symlink(tmp_path: Path) -> None:
    first = tmp_path / "first.parquet"
    second = tmp_path / "second.parquet"
    first.write_bytes(b"first")
    second.write_bytes(b"second-source")
    source = tmp_path / "current.parquet"
    source.symlink_to(first.name)
    tracker = TableSourceRefreshTracker.for_local_file(source)

    source.unlink()
    source.symlink_to(second.name)
    status, transitioned = tracker.poll()

    assert transitioned is True
    assert status.state == "restart-required"


def test_uncached_row_group_rejects_changed_source_generation(tmp_path: Path) -> None:
    source = tmp_path / "items.parquet"
    pq.write_table(
        pa.table({"field": ["old-0", "old-1"]}),
        source,
        row_group_size=1,
    )
    provider = ParquetRowFieldProvider(source, ("field",))
    tracker = TableSourceRefreshTracker.for_local_file(source)
    provider.set_source_refresh_tracker(tracker)
    assert provider(0) == {"field": "old-0"}

    pq.write_table(
        pa.table({"field": ["new-0", "new-1"]}),
        source,
        row_group_size=1,
    )

    assert provider(0) == {"field": "old-0"}
    with pytest.raises(TableSourceChangedError, match="restart Lenslet"):
        provider(1)
    status, transitioned = tracker.poll()
    assert status.state == "restart-required"
    assert transitioned is True


def test_monitor_does_not_start_for_untracked_or_permanent_source() -> None:
    async def exercise() -> None:
        untracked = TableStorage(
            [{"source": "https://example.test/a.jpg", "path": "a.jpg"}],
            options=TableStorageOptions(skip_dimension_probe=True),
        )
        untracked_monitor = TableSourceMonitor(untracked, EventBroker())
        untracked_monitor.start()
        assert untracked_monitor._task is None

        permanent = TableStorage(
            [{"source": "https://example.test/a.jpg", "path": "a.jpg"}],
            options=TableStorageOptions(
                skip_dimension_probe=True,
                source_refresh_tracker=TableSourceRefreshTracker.restart_required("restart"),
            ),
        )
        permanent_monitor = TableSourceMonitor(permanent, EventBroker())
        permanent_monitor.start()
        assert permanent_monitor._task is None

    asyncio.run(exercise())


def test_table_launch_rejects_source_replacement_during_build(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "items.parquet"
    replacement = tmp_path / "replacement.parquet"
    pq.write_table(
        pa.table({
            "source": ["https://example.test/old.jpg"],
            "path": ["old.jpg"],
        }),
        source,
    )
    pq.write_table(
        pa.table({
            "source": ["https://example.test/new.jpg"],
            "path": ["new.jpg"],
        }),
        replacement,
    )
    real_load = table_launch_module.load_parquet_table
    replaced = False

    def load_then_replace(path: str, columns: list[str] | None = None):
        nonlocal replaced
        table = real_load(path, columns=columns)
        if not replaced:
            replaced = True
            os.replace(replacement, source)
        return table

    monkeypatch.setattr(table_launch_module, "load_parquet_table", load_then_replace)

    with pytest.raises(TableSourceChangedError, match="restart Lenslet"):
        prepare_table_launch(
            TableLaunchRequest(
                parquet_path=source,
                base_dir=None,
                source_column="source",
                path_column="path",
                cache_dimensions=False,
                skip_dimension_probe=True,
            )
        )


def test_dimension_rewrite_rejects_replacement_before_recapture(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "items.parquet"
    replacement = tmp_path / "replacement.parquet"
    pq.write_table(
        pa.table({
            "source": ["https://example.test/old.jpg"],
            "path": ["old.jpg"],
        }),
        source,
    )
    pq.write_table(
        pa.table({
            "source": [
                "https://example.test/new-a.jpg",
                "https://example.test/new-b.jpg",
            ],
            "path": ["new-a.jpg", "new-b.jpg"],
        }),
        replacement,
    )
    monkeypatch.setattr(TableStorage, "_source_header_is_image", lambda self, value: True)
    monkeypatch.setattr(
        TableStorage,
        "_get_remote_header_info",
        lambda self, url, name: ((8, 6), 128),
    )
    real_cache = table_launch_module.cache_missing_dimensions

    def cache_then_replace(**kwargs):
        result = real_cache(**kwargs)
        assert result.rewritten_table is not None
        os.replace(replacement, source)
        return result

    monkeypatch.setattr(table_launch_module, "cache_missing_dimensions", cache_then_replace)

    with pytest.raises(TableSourceChangedError, match="restart Lenslet"):
        prepare_table_launch(
            TableLaunchRequest(
                parquet_path=source,
                base_dir=None,
                source_column="source",
                path_column="path",
                cache_dimensions=True,
                skip_dimension_probe=True,
            )
        )
