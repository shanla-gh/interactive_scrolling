"""Brief 007 Broadcast Mode refinements: control status, counters, positioning, smoothing."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
from PySide6.QtWidgets import QApplication

from interactive_scrolling.actions.types import ControlMode
from interactive_scrolling.config.settings import (
    AppearanceSettings,
    AppSettings,
    CameraSettings,
    CreatorSettings,
    OverlayCorner,
)
from interactive_scrolling.ui.control_bar import ControlBar
from interactive_scrolling.ui.creator_overlay import CreatorOverlay
from interactive_scrolling.ui.main_window import MainWindow, broadcast_counters
from interactive_scrolling.vision.landmarks import TrackingResult
from interactive_scrolling.visualization.smoothing import LandmarkSmoother
from tests.gesture_helpers import POINTING, make_observation
from tests.helpers import ScriptedTracker, camera_factory, make_hand


def test_a_saved_position_off_every_screen_falls_back_to_a_visible_corner(qtbot) -> None:
    """A monitor was removed: the overlay must not open where nobody can see or move it."""
    settings = CreatorSettings(corner=OverlayCorner.CUSTOM, x=-15000, y=-15000)
    overlay = CreatorOverlay(settings, AppearanceSettings())
    qtbot.addWidget(overlay)
    assert overlay.settings.corner is OverlayCorner.BOTTOM_RIGHT
    assert overlay.visible_share(overlay.frameGeometry()) > 0.9


def test_a_visible_custom_position_is_kept(qtbot) -> None:
    area = QApplication.primaryScreen().availableGeometry()
    x, y = area.left() + 40, area.top() + 40
    overlay = CreatorOverlay(
        CreatorSettings(corner=OverlayCorner.CUSTOM, x=x, y=y), AppearanceSettings()
    )
    qtbot.addWidget(overlay)
    assert (overlay.pos().x(), overlay.pos().y()) == (x, y)


def test_move_to_corner_from_the_menu_is_saved(qtbot) -> None:
    overlay = CreatorOverlay(CreatorSettings(), AppearanceSettings())
    qtbot.addWidget(overlay)
    saved = []
    overlay.settings_changed.connect(saved.append)
    overlay.move_to_corner(OverlayCorner.TOP_LEFT)
    area = QApplication.primaryScreen().availableGeometry()
    assert saved[-1].corner is OverlayCorner.TOP_LEFT
    assert overlay.pos().x() < area.center().x() and overlay.pos().y() < area.center().y()
    labels = [a.text() for a in overlay.build_menu().actions()]
    assert "Position" in labels and "Gesture control status" in labels


def test_overlay_shows_the_gesture_control_state_and_follows_mode_changes(qtbot) -> None:
    """Broadcast Mode must never imply Live control (Brief 007 CP 27.2)."""
    tracker = ScriptedTracker(lambda ms: (make_hand((320, 300), palm_px=80),))
    window = MainWindow(
        AppSettings(camera=CameraSettings(width=640, height=480)),
        camera_factory=camera_factory(fps=60),
        tracker_factory=lambda: tracker,
    )
    qtbot.addWidget(window)
    assert window.creator.control_mode is ControlMode.TRACKING_ONLY
    window.set_ui_mode("creator")
    assert window.services.dispatcher.mode is ControlMode.TRACKING_ONLY  # mode unchanged
    window.set_control_mode(ControlMode.LIVE_CONTROL)
    qtbot.waitUntil(lambda: window.creator.control_mode is ControlMode.LIVE_CONTROL)
    window.emergency_disable()
    qtbot.waitUntil(lambda: window.creator.control_mode is ControlMode.TRACKING_ONLY)
    window.set_ui_mode("developer")
    window.close()


def test_session_timer_and_counters_text() -> None:
    assert broadcast_counters(754.0, None) == "Session 12:34"

    from types import SimpleNamespace

    report = SimpleNamespace(succeeded={"next_short": 5, "previous_short": 2})
    assert broadcast_counters(5.0, report) == "Session 0:05  ·  7 actions today"


def _tracking(x: float, ts_ns: int, jitter: float = 0.0, rng=None) -> TrackingResult:  # type: ignore[no-untyped-def]
    obs = make_observation(POINTING, (x, 400.0))
    if jitter:
        obs.landmarks[:, :2] += rng.normal(0, jitter, obs.landmarks[:, :2].shape)
    return TrackingResult(0, ts_ns, 1280, 720, (obs,))


def test_display_smoothing_reduces_still_hand_jitter_and_keeps_up_with_fast_movement() -> None:
    rng = np.random.default_rng(1)
    smoother = LandmarkSmoother()
    raw_steps, smooth_steps = [], []
    prev_raw = prev_smooth = None
    for i in range(90):
        tracking = _tracking(640.0, i * 33_333_333, jitter=1.5 / 1280, rng=rng)
        out = smoother.smooth(tracking)
        raw, smooth = tracking.hands[0].landmarks, out.hands[0].landmarks
        if prev_raw is not None:
            raw_steps.append(np.abs(raw - prev_raw)[:, :2].mean())
            smooth_steps.append(np.abs(smooth - prev_smooth)[:, :2].mean())
        prev_raw, prev_smooth = raw, smooth
    assert np.mean(smooth_steps) < 0.75 * np.mean(raw_steps)
    # A fast swipe (60 px per frame): the drawn hand stays within a few pixels.
    lags = []
    for i in range(90, 105):
        tracking = _tracking(640.0 + (i - 89) * 60.0, i * 33_333_333)
        out = smoother.smooth(tracking)
        lag = np.abs(out.hands[0].landmarks - tracking.hands[0].landmarks)[:, 0].mean() * 1280
        lags.append(lag)
    assert lags[-1] < 15.0


def test_display_smoothing_never_changes_the_input_used_for_recognition() -> None:
    tracking = _tracking(640.0, 0)
    before = tracking.hands[0].landmarks.copy()
    smoother = LandmarkSmoother()
    smoother.smooth(tracking)
    smoother.smooth(replace(tracking, timestamp_ns=33_333_333))
    assert np.array_equal(tracking.hands[0].landmarks, before)


def test_checked_mode_buttons_reserve_room_for_bold_text(qtbot) -> None:
    """Brief 007: the checked (bold) "Tracking only" button was clipped at 125 % scaling."""
    bar = ControlBar()
    qtbot.addWidget(bar)
    bar.show()
    for button in bar.buttons.values():
        font = button.font()
        font.setBold(True)
        from PySide6.QtGui import QFontMetrics

        assert button.minimumWidth() >= QFontMetrics(font).horizontalAdvance(button.text())
        assert button.width() >= button.minimumWidth()
