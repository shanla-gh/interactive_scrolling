"""Transparent-background compositing (Brief 007: enclosed-hole fill)."""

from __future__ import annotations

import numpy as np

from interactive_scrolling.vision.compositing import MaskCompositor


def _person_with_unsure_shirt(w: int = 480, h: int = 270):  # type: ignore[no-untyped-def]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    torso = ((xx - w * 0.5) / (w * 0.26)) ** 2 + ((yy - h * 1.02) / (h * 0.5)) ** 2 <= 1
    conf = np.where(torso, 0.9, 0.05).astype(np.float32)
    patch = torso & (np.abs(xx - w * 0.42) < w * 0.07) & (yy > h * 0.68)
    conf[patch] = 0.3  # light shirt with low model confidence
    return conf, patch, torso


def test_low_confidence_patch_inside_the_person_is_kept() -> None:
    """Brief 007: light clothing against a dark background showed the room through the shirt."""
    conf, patch, torso = _person_with_unsure_shirt()
    image = np.zeros((270, 480, 3), np.uint8)
    rgba = MaskCompositor().compose(image, conf, 1, (480, 270))
    alpha = rgba[..., 3] / 255.0
    assert (alpha[patch] >= 0.5).mean() > 0.8
    assert (alpha[~torso] > 0.1).mean() < 0.02  # the room around the person stays hidden


def test_background_open_to_the_sides_is_never_filled() -> None:
    """Only regions enclosed by the person are filled; the room beside it never is."""
    conf = np.full((270, 480), 0.05, np.float32)
    conf[:, 200:280] = 0.9  # a vertical band touching top and bottom
    rgba = MaskCompositor().compose(np.zeros((270, 480, 3), np.uint8), conf, 1, (480, 270))
    alpha = rgba[..., 3]
    assert alpha[:, :190].max() == 0 and alpha[:, 290:].max() == 0
