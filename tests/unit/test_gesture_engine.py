"""Gesture engine behaviour on scripted synthetic hands (no webcam).

Times are in seconds from the start of a run. A newly visible hand needs ~0.3 s of tracking
and a short still moment before swipes can start, so scripted strokes begin at t >= 0.6 s.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from interactive_scrolling.config.settings import (
    ConfigError,
    ControlHandPreference,
    GestureSettings,
    SensitivityPreset,
)
from interactive_scrolling.gestures.engine import GestureEngine
from interactive_scrolling.gestures.types import ControlStatus, GestureType
from interactive_scrolling.vision.landmarks import Handedness
from tests.gesture_helpers import (
    C_SIDEWAYS,
    FIST,
    HALF_HEART,
    OPEN,
    PINCH,
    POINTING,
    THUMBS_UP,
    Hand,
    chain,
    index_curl,
    kinds,
    rejections,
    run,
    still,
    stroke,
)

G = GestureType


def swipe_down(t: float = 0.8, distance: float = 150, duration: float = 0.3) -> Hand:
    return Hand(stroke((640, 300), (640, 300 + distance), t, duration))


# ---------------------------------------------------------------------- finger swipes


def test_pointing_hand_moving_down_is_one_swipe_down() -> None:
    events, _ = run([swipe_down()], 2.0)
    assert kinds(events) == ["INDEX_SWIPE_DOWN"]
    event = events[0]
    assert event.direction == "down"
    assert event.magnitude_palms >= 0.8
    assert event.peak_speed_palms_s >= 2.0
    assert event.handedness is Handedness.RIGHT


def test_pointing_hand_moving_up_is_one_swipe_up() -> None:
    events, _ = run([Hand(stroke((640, 450), (640, 300), 0.8, 0.3))], 2.0)
    assert kinds(events) == ["INDEX_SWIPE_UP"]
    assert events[0].direction == "up"


def test_return_movement_after_swipe_is_ignored() -> None:
    # Observed in real recordings: the hand returns as fast and as far as the swipe itself.
    # Here the return starts 0.6 s after the swipe ends: after the swipe's cooldown, inside
    # the return window.
    path = stroke((640, 300), (640, 520), 0.8, 0.4, then=stroke((640, 520), (640, 300), 1.8, 0.4))
    events, frames = run([Hand(path)], 3.0)
    assert kinds(events) == ["INDEX_SWIPE_DOWN"]
    assert "return movement after previous swipe" in rejections(frames)


def test_repeated_swipes_with_returns_each_trigger_once() -> None:
    # Down, return, down, return, down: three intended swipes about 2.4 s apart.
    segments = []
    t = 0.8
    for _ in range(3):
        segments.append((t, stroke((640, 300), (640, 520), t, 0.4)))
        segments.append((t + 0.6, stroke((640, 520), (640, 300), t + 0.6, 0.4)))
        t += 2.4
    events, _ = run([Hand(chain(*segments))], t + 1.0)
    assert kinds(events) == ["INDEX_SWIPE_DOWN"] * 3


def test_deliberate_opposite_swipe_after_return_window() -> None:
    path = stroke((640, 300), (640, 450), 0.8, 0.3, then=stroke((640, 450), (640, 300), 2.6, 0.3))
    events, _ = run([Hand(path)], 3.5)
    assert kinds(events) == ["INDEX_SWIPE_DOWN", "INDEX_SWIPE_UP"]


def test_opposite_swipe_right_after_the_return_is_accepted() -> None:
    # Down (next), the hand returns, then immediately up (previous): the up stroke starts back
    # at the original position, so it is a deliberate gesture, not part of the return. This is
    # well inside the return window, which therefore does not delay "next, then previous".
    path = chain(
        (0.0, stroke((640, 350), (640, 520), 0.8, 0.3)),
        (1.55, stroke((640, 520), (640, 350), 1.55, 0.3)),
        (2.15, stroke((640, 350), (640, 190), 2.15, 0.3)),
    )
    events, frames = run([Hand(path)], 3.2)
    assert kinds(events) == ["INDEX_SWIPE_DOWN", "INDEX_SWIPE_UP"]
    assert "return movement after previous swipe" in rejections(frames)
    assert events[1].timestamp_ns - events[0].timestamp_ns < 1.5e9


def test_return_split_into_two_movements_is_ignored() -> None:
    # Observed in recordings: the hand comes back in two parts with a short pause.
    path = chain(
        (0.0, stroke((640, 300), (640, 520), 0.8, 0.3)),
        (1.25, stroke((640, 520), (640, 430), 1.25, 0.2)),
        (1.6, stroke((640, 430), (640, 300), 1.6, 0.2)),
    )
    events, _ = run([Hand(path)], 2.6)
    assert kinds(events) == ["INDEX_SWIPE_DOWN"]


@pytest.mark.parametrize(
    ("distance", "duration", "reason"),
    [
        (40, 0.3, "movement too short"),  # 0.4 palm lengths
        (150, 2.0, "too slow"),  # 0.75 palm lengths per second on average
    ],
)
def test_small_or_slow_movements_are_rejected(
    distance: float, duration: float, reason: str
) -> None:
    events, _frames = run([swipe_down(distance=distance, duration=duration)], 3.5)
    assert events == []


def test_diagonal_movement_is_not_a_vertical_swipe() -> None:
    events, _frames = run([Hand(stroke((500, 300), (650, 450), 0.8, 0.3))], 2.0)
    assert events == []


def test_open_hand_moving_down_is_not_a_finger_swipe() -> None:
    events, _ = run([Hand(stroke((640, 300), (640, 450), 0.8, 0.3), pose=lambda t: OPEN)], 2.0)
    assert events == []


def test_finger_curl_flick_is_not_a_swipe() -> None:
    # Curling the index finger from pointing to a fist (a "flick") is ambiguous with its own
    # return movement in real data, so it must not count as a swipe.
    def pose(t: float):
        return POINTING if t < 0.9 else FIST

    events, _ = run([Hand(stroke((640, 300), (640, 330), 0.85, 0.1), pose=pose)], 2.0)
    assert events == []


def test_hand_raised_into_view_while_pointing_does_not_swipe() -> None:
    # The hand appears low in the frame and keeps rising for 0.5 s before settling.
    entering = stroke((640, 700), (640, 350), 0.0, 0.6)
    events, frames = run([Hand(entering)], 1.5)
    assert events == []
    assert frames[0].status is ControlStatus.STABILIZING


def test_swipe_works_after_hand_has_settled() -> None:
    path = stroke((640, 700), (640, 350), 0.0, 0.6, then=stroke((640, 350), (640, 520), 1.2, 0.3))
    events, _ = run([Hand(path)], 2.5)
    assert kinds(events) == ["INDEX_SWIPE_DOWN"]


def test_stationary_pointing_hand_with_jitter_never_swipes() -> None:
    import random

    rng = random.Random(7)
    jitter = {}

    def position(t: float) -> tuple[float, float]:
        key = round(t, 4)
        if key not in jitter:
            jitter[key] = (640 + rng.gauss(0, 1.2), 400 + rng.gauss(0, 1.2))
        return jitter[key]

    events, _ = run([Hand(position)], 5.0)
    assert events == []


def test_tracking_loss_mid_stroke_cancels_without_event() -> None:
    base = stroke((640, 300), (640, 500), 0.8, 0.4)

    def position(t: float):
        return None if 0.9 <= t < 1.4 else base(t)

    events, frames = run([Hand(position)], 2.5)
    assert events == []
    assert "tracking lost" in rejections(frames)


def test_reacquired_hand_moving_does_not_produce_spike_swipe() -> None:
    # The hand vanishes and reappears 300 px lower; the jump must not count as movement.
    def position(t: float):
        if t < 1.0:
            return (640, 300)
        if t < 1.4:
            return None
        return (640, 600)

    events, _ = run([Hand(position)], 2.5)
    assert events == []


@pytest.mark.parametrize("fps", [15.0, 30.0, 60.0])
def test_recognition_is_frame_rate_independent(fps: float) -> None:
    events, _ = run([swipe_down(distance=150, duration=0.3)], 2.0, fps=fps)
    assert kinds(events) == ["INDEX_SWIPE_DOWN"]
    assert events[0].magnitude_palms == pytest.approx(0.8, abs=0.25)


# ---------------------------------------------------------------------- horizontal swipes


def side_swipe(start_x: float, end_x: float, t: float = 0.8, duration: float = 0.25) -> Hand:
    return Hand(stroke((start_x, 400), (end_x, 400), t, duration))


def test_swipe_to_users_right_moves_towards_image_left() -> None:
    # The camera image is not mirrored: the user's right is the image's left.
    events, _ = run([side_swipe(700, 580)], 2.0)
    assert kinds(events) == ["INDEX_SWIPE_RIGHT"]
    assert events[0].direction == "right"


def test_swipe_to_users_left() -> None:
    events, _ = run([side_swipe(580, 700)], 2.0)
    assert kinds(events) == ["INDEX_SWIPE_LEFT"]
    assert events[0].direction == "left"


@pytest.mark.parametrize("handedness", [Handedness.RIGHT, Handedness.LEFT])
@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ((640, 300), (640, 460), "INDEX_SWIPE_DOWN"),
        ((640, 460), (640, 300), "INDEX_SWIPE_UP"),
        ((700, 400), (560, 400), "INDEX_SWIPE_RIGHT"),
        ((560, 400), (700, 400), "INDEX_SWIPE_LEFT"),
    ],
)
def test_all_four_directions_with_either_hand(
    start: tuple[float, float], end: tuple[float, float], expected: str, handedness: Handedness
) -> None:
    events, _ = run([Hand(stroke(start, end, 0.8, 0.3), handedness=handedness)], 2.0)
    assert kinds(events) == [expected]
    assert events[0].handedness is handedness


@pytest.mark.parametrize(
    ("end", "label"),
    [((490, 550), "down-right in the image"), ((790, 250), "up-left in the image")],
)
def test_diagonal_movements_are_rejected_not_guessed(end: tuple[float, float], label: str) -> None:
    events, frames = run([Hand(stroke((640, 400), end, 0.8, 0.3))], 2.0)
    assert events == [], label
    assert "diagonal movement" in rejections(frames)


def test_wind_up_flowing_into_a_side_swipe_gives_only_the_swipe() -> None:
    # A small movement to the left that turns straight into a swipe to the right is measured
    # from the turning point, so the real stroke is not cut short.
    path = stroke(
        (600, 400), (640, 400), 0.7, 0.25, then=stroke((640, 400), (500, 400), 0.95, 0.25)
    )
    events, _frames = run([Hand(path)], 2.5)
    assert kinds(events) == ["INDEX_SWIPE_RIGHT"]


def test_open_hand_moving_sideways_is_not_a_swipe() -> None:
    # The 0.2 open-hand sweep is no longer a gesture; the index finger must point.
    events, _ = run([Hand(stroke((700, 400), (560, 400), 0.8, 0.25), pose=lambda t: OPEN)], 2.0)
    assert events == []


def test_closed_hand_moving_sideways_is_not_a_swipe() -> None:
    events, _ = run([Hand(stroke((700, 400), (560, 400), 0.8, 0.25), pose=lambda t: FIST)], 2.0)
    assert events == []


def test_small_sideways_movement_is_not_a_swipe() -> None:
    events, _ = run([side_swipe(700, 660)], 2.0)
    assert events == []


@pytest.mark.parametrize("return_at", [1.35, 1.7], ids=["during-cooldown", "after-cooldown"])
def test_return_of_a_side_swipe_is_ignored(return_at: float) -> None:
    path = stroke(
        (700, 400), (540, 400), 0.8, 0.3, then=stroke((540, 400), (700, 400), return_at, 0.3)
    )
    events, frames = run([Hand(path)], 2.8)
    assert kinds(events) == ["INDEX_SWIPE_RIGHT"]
    if return_at > 1.6:  # seen by the recognizer as a stroke, and recognized as the return
        assert "return movement after previous swipe" in rejections(frames)


def test_handedness_label_flip_during_swipe_does_not_cancel_it() -> None:
    # MediaPipe's per-frame handedness label occasionally flips during fast movement; this
    # used to reset the control hand and cancel the stroke.
    def label(t: float) -> Handedness:
        return Handedness.LEFT if 0.85 <= t < 0.95 else Handedness.RIGHT

    hand = Hand(stroke((700, 400), (580, 400), 0.8, 0.25), label=label)
    events, _ = run([hand], 2.0)
    assert kinds(events) == ["INDEX_SWIPE_RIGHT"]


def test_disabled_direction_is_not_read_as_another_direction() -> None:
    settings = GestureSettings(enable_swipe_right=False)
    path = stroke((700, 400), (540, 400), 0.8, 0.3, then=stroke((540, 400), (700, 400), 1.35, 0.3))
    events, frames = run([Hand(path)], 2.5, settings=settings)
    # Neither the disabled swipe nor its return (a movement to the left) produces an event.
    assert events == []
    assert "gesture disabled" in rejections(frames)


# ---------------------------------------------------------------------- static poses


def heart(start: float, end: float, other=FIST) -> Hand:
    return Hand(still(640, 400), pose=lambda t: HALF_HEART if start <= t < end else other)


def test_held_half_heart_triggers_exactly_once() -> None:
    events, _ = run([heart(0.5, 4.0)], 4.5)
    assert kinds(events) == ["HALF_HEART"]
    assert events[0].duration_s >= GestureSettings().half_heart_hold_s


@pytest.mark.parametrize("handedness", [Handedness.RIGHT, Handedness.LEFT])
def test_half_heart_with_either_hand(handedness: Handedness) -> None:
    hand = Hand(still(640, 400), pose=lambda t: HALF_HEART, handedness=handedness)
    events, _ = run([hand], 2.0)
    assert kinds(events) == ["HALF_HEART"]


def test_half_heart_again_after_release_triggers_again() -> None:
    def pose(t: float):
        return HALF_HEART if (0.5 <= t < 1.6 or 2.3 <= t < 3.4) else FIST

    events, _ = run([Hand(still(640, 400), pose=pose)], 4.0)
    assert kinds(events) == ["HALF_HEART", "HALF_HEART"]


def test_brief_half_heart_is_rejected() -> None:
    events, frames = run([heart(0.5, 0.85)], 2.0)
    assert events == []
    assert any(f.rejection and f.rejection.gesture is G.HALF_HEART for f in frames)


def test_half_heart_while_moving_is_rejected() -> None:
    path = stroke((500, 400), (800, 400), 0.5, 1.5)
    events, _ = run([Hand(path, pose=lambda t: HALF_HEART)], 2.5)
    assert events == []


@pytest.mark.parametrize(
    "pose",
    [PINCH, C_SIDEWAYS, THUMBS_UP, POINTING, FIST],
    ids=["pinch", "sideways-c", "thumbs-up", "pointing", "fist"],
)
def test_similar_poses_are_not_a_half_heart(pose) -> None:
    events, _ = run([Hand(still(640, 400), pose=lambda t: pose)], 3.0)
    assert "HALF_HEART" not in kinds(events)


def test_held_stop_pose_toggles_exactly_once() -> None:
    events, _ = run([Hand(still(640, 400), pose=lambda t: OPEN)], 4.0)
    assert kinds(events) == ["STOP_GESTURE"]


def test_pose_classification_flicker_does_not_break_a_hold() -> None:
    def pose(t: float):
        return FIST if 0.9 <= t < 0.95 else HALF_HEART  # one dropped frame

    events, _ = run([Hand(still(640, 400), pose=pose)], 2.0)
    assert kinds(events) == ["HALF_HEART"]


def test_global_cooldown_blocks_a_second_gesture_right_after_the_first() -> None:
    def pose(t: float):
        return HALF_HEART if t < 1.3 else POINTING

    # The half-heart confirms at ~1.1 s; a swipe 0.15 s later falls inside the global cooldown.
    path = stroke((640, 400), (640, 560), 1.25, 0.25)
    events, _ = run([Hand(path, pose=pose)], 2.5)
    assert kinds(events) == ["HALF_HEART"]


# ---------------------------------------------------------------------- control hand


def test_two_hands_appearing_together_suspend_recognition() -> None:
    right = swipe_down()
    left = Hand(still(300, 400), handedness=Handedness.LEFT)
    events, frames = run([right, left], 2.0)
    assert events == []
    assert frames[-1].status is ControlStatus.AMBIGUOUS


def test_second_hand_cannot_issue_gestures_once_control_is_established() -> None:
    control = Hand(stroke((640, 300), (640, 460), 2.0, 0.3))
    intruder_path = stroke((250, 300), (250, 460), 1.2, 0.3)
    intruder = Hand(lambda t: intruder_path(t) if t >= 0.7 else None, handedness=Handedness.LEFT)
    events, _ = run([control, intruder], 3.0)
    assert kinds(events) == ["INDEX_SWIPE_DOWN"]
    assert events[0].handedness is Handedness.RIGHT
    assert events[0].timestamp_ns > 1_000_000_000 + 2.0e9


def test_hands_close_together_are_ambiguous() -> None:
    a = Hand(still(640, 400))
    b = Hand(lambda t: (700, 420) if t > 0.8 else None, handedness=Handedness.LEFT)
    _, frames = run([a, b], 1.5)
    assert frames[-1].status is ControlStatus.AMBIGUOUS
    assert any("close" in f.status_detail for f in frames)


@pytest.mark.parametrize(
    ("preference", "expected"),
    [
        (ControlHandPreference.LEFT, ["INDEX_SWIPE_DOWN"]),
        (ControlHandPreference.RIGHT, []),
    ],
)
def test_control_hand_preference(preference: ControlHandPreference, expected: list[str]) -> None:
    left = Hand(stroke((640, 300), (640, 460), 0.8, 0.3), handedness=Handedness.LEFT)
    events, _ = run([left], 2.0, settings=GestureSettings(control_hand=preference))
    assert kinds(events) == expected


def test_low_handedness_score_is_not_trusted_for_preference() -> None:
    hand = Hand(stroke((640, 300), (640, 460), 0.8, 0.3), score=0.55)
    settings = GestureSettings(control_hand=ControlHandPreference.RIGHT)
    events, frames = run([hand], 2.0, settings=settings)
    assert events == []
    assert frames[-1].status is ControlStatus.NO_HAND


def test_no_hand_status() -> None:
    _, frames = run([Hand(lambda t: None)], 0.3)
    assert frames[-1].status is ControlStatus.NO_HAND


# ---------------------------------------------------------------------- settings


def test_disabled_gesture_never_triggers() -> None:
    events, _ = run([swipe_down()], 2.0, settings=GestureSettings(enable_swipe_down=False))
    assert events == []


def test_presets_change_recognition_thresholds() -> None:
    low = GestureSettings.from_preset(SensitivityPreset.LOW)
    high = GestureSettings.from_preset(SensitivityPreset.HIGH)
    balanced = GestureSettings()
    assert low.swipe_min_distance_palms > balanced.swipe_min_distance_palms
    assert high.swipe_min_distance_palms < balanced.swipe_min_distance_palms
    assert low.stop_hold_s > balanced.stop_hold_s > high.stop_hold_s
    # A 0.72 palm-length swipe passes the high preset only.
    for settings, expected in ((low, []), (balanced, []), (high, ["INDEX_SWIPE_DOWN"])):
        events, _ = run([swipe_down(distance=72, duration=0.2)], 2.0, settings=settings)
        assert kinds(events) == expected


def test_settings_requested_from_another_thread_apply_on_next_update() -> None:
    engine = GestureEngine()
    engine.request_settings(GestureSettings(enable_swipe_down=False))
    events, _ = run([swipe_down()], 2.0, engine=engine)
    assert events == []
    assert engine.settings.enable_swipe_down is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"swipe_min_distance_palms": 0.0},
        {"stop_hold_s": 10.0},
        {"direction_ratio": 0.5},
        {"cooldown_s": -1.0},
    ],
)
def test_invalid_gesture_settings_are_rejected(overrides: dict) -> None:
    with pytest.raises(ConfigError):
        replace(GestureSettings(), **overrides)


def test_custom_is_not_a_preset() -> None:
    with pytest.raises(ConfigError):
        GestureSettings.from_preset(SensitivityPreset.CUSTOM)


def test_reset_forgets_control_hand_and_candidates() -> None:
    engine = GestureEngine()
    run([Hand(still(640, 400))], 1.0, engine=engine)
    engine.reset()
    events, _frames = run([swipe_down(t=0.1)], 1.0, engine=engine)
    assert events == []  # the hand must settle again after a reset


# ---------------------------------------------------------------------- Brief 004 findings


def test_finger_relaxing_into_a_fist_is_not_a_swipe() -> None:
    """Relaxing a pointing finger moves the fingertip like a flick but the finger stays curled
    (synthetic horizontal benchmark, Brief 004): no swipe, with an explanation."""

    def pose(t: float):
        return POINTING if t < 1.0 else (index_curl((t - 1.0) / 0.12) if t < 1.12 else FIST)

    events, frames = run([Hand(still(640, 400), pose=pose, palm_px=140)], 2.5)
    assert events == []
    assert any(f.rejection and "stayed curled" in f.rejection.reason for f in frames)


def test_short_tracking_dropout_during_a_stroke_does_not_cancel_it() -> None:
    base = stroke((640, 300), (640, 450), 0.8, 0.3)

    def position(t: float):
        return None if 0.9 <= t < 1.0 else base(t)  # three frames without a hand

    events, _ = run([Hand(position)], 2.0)
    assert kinds(events) == ["INDEX_SWIPE_DOWN"]


def test_long_tracking_loss_cancels_the_candidate() -> None:
    base = stroke((640, 300), (640, 450), 0.8, 0.3)

    def position(t: float):
        return None if 0.95 <= t < 1.4 else base(t)

    events, frames = run([Hand(position)], 2.0)
    assert events == []
    assert any(f.rejection and f.rejection.code == "tracking_lost" for f in frames)


def test_rejections_report_measured_and_required_values() -> None:
    events, frames = run([Hand(stroke((640, 300), (640, 345), 0.8, 0.2))], 2.0)
    assert events == []
    (short,) = [f.rejection for f in frames if f.rejection and f.rejection.code == "too_short"]
    assert short.gesture is G.INDEX_SWIPE_DOWN
    assert short.unit == "palms" and short.required == 0.8
    assert 0.2 < short.measured < 0.8


def test_small_hand_gets_a_positioning_hint() -> None:
    _, frames = run([Hand(still(640, 400), palm_px=40)], 1.0)
    assert any("closer" in f.hint for f in frames)
    _, frames = run([Hand(still(640, 400), palm_px=120)], 1.0)
    assert not any(f.hint for f in frames)


def test_low_frame_rate_gets_a_hint() -> None:
    _, frames = run([Hand(still(640, 400), palm_px=120)], 2.0, fps=12.0)
    assert any("frame rate" in f.hint for f in frames[-5:])
    _, frames = run([Hand(still(640, 400), palm_px=120)], 2.0, fps=30.0)
    assert not any(f.hint for f in frames)


def test_hand_swipes_work_at_15_fps() -> None:
    """Brief 004 frame-rate check: hand movements stayed 8/8 at 15 fps on the recordings."""
    events, _ = run([swipe_down(distance=150, duration=0.35)], 2.0, fps=15.0)
    assert kinds(events) == ["INDEX_SWIPE_DOWN"]
