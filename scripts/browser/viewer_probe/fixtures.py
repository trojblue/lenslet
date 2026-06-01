from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

FIXTURE_IMAGE_QUALITY = 88


def build_fixture_dataset(root: Path) -> None:
    specs = [
        ("alpha/alpha_00_wide.jpg", (1800, 1200), (48, 90, 140)),
        ("alpha/alpha_01_tall.jpg", (900, 1600), (122, 74, 150)),
        ("alpha/alpha_02_square.jpg", (1200, 1200), (65, 128, 104)),
        ("beta/beta_00_wide.jpg", (1600, 900), (154, 91, 62)),
        ("beta/beta_01_tall.jpg", (800, 1400), (70, 118, 165)),
        ("beta/beta_02_square.jpg", (1000, 1000), (143, 116, 50)),
    ]
    for index, (relative, size, color) in enumerate(specs):
        write_fixture_image(root / relative, size=size, color=color, label=str(index))


def write_fixture_image(path: Path, *, size: tuple[int, int], color: tuple[int, int, int], label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", size, color=color)
    draw = ImageDraw.Draw(image)
    accent = tuple(min(255, channel + 55) for channel in color)
    draw.rectangle((24, 24, min(size[0] - 24, 420), min(size[1] - 24, 180)), outline=accent, width=8)
    draw.text((48, 52), f"Lenslet probe {label}", fill=(245, 245, 245))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=FIXTURE_IMAGE_QUALITY)
    temp = path.with_suffix(f"{path.suffix}.tmp")
    temp.write_bytes(buffer.getvalue())
    temp.replace(path)
