from __future__ import annotations

import gzip
import json
import logging
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)


def atomic_write_path(
    path: Path,
    writer: Callable[[Path], None],
    *,
    suffix: str = ".tmp",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=suffix,
        dir=path.parent,
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        writer(tmp_path)
        _fsync_file(tmp_path)
        tmp_path.replace(path)
        _fsync_dir(path.parent)
    except BaseException:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def atomic_write_text(path: Path, payload: str, *, encoding: str = "utf-8") -> None:
    def _write(tmp_path: Path) -> None:
        tmp_path.write_text(payload, encoding=encoding)

    atomic_write_path(path, _write)


def atomic_write_json(
    path: Path,
    payload: Any,
    *,
    indent: int | None = 2,
    sort_keys: bool = True,
    separators: tuple[str, str] | None = None,
    ensure_ascii: bool = True,
) -> None:
    serialized = json.dumps(
        payload,
        indent=indent,
        sort_keys=sort_keys,
        separators=separators,
        ensure_ascii=ensure_ascii,
    )
    atomic_write_text(path, serialized)


def atomic_write_gzip_json(
    path: Path,
    payload: Any,
    *,
    sort_keys: bool = True,
    separators: tuple[str, str] | None = None,
    ensure_ascii: bool = True,
) -> None:
    def _write(tmp_path: Path) -> None:
        with gzip.open(tmp_path, "wt", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                sort_keys=sort_keys,
                separators=separators,
                ensure_ascii=ensure_ascii,
            )

    atomic_write_path(path, _write, suffix=".tmp.gz")


def _fsync_file(path: Path) -> None:
    fd = os.open(os.fspath(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_dir(path: Path) -> None:
    flags = getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(os.fspath(path), os.O_RDONLY | flags)
    except OSError as exc:
        _LOGGER.warning("Could not open atomic write directory %s for fsync: %s", path, exc)
        return
    try:
        os.fsync(fd)
    except OSError as exc:
        _LOGGER.warning("Could not fsync atomic write directory %s: %s", path, exc)
    finally:
        os.close(fd)
