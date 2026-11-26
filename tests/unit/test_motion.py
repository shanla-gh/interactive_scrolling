"""Motion analysis on controlled synthetic hand sequences."""

from __future__ import annotations

import math

import numpy as np
import pytest

from interactive_scrolling.config.settings import ConfigError, MotionSettings
from interactive_scrolling.motion.analyzer import (
    Direction,
    MotionAnalyzer,
    classify_direction,
    smoothing_alpha,
)
from interactive_scrolling.vision.landmarks import Handedness
from tests.helpers import INDEX_TIP_OFFSET, PALM_CENTER_OFFSET, make_hand, tracking

MS = 1_000_000
# Landmarks are float32 (as produced by MediaPipe) and timestamps are integer nanoseconds,
# so "exact" results are compared with a relative tolerance of 1e-5.
UNSMOOTHED = MotionSettings(position_time_constant_s=0.0, velocity_time_constant_s=0.0)


def run_linear(
    analyzer: MotionAnalyzer,
    velocity: tuple[float, float],
    frames: int,
    dt_ms: float = 1000 / 30,
    start: tuple[float, float] = (200.0, 300.0),
    palm_px: float = 100.0,
    t0_ns: int = 1_000 * MS,
):
    """Feed a hand moving at constant ``velocity`` (px/s); return the motion frames."""
    results = []
    for i in range(frames):
        t = i * dt_ms / 1000
        wrist = (start[0] + velocity[0] * t, start[1] + velocity[1] * t)
        ts = t0_ns + round(i * dt_ms * MS)
        results.append(analyzer.update(tracking(ts, (make_hand(wrist, palm_px),))))
    return results


# ---------------------------------------------------------------------- direction


@pytest.mark.parametrize(
    ("vector", "expected"),
    [
        ((1, 0), Direction.RIGHT),
        ((-1, 0), Direction.LEFT),
        ((0, -1), Direction.UP),  # image y grows downwards
        ((0, 1), Direction.DOWN),
        ((1, -1), Direction.UP_RIGHT),
        ((-1, -1), Direction.UP_LEFT),
        ((1, 1), Direction.DOWN_RIGHT),
        ((-1, 1), Direction.DOWN_LEFT),
        ((10, -3), Direction.RIGHT),  # 16.7 degrees: still within the RIGHT sector
        ((10, -5), Direction.UP_RIGHT),  # 26.6 degrees: beyond the 22.5 degree boundary
        ((0, 0), Direction.NONE),
    ],
)
def test_classify_direction(vector: tuple[float, float], expected: Direction) -> None:
    assert classify_direction(*vector) is expected


def test_mirrored_direction_swaps_horizontal_component() -> None:
    assert Direction.RIGHT.mirrored() is Direction.LEFT
    assert Direction.UP_LEFT.mirrored() is Direction.UP_RIGHT
    assert Direction.DOWN.mirrored() is Direction.DOWN
    assert Direction.NONE.mirrored() is Direction.NONE
    for direction in Direction:
        assert direction.mirrored().mirrored() is direction


def test_smoothing_alpha() -> None:
    assert smoothing_alpha(0.033, 0.0) == 1.0
    assert smoothing_alpha(0.05, 0.05) == pytest.approx(1 - math.exp(-1))
    # Frame-rate independence: two half steps equal one full step.
    half = smoothing_alpha(0.01, 0.04)
    full = smoothing_alpha(0.02, 0.04)
    assert 1 - (1 - half) ** 2 == pytest.approx(full)


# ---------------------------------------------------------------------- velocity


def test_constant_velocity_unsmoothed_is_exact() -> None:
    results = run_linear(MotionAnalyzer(UNSMOOTHED), (300.0, 0.0), frames=10)
    first = results[0].hands[0]
    assert first.reset and first.fingertip.speed_px_s == 0.0
    for frame in results[1:]:
        tip = frame.hands[0].fingertip
        assert tip.velocity_px_s == pytest.approx((300.0, 0.0), rel=1e-5)
        assert tip.frame_displacement_px == pytest.approx((10.0, 0.0), abs=1e-6)
        assert tip.speed_palms_s == pytest.approx(3.0, rel=1e-5)
        assert tip.is_moving and tip.direction is Direction.RIGHT
    assert results[-1].hands[0].palm.velocity_px_s == pytest.approx((300.0, 0.0), rel=1e-5)


def test_positions_are_tracked_in_source_pixels() -> None:
    results = run_linear(MotionAnalyzer(UNSMOOTHED), (0.0, 0.0), frames=2, start=(200, 300))
    hand = results[-1].hands[0]
    assert hand.fingertip.position_px == pytest.approx(
        tuple(np.add((200, 300), INDEX_TIP_OFFSET * 100)), abs=1e-3
    )
    assert hand.palm.position_px == pytest.approx(
        tuple(np.add((200, 300), PALM_CENTER_OFFSET * 100)), abs=1e-3
    )
    assert hand.palm_length_px == pytest.approx(100.0, rel=1e-4)


