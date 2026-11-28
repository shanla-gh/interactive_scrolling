"""Shared colour palette for the overlay and the application theme."""

from __future__ import annotations

from interactive_scrolling.vision.landmarks import Handedness

BACKGROUND = "#111214"
SURFACE = "#16181b"
SURFACE_RAISED = "#1e2125"
BORDER = "#2a2d32"
TEXT = "#e8eaed"
TEXT_MUTED = "#9aa0a6"
TEXT_DIM = "#62676e"

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
