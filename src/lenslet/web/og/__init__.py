"""Public OpenGraph helpers used by routes and import-contract tests."""

from __future__ import annotations

from importlib import import_module

from .data import (
    OgDataUnavailableError,
    load_index_or_none,
    normalize_path,
    sample_paths,
    subtree_image_count,
)
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

_RENDERING_EXPORTS = frozenset(
    {
        "fallback_og_image",
        "pixel_tile_grid",
        "render_pixel_mosaic",
    }
)

__all__ = (
    "OG_IMAGE_HEIGHT",
    "OG_IMAGE_WIDTH",
    "OG_IMAGES_X",
    "OG_IMAGES_Y",
    "OG_PIXELS_PER_IMAGE",
    "OG_STYLE",
    "OG_STYLES",
    "OG_TILE_GAP",
    "OgDataUnavailableError",
    "fallback_og_image",
    "load_index_or_none",
    "normalize_path",
    "pixel_tile_grid",
    "render_pixel_mosaic",
    "resolve_style",
    "sample_paths",
    "subtree_image_count",
)


def __getattr__(name: str) -> object:
    if name not in _RENDERING_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    rendering = import_module(f"{__name__}.rendering")
    value = getattr(rendering, name)
    globals()[name] = value
    return value
