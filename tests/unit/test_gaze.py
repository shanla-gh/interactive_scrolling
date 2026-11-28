"""Passive gaze estimate and eye overlay (Brief 009; synthetic landmarks, no person)."""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtGui import QColor, QImage, QPainter

from interactive_scrolling.vision.face_tracker import FaceObservation
from interactive_scrolling.visualization.eye_overlay import GAZE_COLOR, EyeOverlay
from interactive_scrolling.visualization.geometry import ViewTransform
from interactive_scrolling.wellbeing import gaze as g


def face(
    iris_dx: float = 0.0,
    iris_dy: float = 0.0,
    yaw: float = 0.0,
    pitch: float = 0.0,
    blink: float = 0.0,
) -> FaceObservation:
    lm = np.zeros((478, 3), dtype=np.float32)
    lm[:, :2] = (0.5, 0.45)
    for contour, cx in ((g.RIGHT_EYE, 0.43), (g.LEFT_EYE, 0.57)):
        for k, i in enumerate(contour):
            t = 2 * np.pi * k / len(contour)
            lm[i, :2] = (cx + 0.03 * np.cos(t), 0.40 + 0.01 * np.sin(t))
    lm[g.R_OUTER, :2], lm[g.R_INNER, :2] = (0.40, 0.40), (0.46, 0.40)
    lm[g.L_OUTER, :2], lm[g.L_INNER, :2] = (0.60, 0.40), (0.54, 0.40)
    lm[g.R_UPPER, :2], lm[g.R_LOWER, :2] = (0.43, 0.39), (0.43, 0.41)
    lm[g.L_UPPER, :2], lm[g.L_LOWER, :2] = (0.57, 0.39), (0.57, 0.41)
    # Iris offsets in eye widths (0.06): positive dx towards the image right (person's left).
    lm[g.R_IRIS, :2] = (0.43 + iris_dx * 0.06, 0.40 + iris_dy * 0.06)
    lm[g.L_IRIS, :2] = (0.57 + iris_dx * 0.06, 0.40 + iris_dy * 0.06)
    shapes = {"eyeBlinkLeft": blink, "eyeBlinkRight": blink}
    return FaceObservation(lm, shapes, yaw, pitch)


def test_centred_irises_and_straight_head_look_straight_ahead() -> None:
    e = g.estimate_gaze(face())
    assert e is not None and e.usable and e.quality == 1.0
    assert e.gaze_yaw_deg == pytest.approx(0.0, abs=0.5)
    assert e.gaze_pitch_deg == pytest.approx(0.0, abs=0.5)
    assert e.head_roll_deg == pytest.approx(0.0, abs=0.5)


def test_iris_offset_and_head_turn_add_up() -> None:
    eyes = g.estimate_gaze(face(iris_dx=0.1))
    assert eyes.gaze_yaw_deg == pytest.approx(13.8, abs=0.5)  # asin(0.1 / 0.42)
    head = g.estimate_gaze(face(yaw=20.0))
    assert head.gaze_yaw_deg == pytest.approx(20.0, abs=0.5)
    up = g.estimate_gaze(face(iris_dy=-0.08))
    assert up.gaze_pitch_deg > 5  # iris higher in the eye: looking up


def test_blink_and_strong_head_turn_make_the_estimate_unusable() -> None:
    assert not g.estimate_gaze(face(blink=0.9)).usable
    assert not g.estimate_gaze(face(yaw=55.0)).usable
    assert g.estimate_gaze(None) is None
    no_angles = face()
    assert g.estimate_gaze(FaceObservation(no_angles.landmarks, {}, None, None)) is None


def render(overlay: EyeOverlay, mirrored: bool) -> QImage:
    image = QImage(640, 480, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    overlay.paint(painter, ViewTransform.fit(640, 480, 640, 480, mirrored))
    painter.end()
    return image


def gaze_pixels(image: QImage, x0: int, x1: int) -> int:
    target = QColor(GAZE_COLOR)
    count = 0
    for x in range(x0, x1):
        for y in range(150, 240):
            c = image.pixelColor(x, y)
            if c.alpha() > 60 and abs(c.blue() - target.blue()) < 60 and c.red() < 160:
                count += 1
    return count


def test_overlay_draws_the_vector_towards_the_gaze_and_follows_mirroring(qtbot) -> None:
    overlay = EyeOverlay()
    for i in range(20):
        overlay.update(face(yaw=30.0), int(1e9 + i * 33e6))
    plain = render(overlay, mirrored=False)
    # Person's left is the image right: the arrow from between the eyes points right.
    assert gaze_pixels(plain, 330, 420) > gaze_pixels(plain, 220, 310)
    mirrored = render(overlay, mirrored=True)
    assert gaze_pixels(mirrored, 220, 310) > gaze_pixels(mirrored, 330, 420)


def test_overlay_hides_vectors_when_quality_is_low_and_clears_when_the_face_is_lost(
    qtbot,
) -> None:
    overlay = EyeOverlay()
    overlay.update(face(blink=0.95), int(1e9))
    assert gaze_pixels(render(overlay, False), 200, 440) == 0
    overlay.update(None, int(2e9))
    assert overlay.estimate is None
    assert render(overlay, False).pixelColor(320, 192).alpha() == 0
