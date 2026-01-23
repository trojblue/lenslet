from __future__ import annotations

import io
from collections import deque

from PIL import Image, ImageDraw, ImageFont

OG_IMAGE_WIDTH = 1200
OG_IMAGE_HEIGHT = 630
OG_IMAGES_X = 6
OG_IMAGES_Y = 3
OG_PIXELS_PER_IMAGE = 6
OG_TILE_GAP = 2
OG_STYLE = "pixel-grid"


def normalize_path(path: str | None) -> str:
    if not path:
        return "/"
    cleaned = path.strip()
    if not cleaned:
        return "/"
    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned}"
    if len(cleaned) > 1:
        cleaned = cleaned.rstrip("/")
    return cleaned


def sample_paths(storage, path: str | None, count: int) -> list[str]:
    target = normalize_path(path)
    index = _safe_index(storage, target)
    if index is None and target != "/":
        target = "/"
        index = _safe_index(storage, target)
    if index is None:
        return []

    records = _index_records(index)
    if records:
        return [p for _, p in records[:count]]

    records = _subfolder_records(storage, index, target, count)
    if not records:
        return []
    records.sort(key=lambda rec: (-rec[0], rec[1]))
    return [p for _, p in records[:count]]


def subtree_image_count(storage, path: str | None) -> int | None:
    target = normalize_path(path)
    index = _safe_index(storage, target)
    if index is None:
        return None

    total = len(getattr(index, "items", []) or [])
    dirs = getattr(index, "dirs", []) or []
    if not dirs:
        return total

    queue = deque(storage.join(target, name) for name in dirs)
    seen: set[str] = {target}
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        sub_index = _safe_index(storage, current)
        if sub_index is None:
            continue
        total += len(getattr(sub_index, "items", []) or [])
        sub_dirs = getattr(sub_index, "dirs", []) or []
        for name in sub_dirs:
            queue.append(storage.join(current, name))
    return total


def pixel_tile_grid(thumb_bytes: bytes, grid_size: int) -> list[list[tuple[int, int, int]]] | None:
    try:
        with Image.open(io.BytesIO(thumb_bytes)) as im:
            im = im.convert("RGB").resize((grid_size, grid_size), Image.BOX)
            pixels = list(im.getdata())
    except Exception:
        return None
    rows: list[list[tuple[int, int, int]]] = []
    for y in range(grid_size):
        start = y * grid_size
        rows.append(pixels[start:start + grid_size])
    return rows


def render_pixel_mosaic(
    tiles: list[list[list[tuple[int, int, int]]]],
    width: int,
    height: int,
    images_x: int,
    images_y: int,
    pixels_per_image: int,
    gap: int,
    harmonize_strength: float = 0.28,
) -> bytes:
    grid_cols = images_x * pixels_per_image
    grid_rows = images_y * pixels_per_image
    tile_size = max(
        1,
        min(
            (width - gap * (grid_cols - 1)) // grid_cols,
            (height - gap * (grid_rows - 1)) // grid_rows,
        ),
    )

    full_grid_w = tile_size * grid_cols + gap * (grid_cols - 1)
    full_grid_h = tile_size * grid_rows + gap * (grid_rows - 1)
    offset_x = max(0, (width - full_grid_w) // 2)
    offset_y = max(0, (height - full_grid_h) // 2)

    flat_pixels: list[tuple[int, int, int]] = []
    for tile in tiles:
        for row in tile:
            flat_pixels.extend(row)
    tint = _avg_color(flat_pixels)
    bg = _harmonize(tint, (18, 22, 26), 0.6)

    canvas = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(canvas)
    radius = max(1, tile_size // 4)

    for tile_idx in range(images_x * images_y):
        tile = tiles[tile_idx % len(tiles)]
        base_row = (tile_idx // images_x) * pixels_per_image
        base_col = (tile_idx % images_x) * pixels_per_image
        for y in range(pixels_per_image):
            row = tile[y]
            for x in range(pixels_per_image):
                color = _harmonize(row[x], tint, harmonize_strength)
                gx = base_col + x
                gy = base_row + y
                x0 = offset_x + gx * (tile_size + gap)
                y0 = offset_y + gy * (tile_size + gap)
                draw.rounded_rectangle(
                    (x0, y0, x0 + tile_size, y0 + tile_size),
                    radius=radius,
                    fill=color,
                )

    output = io.BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()


def fallback_og_image(label: str, width: int = OG_IMAGE_WIDTH, height: int = OG_IMAGE_HEIGHT) -> bytes:
    bg = (24, 28, 32)
    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)
    text = f"Lenslet • {label}"
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    text_w, text_h = _measure_text(draw, text, font)
    draw.text(
        ((width - text_w) // 2, (height - text_h) // 2),
        text,
        fill=(220, 225, 230),
        font=font,
    )
    output = io.BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()


def _measure_text(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    if hasattr(draw, "textbbox"):
        try:
            left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
            return right - left, bottom - top
        except Exception:
            pass
    if font is not None and hasattr(font, "getbbox"):
        try:
            left, top, right, bottom = font.getbbox(text)
            return right - left, bottom - top
        except Exception:
            pass
    if font is not None and hasattr(font, "getsize"):
        try:
            return font.getsize(text)
        except Exception:
            pass
    if hasattr(draw, "textlength"):
        try:
            width = int(draw.textlength(text, font=font))
            return width, 12
        except Exception:
            pass
    return 0, 0


def _avg_color(pixels: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    if not pixels:
        return (32, 36, 40)
    r = sum(p[0] for p in pixels)
    g = sum(p[1] for p in pixels)
    b = sum(p[2] for p in pixels)
    n = len(pixels)
    return (int(r / n), int(g / n), int(b / n))


def _harmonize(color: tuple[int, int, int], tint: tuple[int, int, int], strength: float) -> tuple[int, int, int]:
    return (
        int(color[0] * (1 - strength) + tint[0] * strength),
        int(color[1] * (1 - strength) + tint[1] * strength),
        int(color[2] * (1 - strength) + tint[2] * strength),
    )


def _index_records(index) -> list[tuple[float, str]]:
    items = getattr(index, "items", [])
    if not items:
        return []
    records: list[tuple[float, str]] = []
    for item in items:
        path = getattr(item, "path", None)
        if not path:
            continue
        mtime = getattr(item, "mtime", 0.0) or 0.0
        records.append((mtime, path))
    records.sort(key=lambda rec: (-rec[0], rec[1]))
    return records


def _safe_index(storage, path: str):
    getter = getattr(storage, "get_index", None)
    if not callable(getter):
        return None
    try:
        return getter(path)
    except Exception:
        return None


def _subfolder_records(storage, index, base_path: str, count: int) -> list[tuple[float, str]]:
    dirs = getattr(index, "dirs", []) or []
    if not dirs:
        return []

    queue = deque()
    for name in dirs:
        queue.append(storage.join(base_path, name))

    records: list[tuple[float, str]] = []
    seen: set[str] = set()
    while queue and len(records) < count:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        sub_index = _safe_index(storage, current)
        if sub_index is None:
            continue
        sub_records = _index_records(sub_index)
        if sub_records:
            records.extend(sub_records)
            if len(records) >= count:
                break
        sub_dirs = getattr(sub_index, "dirs", []) or []
        for name in sub_dirs:
            queue.append(storage.join(current, name))
    return records
