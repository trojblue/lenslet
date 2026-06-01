from __future__ import annotations

from dataclasses import dataclass

from scripts.smoke_harness import SmokeFailure


class ViewerProbeFailure(SmokeFailure):
    """Raised when a viewer browser probe cannot collect evidence."""


@dataclass(frozen=True)
class Viewport:
    width: int
    height: int
    name: str


BACK_SWEEP_VIEWPORTS = [
    Viewport(899, 760, "899x760"),
    Viewport(900, 760, "900x760"),
    Viewport(901, 760, "901x760"),
    Viewport(960, 760, "960x760"),
    Viewport(1024, 760, "1024x760"),
    Viewport(1100, 760, "1100x760"),
    Viewport(1179, 760, "1179x760"),
    Viewport(1180, 760, "1180x760"),
    Viewport(1181, 760, "1181x760"),
    Viewport(1240, 760, "1240x760"),
    Viewport(1280, 760, "1280x760"),
    Viewport(1360, 760, "1360x760"),
    Viewport(1440, 760, "1440x760"),
    Viewport(1600, 760, "1600x760"),
    Viewport(1650, 760, "1650x760"),
    Viewport(1650, 1194, "1650x1194"),
    Viewport(1700, 760, "1700x760"),
]

BACK_SAMPLE_X_FRACS = (0.08, 0.27, 0.5, 0.73, 0.92)
BACK_SAMPLE_Y_FRACS = (0.18, 0.5, 0.82)
BACK_CLICK_POINTS = (
    ("top-center", 0.5, 0.18),
    ("center", 0.5, 0.5),
    ("bottom-center", 0.5, 0.82),
)
VIEWER_LOADER_DELAY_MS = 150
DEFAULT_DRAGS = (
    ("default-left", -160, 0),
    ("default-right", 160, 0),
    ("default-up", 0, -160),
    ("default-down", 0, 160),
)
EDGE_DRAGS = (
    ("zoom-left-edge", -260, 0),
    ("zoom-right-edge", 260, 0),
    ("zoom-up-edge", 0, -260),
    ("zoom-down-edge", 0, 260),
)
