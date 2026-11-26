"""Pixel-level checks that the overlay is drawn exactly over the corresponding image content.

The video view is rendered offscreen at several sizes, mirrored and unmirrored, and the
rendered pixels are inspected at the positions where landmarks and image markers must be.
"""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtGui import QColor, QImage

from interactive_scrolling.config.settings import OverlaySettings
from interactive_scrolling.core.pipeline import ProcessedFrame
from interactive_scrolling.motion.analyzer import MotionAnalyzer, MotionFrame
from interactive_scrolling.ui.video_view import VideoView
from interactive_scrolling.vision.landmarks import Handedness, TrackingResult
from interactive_scrolling.visualization import palette
from tests.helpers import make_hand

W, H = 640, 480
MARKER = (0.15, 0.2)  # normalized position of a red block in the source image
GREEN = QColor(palette.ACCENT_GREEN)
CYAN = QColor(palette.ACCENT_CYAN)


def build_frame(hands=(), motion: MotionFrame | None = None, ts: int = 1) -> ProcessedFrame:
    image = np.zeros((H, W, 3), dtype=np.uint8)
    mx, my = int(MARKER[0] * W), int(MARKER[1] * H)
    image[my - 6 : my + 7, mx - 6 : mx + 7] = (255, 0, 0)  # RGB red
    tracking = TrackingResult(0, ts, W, H, tuple(hands))
    return ProcessedFrame(
        session=1,
        image_rgb=image,
        tracking=tracking,
        motion=motion or MotionFrame(ts),
        capture_ns=ts,
        completed_ns=ts,
        inference_ms=None,
        processing_ms=0.0,
    )


def render(view: VideoView, width: int, height: int) -> QImage:
    view.resize(width, height)
    return view.grab().toImage()


def close(a: QColor, b: QColor, tol: int = 12) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a.getRgb()[:3], b.getRgb()[:3], strict=True))


@pytest.fixture
def view(qtbot) -> VideoView:
    widget = VideoView(OverlaySettings())
    qtbot.addWidget(widget)
    return widget


@pytest.mark.parametrize("mirrored", [False, True])
@pytest.mark.parametrize("size", [(640, 480), (1000, 500), (500, 900), (1337, 777)])
def test_landmarks_land_on_mapped_positions(view: VideoView, mirrored: bool, size) -> None:
    hand = make_hand((300, 380), palm_px=90, handedness=Handedness.RIGHT)
    view.set_mirrored(mirrored)
    view.set_frame(build_frame([hand]))
    image = render(view, *size)
    transform = view.current_transform()
    assert transform is not None and transform.mirrored is mirrored
    for x, y, _ in hand.landmarks:
        vx, vy = transform.map_normalized(float(x), float(y))
        pixel = image.pixelColor(round(vx - 0.5), round(vy - 0.5))
        assert close(pixel, GREEN), (x, y, pixel.name())


@pytest.mark.parametrize("mirrored", [False, True])
@pytest.mark.parametrize("size", [(640, 480), (1200, 500), (500, 900)])
def test_video_image_uses_the_same_transform(view: VideoView, mirrored: bool, size) -> None:
    view.set_mirrored(mirrored)
    view.set_frame(build_frame())
    image = render(view, *size)
    transform = view.current_transform()
    vx, vy = transform.map_normalized(*MARKER)
    assert close(image.pixelColor(round(vx), round(vy)), QColor(255, 0, 0))
    # The opposite side of the image must not contain the marker.
    ox, oy = transform.map_normalized(1 - MARKER[0], MARKER[1])
    assert not close(image.pixelColor(round(ox), round(oy)), QColor(255, 0, 0))


def test_mirroring_moves_marker_to_the_opposite_side(view: VideoView) -> None:
    view.set_mirrored(False)
    view.set_frame(build_frame())
    plain = render(view, 640, 480)
    view.set_mirrored(True)
    mirrored = render(view, 640, 480)
    x, y = int(MARKER[0] * 640), int(MARKER[1] * 480)
    assert close(plain.pixelColor(x, y), QColor(255, 0, 0))
    assert close(mirrored.pixelColor(639 - x, y), QColor(255, 0, 0))
    assert not close(mirrored.pixelColor(x, y), QColor(255, 0, 0))


