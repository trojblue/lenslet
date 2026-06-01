"""Fixture dataset builder for GUI jitter probes."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from PIL import Image, PngImagePlugin

from scripts.browser.gui_jitter.shared import write_bytes_atomic, write_json_atomic


def build_fixture_dataset(root: Path) -> None:
    payload = jpeg_payload()
    for idx in range(12):
        write_image(root / f"sample_{idx:03d}.jpg", payload)
    build_inspector_fixture_images(root)
    write_fixture_items_parquet(root)
    write_fixture_labels_snapshot(root)


def build_inspector_fixture_images(root: Path) -> None:
    write_png_with_metadata(
        root / "quick_00_meta.png",
        itxt_chunks={
            "qfty_meta": json.dumps(
                {
                    "prompt": "alpha prompt",
                    "model": "alpha-model",
                    "lora": {"alpha-lora.safetensors": 0.8},
                }
            )
        },
    )
    write_png_with_metadata(
        root / "quick_01_meta.png",
        itxt_chunks={
            "qfty_meta": json.dumps(
                {
                    "prompt": "beta prompt",
                    "model": "beta-model",
                    "lora": {"beta-lora.safetensors": 1.2},
                }
            )
        },
    )
    write_png_with_metadata(
        root / "quick_02_plain.png",
        text_chunks={"comment": "no quick-view defaults"},
    )
    write_png_with_metadata(
        root / "quick_03_meta.png",
        itxt_chunks={
            "qfty_meta": json.dumps(
                {
                    "prompt": "gamma prompt",
                    "model": "gamma-model",
                    "lora": {"gamma-lora.safetensors": 0.6},
                }
            )
        },
    )


def fixture_image_paths(root: Path) -> list[Path]:
    allowed = {".jpg", ".jpeg", ".png", ".webp"}
    paths = [path for path in root.iterdir() if path.is_file() and path.suffix.lower() in allowed]
    return sorted(paths, key=lambda path: path.name)


def write_fixture_labels_snapshot(root: Path) -> None:
    items: dict[str, Any] = {}
    for idx, image_path in enumerate(fixture_image_paths(root)):
        path = f"/{image_path.name}"
        score = round((idx % 7) / 7.0, 6)
        item = {
            "tags": [],
            "notes": "",
            "star": None,
            "version": 100,
            "updated_at": "",
            "updated_by": "probe",
        }
        item["metrics"] = {
            "probe_score": score,
            "probe_rank": float(idx),
        }
        items[path] = item

    write_json_atomic(
        root / ".lenslet" / "labels.snapshot.json",
        {
            "version": 1,
            "last_event_id": len(items),
            "items": items,
        },
    )


def write_fixture_items_parquet(root: Path) -> None:
    rows: list[dict[str, Any]] = []
    for idx, image_path in enumerate(fixture_image_paths(root)):
        rel_path = image_path.name
        score = round((idx % 7) / 7.0, 6)
        rows.append(
            {
                "path": rel_path,
                "source": str((root / rel_path).resolve()),
                "metrics": {
                    "probe_score": score,
                    "probe_rank": float(idx),
                },
            }
        )
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, root / "items.parquet")


def jpeg_payload() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (48, 32), color=(44, 88, 132)).save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def write_image(path: Path, payload: bytes) -> None:
    write_bytes_atomic(path, payload)


def write_png_with_metadata(
    path: Path,
    *,
    text_chunks: dict[str, str] | None = None,
    itxt_chunks: dict[str, str] | None = None,
) -> None:
    meta = PngImagePlugin.PngInfo()
    for key, value in (text_chunks or {}).items():
        meta.add_text(key, value)
    for key, value in (itxt_chunks or {}).items():
        meta.add_itxt(key, value)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (48, 32), color=(72, 36, 120)).save(path, format="PNG", pnginfo=meta)
