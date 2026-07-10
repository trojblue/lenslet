from __future__ import annotations

import gzip
import json
import logging
import os
from pathlib import Path

import pytest

from lenslet.atomic_write import (
    atomic_write_gzip_json,
    atomic_write_json,
    atomic_write_path,
)


def _temp_files_for(path: Path) -> list[Path]:
    return list(path.parent.glob(f".{path.name}.*.tmp*"))


def test_atomic_write_json_creates_parent_and_cleans_temp(tmp_path: Path) -> None:
    path = tmp_path / "state" / "views.json"

    atomic_write_json(path, {"b": 1, "a": 2}, indent=2, sort_keys=True)

    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 2, "b": 1}
    assert _temp_files_for(path) == []


def test_atomic_write_path_keeps_existing_file_when_writer_fails(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text("old", encoding="utf-8")

    def _fail_after_temp_write(tmp_path: Path) -> None:
        tmp_path.write_text("new", encoding="utf-8")
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        atomic_write_path(path, _fail_after_temp_write)

    assert path.read_text(encoding="utf-8") == "old"
    assert _temp_files_for(path) == []


def test_atomic_write_path_uses_requested_temp_suffix(tmp_path: Path) -> None:
    path = tmp_path / "matrix.npz"
    seen: list[Path] = []

    def _write(tmp_path: Path) -> None:
        seen.append(tmp_path)
        tmp_path.write_bytes(b"payload")

    atomic_write_path(path, _write, suffix=".tmp.npz")

    assert path.read_bytes() == b"payload"
    assert seen
    assert seen[0].name.endswith(".tmp.npz")
    assert _temp_files_for(path) == []


def test_atomic_write_gzip_json_round_trips_payload(tmp_path: Path) -> None:
    path = tmp_path / "window.json.gz"
    payload = {"scope_path": "/", "items": [{"path": "/a.jpg"}]}

    atomic_write_gzip_json(path, payload, separators=(",", ":"), sort_keys=True)

    with gzip.open(path, "rt", encoding="utf-8") as handle:
        assert json.load(handle) == payload
    assert _temp_files_for(path) == []


def test_atomic_write_logs_directory_fsync_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = tmp_path / "state.json"
    fsync_calls = 0
    fake_dir_fd = 987654
    real_open = os.open
    real_close = os.close

    def _open_directory_for_fsync(path_arg, flags, *args, **kwargs):
        if Path(path_arg).is_dir():
            return fake_dir_fd
        return real_open(path_arg, flags, *args, **kwargs)

    def _close_fake_directory(fd: int) -> None:
        if fd == fake_dir_fd:
            return
        real_close(fd)

    def _fail_directory_fsync(_fd: int) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        if fsync_calls == 2:
            raise OSError("directory sync failed")

    monkeypatch.setattr("lenslet.atomic_write.os.open", _open_directory_for_fsync)
    monkeypatch.setattr("lenslet.atomic_write.os.close", _close_fake_directory)
    monkeypatch.setattr("lenslet.atomic_write.os.fsync", _fail_directory_fsync)

    with caplog.at_level(logging.WARNING, logger="lenslet.atomic_write"):
        atomic_write_json(path, {"ok": True})

    assert json.loads(path.read_text(encoding="utf-8")) == {"ok": True}
    assert "Could not fsync atomic write directory" in caplog.text
    assert "directory sync failed" in caplog.text