def test_overlay_layers_can_be_disabled(view: VideoView) -> None:
    hand = make_hand((300, 380), palm_px=90)
    view.set_frame(build_frame([hand]))
    for field in vars(view.overlay):
        setattr(view.overlay, field, False)
    image = render(view, 640, 480)
    transform = view.current_transform()
    for x, y, _ in hand.landmarks:
        vx, vy = transform.map_normalized(float(x), float(y))
        assert close(image.pixelColor(round(vx - 0.5), round(vy - 0.5)), QColor(0, 0, 0))


def test_skeleton_only_draws_bones_not_landmark_rings(view: VideoView) -> None:
    hand = make_hand((300, 380), palm_px=90)
    view.overlay.show_landmarks = False
    view.overlay.show_bounding_box = False
    view.overlay.show_labels = False
    view.set_frame(build_frame([hand]))
    image = render(view, 640, 480)
    t = view.current_transform()
    # Midpoint of the wrist -> index finger MCP bone.
    a = t.map_normalized(*hand.landmarks[0, :2])
    b = t.map_normalized(*hand.landmarks[5, :2])
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    assert close(image.pixelColor(round(mid[0] - 0.5), round(mid[1] - 0.5)), GREEN, tol=40)


def test_two_hands_are_drawn_in_distinct_colours(view: VideoView) -> None:
    right = make_hand((180, 400), palm_px=70, handedness=Handedness.RIGHT)
    left = make_hand((470, 400), palm_px=70, handedness=Handedness.LEFT)
    view.set_frame(build_frame([right, left]))
    image = render(view, 640, 480)
    t = view.current_transform()
    for hand, color in ((right, GREEN), (left, CYAN)):
        vx, vy = t.map_normalized(*hand.landmarks[0, :2])
        assert close(image.pixelColor(round(vx - 0.5), round(vy - 0.5)), color)


def test_lost_hand_leaves_no_overlay(view: VideoView) -> None:
    hand = make_hand((300, 380), palm_px=90)
    view.set_frame(build_frame([hand], ts=1))
    render(view, 640, 480)
    view.set_frame(build_frame([], ts=2))
    image = render(view, 640, 480)
    t = view.current_transform()
    for x, y, _ in hand.landmarks:
        vx, vy = t.map_normalized(float(x), float(y))
        assert close(image.pixelColor(round(vx - 0.5), round(vy - 0.5)), QColor(0, 0, 0))


def test_motion_vector_points_in_measured_direction(view: VideoView) -> None:
    analyzer = MotionAnalyzer()
    hand = None
    motion = None
    for i in range(20):
        hand = make_hand((150 + 12 * i, 380), palm_px=90)  # 360 px/s to the right
        motion = analyzer.update(TrackingResult(0, i * 33_333_333, W, H, (hand,)))
    assert motion.hands[0].fingertip.is_moving
    view.overlay.show_landmarks = False
    view.overlay.show_skeleton = False
    view.overlay.show_bounding_box = False
    view.overlay.show_labels = False
    view.overlay.show_fingertip_trail = False
    for mirrored, sign in ((False, 1), (True, -1)):
        view.set_mirrored(mirrored)
        view.set_frame(build_frame([hand], motion, ts=motion.timestamp_ns))
        image = render(view, 640, 480)
        t = view.current_transform()
        tx, ty = t.map_normalized(*hand.landmarks[8, :2])
        ahead = image.pixelColor(round(tx + sign * 25), round(ty))
        behind = image.pixelColor(round(tx - sign * 25), round(ty))
        assert close(ahead, GREEN, tol=40), ahead.name()
        assert close(behind, QColor(0, 0, 0), tol=40), behind.name()


def test_clear_removes_frame(view: VideoView) -> None:
    view.set_frame(build_frame([make_hand((300, 380))]))
    view.clear("Camera is off")
    assert view.frame is None and view.current_transform() is None
    image = render(view, 640, 480)
    assert image.width() == 640
