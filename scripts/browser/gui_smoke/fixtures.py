from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image


def build_fixture_dataset(root: Path) -> None:
    payload = _build_jpeg_payload()
    alpha_count = 1_600
    beta_count = 1_200
    tree_dirs = 90

    for idx in range(alpha_count):
        _write_image(root / "alpha" / f"alpha_{idx:04d}.jpg", payload)
    for idx in range(beta_count):
        _write_image(root / "beta" / f"beta_{idx:04d}.jpg", payload)
    for idx in range(tree_dirs):
        _write_image(root / f"tree_{idx:03d}" / f"tree_{idx:03d}_sample.jpg", payload)


def _build_jpeg_payload() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (24, 18), color=(44, 88, 132)).save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def _write_image(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