def test_irregular_frame_intervals_use_timestamps() -> None:
    analyzer = MotionAnalyzer(UNSMOOTHED)
    velocity = np.array([0.0, -250.0])  # moving up
    t_ms = 0.0
    for i, dt in enumerate([20, 50, 20, 80, 10, 45, 33]):
        t_ms += dt
        wrist = np.array([300.0, 400.0]) + velocity * t_ms / 1000
        frame = analyzer.update(tracking(round(t_ms * MS), (make_hand(tuple(wrist)),)))
        if i > 0:
            assert frame.hands[0].fingertip.velocity_px_s == pytest.approx((0.0, -250.0), rel=1e-5)
            assert frame.hands[0].fingertip.direction is Direction.UP


def test_smoothed_velocity_converges_to_true_velocity() -> None:
    results = run_linear(MotionAnalyzer(), (-180.0, 120.0), frames=45)
    vx, vy = results[-1].hands[0].fingertip.velocity_px_s
    assert vx == pytest.approx(-180.0, rel=0.02)
    assert vy == pytest.approx(120.0, rel=0.02)
    assert results[-1].hands[0].fingertip.direction is Direction.DOWN_LEFT


def test_window_displacement_measures_net_movement() -> None:
    settings = MotionSettings(
        position_time_constant_s=0.0, velocity_time_constant_s=0.0, displacement_window_s=0.2
    )
    results = run_linear(MotionAnalyzer(settings), (300.0, 0.0), frames=20, dt_ms=25)
    assert results[-1].hands[0].fingertip.window_displacement_px == pytest.approx(
        (60.0, 0.0), abs=1e-6
    )


@pytest.mark.parametrize("palm_px", [50.0, 100.0, 150.0])
def test_normalized_speed_is_independent_of_hand_size(palm_px: float) -> None:
    # The same movement of two palm lengths per second at different distances from the camera.
    results = run_linear(
        MotionAnalyzer(UNSMOOTHED), (2.0 * palm_px, 0.0), frames=6, palm_px=palm_px
    )
    tip = results[-1].hands[0].fingertip
    assert tip.speed_palms_s == pytest.approx(2.0, rel=1e-4)
    assert tip.speed_px_s == pytest.approx(2.0 * palm_px, rel=1e-5)


# ---------------------------------------------------------------------- stationary noise


def test_stationary_hand_with_landmark_jitter_is_not_moving() -> None:
    rng = np.random.default_rng(1234)
    analyzer = MotionAnalyzer()
    moving_frames = 0
    for i in range(90):  # 3 s at 30 FPS
        noise = rng.normal(0.0, 0.8, size=2)  # 0.8 px jitter on a 100 px palm
        frame = analyzer.update(
            tracking(i * 33 * MS, (make_hand((320 + noise[0], 360 + noise[1])),))
        )
        hand = frame.hands[0]
        moving_frames += hand.fingertip.is_moving or hand.palm.is_moving
        if not hand.fingertip.is_moving:
            assert hand.fingertip.direction is Direction.NONE
    assert moving_frames == 0


def test_hysteresis_keeps_state_between_thresholds() -> None:
    settings = MotionSettings(
        position_time_constant_s=0.0,
        velocity_time_constant_s=0.0,
        moving_threshold_palms_per_s=1.0,
        stationary_threshold_palms_per_s=0.5,
    )
    analyzer = MotionAnalyzer(settings)
    wrist_x, t_ms = 100.0, 0
    states = []
    for speed in [0, 80, 120, 80, 60, 40, 80]:  # px/s with a 100 px palm
        t_ms += 50
        wrist_x += speed * 0.05
        frame = analyzer.update(tracking(t_ms * MS, (make_hand((wrist_x, 300)),)))
        states.append(frame.hands[0].fingertip.is_moving)
    # 0.8 palms/s does not start motion; 1.2 does; 0.8 and 0.6 sustain it; 0.4 ends it.
    assert states == [False, False, True, True, True, False, False]


# ---------------------------------------------------------------------- loss handling


def test_hand_disappearance_produces_no_motion_entries() -> None:
    analyzer = MotionAnalyzer()
    run_linear(analyzer, (200.0, 0.0), frames=5)
    frame = analyzer.update(tracking(2_000 * MS, ()))
    assert frame.hands == ()


def test_reacquisition_after_loss_has_no_velocity_spike() -> None:
    analyzer = MotionAnalyzer()
    results = run_linear(analyzer, (200.0, 0.0), frames=10, start=(100, 300))
    last_ns = 1_000 * MS + round(9 * 1000 / 30 * MS)
    # Hand lost for half a second (longer than max_observation_gap_s)...
    for k in range(1, 15):
        assert analyzer.update(tracking(last_ns + k * 33 * MS, ())).hands == ()
    # ...and reappears far away.
    frame = analyzer.update(tracking(last_ns + 500 * MS, (make_hand((520, 200)),)))
    hand = frame.hands[0]
    assert hand.reset
    assert hand.track_id != results[-1].hands[0].track_id
    assert hand.fingertip.speed_px_s == 0.0 and not hand.fingertip.is_moving
    assert len(hand.fingertip_trail) == 1


