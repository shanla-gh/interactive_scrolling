"""Passive eye analytics and the Progressive Clown Transformation (synthetic faces)."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pytest
from PySide6.QtGui import QImage, QPainter

from interactive_scrolling.config.settings import ConfigError, EffectsSettings
from interactive_scrolling.storage.analytics import AnalyticsStore
from interactive_scrolling.vision.face_tracker import FaceObservation, head_angles
from interactive_scrolling.visualization.clown import (
    FACE_LEFT,
    FACE_RIGHT,
    NOSE_TIP,
    ClownEffect,
    clown_stage,
)
from interactive_scrolling.visualization.geometry import ViewTransform
from interactive_scrolling.wellbeing.eyes import (
    Baseline,
    EyeAnalytics,
    ViewState,
    calibrate,
    classify,
    horizontal_gaze,
)


def face(
    yaw: float = 0.0,
    pitch: float = 0.0,
    iris_shift: float = 0.0,
    blink: float = 0.0,
    jitter: float = 0.0,
    seed: int = 0,
) -> FaceObservation:
    """478 landmarks with eye corners, irises, nose and face outline in plausible places."""
    rng = np.random.default_rng(seed)
    pts = np.zeros((478, 3), dtype=np.float32)
    pts[:, 0] = 0.5 + rng.normal(0, 0.05, 478)
    pts[:, 1] = 0.45 + rng.normal(0, 0.06, 478)
    # Right eye (image left): outer 33 at x=0.40, inner 133 at 0.46; left eye mirrored.
    pts[33, :2] = (0.40, 0.40)
    pts[133, :2] = (0.46, 0.40)
    pts[263, :2] = (0.60, 0.40)
    pts[362, :2] = (0.54, 0.40)
    # Irises; a positive shift moves both towards the person's left (image right).
    pts[468, :2] = (0.43 + iris_shift * 0.06, 0.40)
    pts[473, :2] = (0.57 + iris_shift * 0.06, 0.40)
    pts[NOSE_TIP, :2] = (0.5, 0.47)
    pts[FACE_RIGHT, :2] = (0.36, 0.45)
    pts[FACE_LEFT, :2] = (0.64, 0.45)
    pts[:, :2] += rng.normal(0, jitter, (478, 2))
    shapes = {"eyeBlinkLeft": blink, "eyeBlinkRight": blink}
    return FaceObservation(pts, shapes, yaw, pitch)


def test_horizontal_gaze_is_centred_and_signed() -> None:
    assert horizontal_gaze(face().landmarks) == pytest.approx(0.0, abs=1e-6)
    assert horizontal_gaze(face(iris_shift=0.5).landmarks) > 0.1


@pytest.mark.parametrize(
    ("kwargs", "state"),
    [
        ({}, ViewState.SCREEN),
        ({"yaw": 50}, ViewState.AWAY),
        ({"pitch": -40}, ViewState.AWAY),
        ({"iris_shift": 0.6}, ViewState.AWAY),
        ({"yaw": 30}, ViewState.UNKNOWN),  # between the limits: ambiguous
        ({"blink": 0.9}, ViewState.UNKNOWN),
    ],
)
def test_classification(kwargs: dict, state: ViewState) -> None:
    assert classify(face(**kwargs), Baseline()).state is state


def test_no_face_is_unknown_never_away() -> None:
    assert classify(None, Baseline()).state is ViewState.UNKNOWN


def test_calibration_moves_the_baseline() -> None:
    turned = face(yaw=22)
    assert classify(turned, Baseline()).state is ViewState.SCREEN
    assert classify(face(yaw=45), Baseline()).state is ViewState.AWAY
    assert classify(face(yaw=45), Baseline(yaw=30)).state is ViewState.SCREEN


def test_durations_are_mutually_exclusive_and_gaps_are_unknown() -> None:
    eyes = EyeAnalytics()
    t = 0.0
    for _ in range(30):  # 30 samples at 15 Hz facing the screen
        eyes.add(t, face())
        t += 1 / 15
    for _ in range(15):  # 1 s looking away
        eyes.add(t, face(yaw=60))
        t += 1 / 15
    eyes.add(t + 3.0, face())  # a 3 s gap without measurements
    totals = eyes.take()
    assert totals.screen_s == pytest.approx(30 / 15, abs=0.08)
    assert totals.away_s == pytest.approx(1.0, abs=0.08)
    assert totals.unknown_s >= 3.0
    assert totals.total_s == pytest.approx(totals.screen_s + totals.away_s + totals.unknown_s)
    assert totals.longest_screen_s == pytest.approx(30 / 15, abs=0.08)


def test_blinks_are_counted_and_do_not_interrupt_screen_time() -> None:
    eyes = EyeAnalytics()
    t = 0.0
    for i in range(60):
        closed = i in (20, 21, 40, 41)
        eyes.add(t, face(blink=0.9 if closed else 0.0))
        t += 1 / 15
    totals = eyes.take()
    assert totals.blinks == 2
    assert totals.away_s == 0 and totals.unknown_s == 0
    assert totals.screen_s == pytest.approx(59 / 15, abs=0.08)


def test_blinks_unavailable_at_low_frame_rate() -> None:
    eyes = EyeAnalytics()
    for i in range(10):
        eyes.add(i * 0.5, face())
    assert eyes.take().blinks is None


def test_calibration_quality() -> None:
    steady = [face(yaw=5.0, seed=i) for i in range(30)]
    result = calibrate(steady)
    assert result is not None and result.reliable
    assert result.baseline.yaw == pytest.approx(5.0)
    shaky = [face(yaw=float(i % 2) * 30, seed=i) for i in range(30)]
    assert not calibrate(shaky).reliable
    assert calibrate([]) is None


def test_head_angles_from_rotation_matrix() -> None:
    angle = np.radians(20)
    matrix = np.eye(4)
    matrix[:3, :3] = [
        [np.cos(angle), 0, np.sin(angle)],
        [0, 1, 0],
        [-np.sin(angle), 0, np.cos(angle)],
    ]
    yaw, pitch = head_angles(matrix)
    assert yaw == pytest.approx(20, abs=0.5) and pitch == pytest.approx(0, abs=0.5)


def test_eye_aggregates_are_stored_without_per_frame_data(tmp_path) -> None:
    store = AnalyticsStore(tmp_path / "a.sqlite3")
    store.record_eyes(100.0, 20.0, 5.0, 30, 60.0)
    store.record_eyes(50.0, 10.0, 5.0, 12, 80.0)
    store.flush()
    report = store.eye_report()
    assert report.screen_s == 150 and report.away_s == 30 and report.unknown_s == 10
    assert report.blinks == 42 and report.longest_screen_s == 80
    store.record_eyes(10.0, 0.0, 0.0, None, 5.0)  # blinks not countable in this period
    store.flush()
    assert store.eye_report().blinks is None
    assert store.clear()
    assert store.eye_report() is None
    store.close()


def test_eye_report_for_another_day_is_empty(tmp_path) -> None:
    store = AnalyticsStore(tmp_path / "a.sqlite3")
    store.record_eyes(1.0, 1.0, 1.0, 1, 1.0)
    store.flush()
    assert store.eye_report(datetime(2020, 1, 1).date()) is None
    store.close()


# ---------------------------------------------------------------------- clown


@pytest.mark.parametrize(
    ("minutes", "stage"), [(0, 0), (9.9, 0), (10, 1), (19, 1), (20, 2), (30, 3), (500, 3)]
)
def test_clown_stage_thresholds(minutes: float, stage: int) -> None:
    assert clown_stage(minutes * 60, (10, 20, 30)) == stage


def test_clown_settings_validation() -> None:
    with pytest.raises(ConfigError):
        EffectsSettings(clown_stage1_min=30, clown_stage2_min=20)
    with pytest.raises(ConfigError):
        EffectsSettings(clown_preview_stage=4)


def render(effect: ClownEffect) -> QImage:
    image = QImage(640, 480, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    effect.paint(painter, ViewTransform.fit(640, 480, 640, 480, False))
    painter.end()
    return image


def feed(
    effect: ClownEffect, stage: int, seconds: float, with_face: bool = True, start: float = 1.0
) -> None:
    landmarks = face().landmarks
    for i in range(int(seconds * 30)):
        effect.update(landmarks if with_face else None, int((start + i / 30) * 1e9), stage)


def test_red_nose_is_drawn_on_the_nose_tip(qtbot) -> None:
    effect = ClownEffect()
    feed(effect, 1, 3.0)
    image = render(effect)
    nose = image.pixelColor(int(0.5 * 640), int(0.47 * 480))
    assert nose.red() > 150 and nose.green() < 90 and nose.alpha() > 200
    far = image.pixelColor(20, 20)
    assert far.alpha() == 0


def test_stage_zero_draws_nothing_and_effect_follows_the_face(qtbot) -> None:
    effect = ClownEffect()
    feed(effect, 0, 2.0)
    assert render(effect).pixelColor(320, 225).alpha() == 0
    moved = face().landmarks.copy()
    moved[:, 0] += 0.1  # the head moves to the image right
    effect = ClownEffect()
    for i in range(90):
        effect.update(moved, int(1e9 + i * 1e9 / 30), 1)
    image = render(effect)
    assert image.pixelColor(int(0.6 * 640), int(0.47 * 480)).red() > 150
    assert image.pixelColor(int(0.5 * 640), int(0.47 * 480)).alpha() < 50


def test_effect_disappears_when_the_face_is_lost(qtbot) -> None:
    effect = ClownEffect()
    feed(effect, 3, 6.0)
    assert effect.visible
    feed(effect, 3, 1.5, with_face=False, start=7.0)
    assert not effect.visible
    assert render(effect).pixelColor(320, 225).alpha() == 0
