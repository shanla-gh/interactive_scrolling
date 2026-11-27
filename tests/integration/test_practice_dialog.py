"""Gesture Practice and Quick Calibration dialog (no browser actions while it is open)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from interactive_scrolling.actions.types import ControlMode
from interactive_scrolling.config.settings import SensitivityPreset
from interactive_scrolling.gestures.types import GestureEvent, GestureType
from interactive_scrolling.motion.analyzer import MotionAnalyzer
from interactive_scrolling.services import offline_services
from interactive_scrolling.ui.practice_dialog import SEQUENCE, PracticeDialog
from interactive_scrolling.vision.landmarks import Handedness, TrackingResult
from tests.gesture_helpers import HALF_HEART, OPEN, Hand, chain, make_observation, still, stroke

G = GestureType


def event(gesture: GestureType) -> GestureEvent:
    return GestureEvent(gesture, time.perf_counter_ns(), 1, Handedness.RIGHT)


def make(qtbot, tmp_path: Path, mode: ControlMode = ControlMode.TRACKING_ONLY):
    services = offline_services()
    services.dispatcher.set_mode(mode)
    dialog = PracticeDialog(services, tmp_path)
    qtbot.addWidget(dialog)
    return dialog, services


def test_no_browser_action_while_open_and_live_control_is_not_restored(qtbot, tmp_path) -> None:
    dialog, services = make(qtbot, tmp_path, ControlMode.LIVE_CONTROL)
    assert services.dispatcher.mode is ControlMode.GESTURE_TEST
    dialog.close()
    assert services.dispatcher.mode is ControlMode.GESTURE_TEST
    dialog, services = make(qtbot, tmp_path, ControlMode.TRACKING_ONLY)
    dialog.close()
    assert services.dispatcher.mode is ControlMode.TRACKING_ONLY


def test_emergency_disable_during_practice_is_kept(qtbot, tmp_path) -> None:
    dialog, services = make(qtbot, tmp_path, ControlMode.LIVE_CONTROL)
    services.dispatcher.emergency_disable()
    dialog.close()
    assert services.dispatcher.mode is ControlMode.TRACKING_ONLY


def test_practice_counts_recognized_gestures_and_explains_wrong_ones(qtbot, tmp_path) -> None:
    dialog, services = make(qtbot, tmp_path)
    dialog.start("practice")
    assert SEQUENCE[dialog.index] is G.INDEX_SWIPE_UP
    services.dispatcher.submit(event(G.INDEX_SWIPE_DOWN))
    qtbot.waitUntil(lambda: "That was SWIPE DOWN" in dialog.result.text(), timeout=2000)
    for _ in range(3):
        services.dispatcher.submit(event(G.INDEX_SWIPE_UP))
    qtbot.waitUntil(lambda: SEQUENCE[dialog.index] is G.INDEX_SWIPE_DOWN, timeout=3000)
    assert dialog.result.text() == ""


def _feed(services, hand: Hand, seconds: float, t0: float) -> None:
    analyzer = MotionAnalyzer()
    for i in range(int(seconds * 30)):
        t = i / 30
        position = hand.position(t)
        obs = () if position is None else (make_observation(hand.pose(t), position),)
        tracking = TrackingResult(i, int((t0 + t) * 1e9), 1280, 720, obs)
        frame = services.engine.update(tracking, analyzer.update(tracking))
        services.gesture_tap(tracking, frame)


def _strokes(dx: float, dy: float) -> Hand:
    x, y = 640.0, 400.0
    segments = [(0.0, still(x, y))]
    for k in range(3):
        t = 0.8 + 1.2 * k
        end = (x + dx * 70, y + dy * 70)
        segments.append((t, stroke((x, y), end, t, 0.2)))
        segments.append((t + 0.45, stroke(end, (x, y), t + 0.45, 0.3)))
    return Hand(chain(*segments))


def test_quick_calibration_measures_applies_and_records(qtbot, tmp_path) -> None:
    dialog, services = make(qtbot, tmp_path)
    dialog.record_box.setChecked(True)
    dialog.start("calibration")
    hands = {
        G.INDEX_SWIPE_UP: _strokes(0, -1),
        G.INDEX_SWIPE_DOWN: _strokes(0, 1),
        G.INDEX_SWIPE_RIGHT: _strokes(-1, 0),  # image left = the user's right
        G.INDEX_SWIPE_LEFT: _strokes(1, 0),
        G.HALF_HEART: Hand(still(640, 400), pose=lambda t: HALF_HEART),
        G.STOP_GESTURE: Hand(still(640, 400), pose=lambda t: OPEN),
    }
    t0 = 1.0
    for gesture in SEQUENCE:
        qtbot.waitUntil(lambda g=gesture: SEQUENCE[dialog.index] is g, timeout=3000)
        _feed(services, hands[gesture], 4.5 if gesture.is_dynamic else 1.5, t0)
        t0 += 10
        dialog._prompt_started -= 3  # the static prompts accept a hold after 2 s
        qtbot.waitUntil(
            lambda g=gesture: dialog.stack.currentIndex() == 2 or SEQUENCE[dialog.index] is not g,
            timeout=3000,
        )
    assert dialog.stack.currentIndex() == 2
    assert "Quick Calibration results" in dialog.summary.text()
    assert dialog.derived is not None
    dialog.apply_profile()
    assert services.user_settings.gestures.preset is SensitivityPreset.PERSONAL
    assert services.user_settings.calibration.has_heart
    assert services.engine.profile is services.user_settings.calibration
    assert dialog.saved_recording is not None
    content = json.loads(dialog.saved_recording.read_text(encoding="utf-8"))
    labels = {p[0] for p in content["prompts"]}
    assert {"calib_up", "calib_half_heart", "calib_stop"} <= labels
    dialog.restore_defaults()
    assert services.user_settings.gestures.preset is SensitivityPreset.BALANCED
    assert not services.user_settings.calibration.has_heart
