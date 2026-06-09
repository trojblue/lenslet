from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

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


def build_derived_metric_table_fixture(root: Path, row_count: int = 5_006) -> Path:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - runtime dependency guard
        raise RuntimeError("pyarrow is required for derived metric GUI smoke fixtures") from exc

    root.mkdir(parents=True, exist_ok=True)
    payload = _build_jpeg_payload()
    _write_image(root / "shared.jpg", payload)
    rows = _derived_metric_rows(row_count)
    table = pa.table(rows)
    target = root / "items.parquet"
    pq.write_table(table, target)
    return target


def build_backend_browse_filter_table_fixture(root: Path, row_count: int = 1_006) -> Path:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - runtime dependency guard
        raise RuntimeError("pyarrow is required for backend browse filter GUI smoke fixtures") from exc

    root.mkdir(parents=True, exist_ok=True)
    payload = _build_jpeg_payload()
    _write_image(root / "shared.jpg", payload)
    rows = _backend_browse_filter_rows(row_count)
    table = pa.table(rows)
    target = root / "backend_browse_filter.parquet"
    pq.write_table(table, target)
    return target


def _derived_metric_rows(row_count: int) -> dict[str, list[Any]]:
    rows: dict[str, list[Any]] = {
        "image_path": [],
        "path": [],
        "q1": [],
        "q2": [],
        "q3": [],
        "q4": [],
        "q5": [],
        "q6": [],
        "dataset_from": [],
    }
    for idx in range(row_count):
        rows["image_path"].append("shared.jpg")
        rows["path"].append(f"ranked/item_{idx:04d}.jpg")
        if idx == 1:
            q1, q2, q3, dataset_from = 1.0, 1.0, 1.0, "gt"
        elif idx == 2:
            q1, q2, q3, dataset_from = 50.0, 0.0, 0.0, "train"
        else:
            q1 = float((idx % 7) / 10)
            q2 = float((idx % 5) / 10)
            q3 = float((idx % 3) / 10)
            dataset_from = "gt" if idx % 11 == 0 else "train"
        rows["q1"].append(q1)
        rows["q2"].append(q2)
        rows["q3"].append(q3)
        rows["q4"].append(float(idx % 4))
        rows["q5"].append(float(idx % 5))
        rows["q6"].append(float(idx % 6))
        rows["dataset_from"].append(dataset_from)
    return rows


def _backend_browse_filter_rows(row_count: int) -> dict[str, list[Any]]:
    target_indexes = {row_count - 2, row_count - 1}
    rows: dict[str, list[Any]] = {
        "image_path": [],
        "path": [],
        "mtime": [],
        "quality_score": [],
        "source_column": [],
    }
    for idx in range(row_count):
        target = idx in target_indexes
        rows["image_path"].append("shared.jpg")
        rows["path"].append(
            f"backend-query/{'target' if target else 'other'}_{idx:04d}.jpg"
        )
        rows["mtime"].append(1_700_000_000 + (row_count - idx))
        rows["quality_score"].append(float(idx % 10) / 10)
        rows["source_column"].append(
            "v0603_ema14k_image_url" if target else "other_source"
        )
    return rows


def _build_jpeg_payload() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (24, 18), color=(44, 88, 132)).save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def _write_image(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
