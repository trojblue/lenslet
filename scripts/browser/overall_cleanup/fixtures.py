from __future__ import annotations

import os
import tempfile
from io import BytesIO
from pathlib import Path

from PIL import Image


def build_fixture_dataset(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    colors = (
        (215, 80, 75),
        (74, 150, 92),
        (64, 112, 202),
        (222, 171, 66),
        (126, 91, 180),
        (42, 164, 176),
        (202, 96, 148),
        (86, 86, 96),
    )
    sizes = (
        (1000, 100),
        (100, 100),
        (100, 100),
        (100, 100),
        (400, 100),
        (100, 800),
        (160, 320),
        (1600, 1200),
    )
    for idx, (color, size) in enumerate(zip(colors, sizes)):
        path = root / f"cleanup_fixture_{idx:02d}.png"
        write_bytes_atomic(path, _png_payload(size=size, color=color))
    nested = root / "cleanup_nested"
    nested.mkdir(exist_ok=True)
    write_bytes_atomic(
        nested / "cleanup_fixture_nested.png",
        _png_payload(size=(640, 360), color=(118, 142, 62)),
    )


def _png_payload(*, size: tuple[int, int], color: tuple[int, int, int]) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color=color).save(buffer, format="PNG")
    return buffer.getvalue()


def write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        tmp_path.replace(path)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise


def write_text_atomic(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        tmp_path.replace(path)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise
