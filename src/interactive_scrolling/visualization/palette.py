"""Shared colour palette for the overlay and the application theme."""

from __future__ import annotations

from interactive_scrolling.vision.landmarks import Handedness

BACKGROUND = "#0b0d10"
SURFACE = "#14171c"
SURFACE_RAISED = "#1b1f26"
BORDER = "#262b33"
TEXT = "#e6edf3"
TEXT_MUTED = "#8b949e"
TEXT_DIM = "#5c6570"

ACCENT_GREEN = "#3dff9a"
ACCENT_CYAN = "#2de2f2"
ACCENT_AMBER = "#ffb547"
ACCENT_RED = "#ff5c6c"
ACCENT_WHITE = "#dfe7ee"

HAND_COLORS: dict[Handedness, str] = {
    Handedness.RIGHT: ACCENT_GREEN,
    Handedness.LEFT: ACCENT_CYAN,
    Handedness.UNKNOWN: ACCENT_WHITE,
}


def hand_color(handedness: Handedness) -> str:
    return HAND_COLORS[handedness]
