from __future__ import annotations

OG_IMAGE_WIDTH = 1200
OG_IMAGE_HEIGHT = 630
OG_IMAGES_X = 6
OG_IMAGES_Y = 3
OG_PIXELS_PER_IMAGE = 6
OG_TILE_GAP = 2
OG_STYLE = "pixel-grid"
OG_STYLES = (OG_STYLE,)


def resolve_style(style: str | None) -> str:
    value = (style or "").strip() or OG_STYLE
    if value not in OG_STYLES:
        supported = ", ".join(OG_STYLES)
        raise ValueError(f"unsupported style '{value}'; supported styles: {supported}")
    return value