def test_short_dropout_keeps_track_and_valid_velocity() -> None:
    analyzer = MotionAnalyzer(UNSMOOTHED)
    results = run_linear(analyzer, (300.0, 0.0), frames=5, dt_ms=40, t0_ns=0)
    track_id = results[-1].hands[0].track_id
    analyzer.update(tracking(200 * MS, ()))  # one missed detection
    frame = analyzer.update(tracking(240 * MS, (make_hand((200 + 300 * 0.24, 300)),)))
    hand = frame.hands[0]
    assert not hand.reset and hand.track_id == track_id
    assert hand.fingertip.velocity_px_s == pytest.approx((300.0, 0.0), rel=1e-5)


def test_large_jump_resets_instead_of_spiking() -> None:
    analyzer = MotionAnalyzer(UNSMOOTHED)
    run_linear(analyzer, (0.0, 0.0), frames=3, t0_ns=0)
    # 5 palm lengths in 33 ms would be a 15 palms/s spike if trusted.
    frame = analyzer.update(tracking(100 * MS, (make_hand((700, 300)),)))
    hand = frame.hands[0]
    assert hand.reset
    assert hand.fingertip.speed_px_s == 0.0 and not hand.fingertip.is_moving


def test_non_increasing_timestamps_are_ignored() -> None:
    analyzer = MotionAnalyzer(UNSMOOTHED)
    run_linear(analyzer, (300.0, 0.0), frames=3, t0_ns=0, dt_ms=40)
    stale = analyzer.update(tracking(40 * MS, (make_hand((500, 300)),)))
    assert stale.hands == ()
    frame = analyzer.update(tracking(120 * MS, (make_hand((200 + 300 * 0.12, 300)),)))
    assert frame.hands[0].fingertip.velocity_px_s == pytest.approx((300.0, 0.0), rel=1e-5)


def test_reset_forgets_tracks() -> None:
    analyzer = MotionAnalyzer()
    run_linear(analyzer, (100.0, 0.0), frames=3)
    assert analyzer.active_track_count == 1
    analyzer.reset()
    assert analyzer.active_track_count == 0


# ---------------------------------------------------------------------- multiple hands


def test_two_hands_keep_identity_while_crossing() -> None:
    analyzer = MotionAnalyzer(UNSMOOTHED)
    ids: dict[Handedness, set[int]] = {Handedness.LEFT: set(), Handedness.RIGHT: set()}
    for i in range(30):
        t = i / 30
        right = make_hand((200 + 300 * t, 300), handedness=Handedness.RIGHT)
        left = make_hand((500 - 300 * t, 320), handedness=Handedness.LEFT)
        hands = (left, right) if i % 2 else (right, left)  # detection order changes
        frame = analyzer.update(tracking(i * 33 * MS, hands))
        for motion in frame.hands:
            observed = hands[motion.observation_index].handedness
            assert motion.handedness is observed
            ids[observed].add(motion.track_id)
            if i > 1:
                expected = 1 if observed is Handedness.RIGHT else -1
                assert np.sign(motion.palm.velocity_px_s[0]) == expected
    assert len(ids[Handedness.LEFT]) == 1 and len(ids[Handedness.RIGHT]) == 1
    assert ids[Handedness.LEFT] != ids[Handedness.RIGHT]


def test_motion_frame_lookup_by_observation() -> None:
    analyzer = MotionAnalyzer()
    frame = analyzer.update(
        tracking(0, (make_hand((100, 300)), make_hand((500, 300), handedness=Handedness.LEFT)))
    )
    assert frame.for_observation(1) is frame.hands[1]
    assert frame.for_observation(2) is None


# ---------------------------------------------------------------------- trails


def test_trail_is_bounded_by_duration() -> None:
    settings = MotionSettings(trail_duration_s=0.3)
    results = run_linear(MotionAnalyzer(settings), (200.0, 50.0), frames=60)
    hand = results[-1].hands[0]
    ages = [(hand.timestamp_ns - p.timestamp_ns) / 1e9 for p in hand.fingertip_trail]
    assert max(ages) <= 0.3 + 1e-9
    assert len(hand.fingertip_trail) >= 9
    assert len(hand.palm_trail) == len(hand.fingertip_trail)
    # The trail ends at the current smoothed position and follows the movement direction.
    assert (hand.fingertip_trail[-1].x, hand.fingertip_trail[-1].y) == pytest.approx(
        hand.fingertip.position_px
    )
    assert hand.fingertip_trail[-1].x > hand.fingertip_trail[0].x


# ---------------------------------------------------------------------- settings


@pytest.mark.parametrize(
    "kwargs",
    [
        {"position_time_constant_s": -1},
        {"moving_threshold_palms_per_s": 0.1, "stationary_threshold_palms_per_s": 0.2},
        {"max_observation_gap_s": 0},
        {"trail_duration_s": 0},
        {"history_capacity": 1},
    ],
)
def test_invalid_motion_settings_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ConfigError):
        MotionSettings(**kwargs)
