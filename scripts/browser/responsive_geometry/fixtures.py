from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any


class ResponsiveGeometryFixtureError(RuntimeError):
    """Raised when responsive geometry fixtures cannot be generated."""


FIXTURE_METRIC_NAMES = (
    "quality_score",
    "aesthetic_score",
    "sharpness",
    "composition_balance",
    "color_harmony",
    "detail_density",
    "noise_penalty",
    "subject_confidence",
    "background_complexity",
    "prompt_alignment",
    "texture_consistency",
    "edge_integrity",
    "lighting_stability",
    "long_metric_name_for_selected_summary_stress",
)


def build_fixture_dataset(root: Path) -> None:
    payload = build_png_payload()
    rows: list[dict[str, Any]] = []
    for folder in ("alpha", "beta"):
        for idx in range(4):
            filename = (
                f"{folder}_source_path_with_unbroken_metadata_identifier_{idx:02d}_abcdef0123456789.png"
                if idx == 0
                else f"{folder}_{idx:02d}.png"
            )
            path = root / folder / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            rows.append(
                {
                    "path": f"{folder}/{filename}",
                    "metrics": build_fixture_metrics(folder=folder, index=idx),
                }
            )
    write_fixture_parquet(root / "items.parquet", rows)


def build_png_payload() -> bytes:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - project dependency guard
        raise ResponsiveGeometryFixtureError(
            "Pillow is required for responsive geometry fixtures"
        ) from exc
    buffer = BytesIO()
    Image.new("RGB", (1600, 1200), color=(44, 88, 132)).save(buffer, format="PNG")
    return buffer.getvalue()


def build_fixture_metrics(*, folder: str, index: int) -> dict[str, float]:
    prefix = 0.1 if folder == "alpha" else 0.6
    return {
        name: round(prefix + (index * 0.03) + (metric_index * 0.011), 6)
        for metric_index, name in enumerate(FIXTURE_METRIC_NAMES)
    }


def write_fixture_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - project dependency guard
        raise ResponsiveGeometryFixtureError(
            "pyarrow is required for responsive geometry fixtures"
        ) from exc

    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)


def scenario_storage() -> dict[str, str]:
    return {
        "leftOpen": "1",
        "rightOpen": "1",
        "leftW.shared": "760",
        "rightW": "900",
    }


def seed_storage_script(storage: dict[str, str]) -> str:
    return f"""{{
      localStorage.clear();
      const values = {json.dumps(storage)};
      for (const [key, value] of Object.entries(values)) {{
        localStorage.setItem(key, value);
      }}
    }}"""
