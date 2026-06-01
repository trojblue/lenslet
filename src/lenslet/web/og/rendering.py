from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

from .style import (
    OG_IMAGE_HEIGHT,
    OG_IMAGE_WIDTH,
    OG_IMAGES_X,
    OG_IMAGES_Y,
    OG_PIXELS_PER_IMAGE,
    OG_STYLE,
    OG_STYLES,
    OG_TILE_GAP,
    resolve_style,
)

_IMAGE_TILE_ERRORS = (Image.DecompressionBombError, OSError, SyntaxError, TypeError, ValueError)
_FONT_LOAD_ERRORS = (OSError, TypeError, ValueError)
_TEXT_MEASURE_ERRORS = (AttributeError, OSError, TypeError, ValueError)


def pixel_tile_grid(thumb_bytes: bytes, grid_size: int) -> list[list[tuple[int, int, int]]] | None:
    try:
        with Image.open(io.BytesIO(thumb_bytes)) as im:
            im = im.convert("RGB").resize((grid_size, grid_size), Image.BOX)
            pixel_data = (
                im.get_flattened_data()
                if hasattr(im, "get_flattened_data")
                else im.getdata()
            )
            pixels = list(pixel_data)
    except _IMAGE_TILE_ERRORS:
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
    except _FONT_LOAD_ERRORS:
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
    textbbox_size = _measure_with_textbbox(draw, text, font)
    if textbbox_size is not None:
        return textbbox_size
    fontbbox_size = _measure_with_fontbbox(text, font)
    if fontbbox_size is not None:
        return fontbbox_size
    fontsize = _measure_with_fontsize(text, font)
    if fontsize is not None:
        return fontsize
    textlength_size = _measure_with_textlength(draw, text, font)
    if textlength_size is not None:
        return textlength_size
    return 0, 0


def _measure_with_textbbox(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int] | None:
    if not hasattr(draw, "textbbox"):
        return None
    try:
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    except _TEXT_MEASURE_ERRORS:
        return None
    return right - left, bottom - top


def _measure_with_fontbbox(text: str, font) -> tuple[int, int] | None:
    if font is None or not hasattr(font, "getbbox"):
        return None
    try:
        left, top, right, bottom = font.getbbox(text)
    except _TEXT_MEASURE_ERRORS:
        return None
    return right - left, bottom - top


def _measure_with_fontsize(text: str, font) -> tuple[int, int] | None:
    if font is None or not hasattr(font, "getsize"):
        return None
    try:
        return font.getsize(text)
    except _TEXT_MEASURE_ERRORS:
        return None


def _measure_with_textlength(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int] | None:
    if not hasattr(draw, "textlength"):
        return None
    try:
        width = int(draw.textlength(text, font=font))
    except _TEXT_MEASURE_ERRORS:
        return None
    return width, 12


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
