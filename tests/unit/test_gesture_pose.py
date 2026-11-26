"""Static hand pose analysis."""

from __future__ import annotations

import pytest

from interactive_scrolling.gestures.pose import PoseLabel, analyze_pose
from tests.gesture_helpers import (
    C_SIDEWAYS,
    FIST,
    HALF_HEART,
    OPEN,
    PINCH,
    POINTING,
    THUMBS_DOWN,
    THUMBS_UP,
    H,
    Pose,
    W,
)
from tests.gesture_helpers import make_observation as obs


@pytest.mark.parametrize("mirror", [False, True], ids=["right-hand", "left-hand"])
@pytest.mark.parametrize(
    ("pose", "label"),
    [
        (OPEN, PoseLabel.OPEN_PALM),
        (POINTING, PoseLabel.POINTING),
        (FIST, PoseLabel.FIST),
        (THUMBS_UP, PoseLabel.THUMBS_UP),
        (THUMBS_DOWN, PoseLabel.FIST),
        (HALF_HEART, PoseLabel.HALF_HEART),
        (PINCH, PoseLabel.FIST),
        (C_SIDEWAYS, PoseLabel.FIST),
    ],
)
def test_pose_labels(pose: Pose, label: PoseLabel, mirror: bool) -> None:
    assert analyze_pose(obs(pose, (600, 500), mirror=mirror), W, H).label is label


@pytest.mark.parametrize("palm_px", [40.0, 100.0, 220.0])
def test_pose_is_independent_of_hand_size(palm_px: float) -> None:
    for pose, label in ((OPEN, PoseLabel.OPEN_PALM), (POINTING, PoseLabel.POINTING)):
        assert analyze_pose(obs(pose, (600, 500), palm_px), W, H).label is label


def test_stop_pose_requires_upright_open_hand() -> None:
    upright = analyze_pose(obs(OPEN, (600, 500)), W, H)
    assert upright.is_stop_pose
    sideways = Pose(OPEN.fingers, OPEN.thumb_dir, OPEN.thumb_bend, roll_deg=80.0)
    tilted = analyze_pose(obs(sideways, (600, 500)), W, H)
    assert tilted.label is PoseLabel.OPEN_PALM
    assert not tilted.is_stop_pose


def test_partially_bent_fingers_are_uncertain_not_open() -> None:
    half = Pose({f: (30.0, 40.0, 30.0) for f in OPEN.fingers}, OPEN.thumb_dir, OPEN.thumb_bend)
    pose = analyze_pose(obs(half, (600, 500)), W, H)
    assert pose.label is PoseLabel.OTHER
    assert all(state.value == "uncertain" for name, state in pose.states.items() if name != "thumb")


def test_thumb_must_point_up_for_thumbs_up() -> None:
    tilted = Pose(THUMBS_UP.fingers, THUMBS_UP.thumb_dir, THUMBS_UP.thumb_bend, roll_deg=30.0)
    pose = analyze_pose(obs(tilted, (600, 500)), W, H)
    assert pose.label is PoseLabel.FIST
    assert pose.thumb_up_alignment < 0.77


@pytest.mark.parametrize("palm_px", [50.0, 100.0, 200.0])
@pytest.mark.parametrize("mirror", [False, True], ids=["right-hand", "left-hand"])
def test_half_heart_geometry_is_size_and_hand_independent(palm_px: float, mirror: bool) -> None:
    pose = analyze_pose(obs(HALF_HEART, (600, 500), palm_px, mirror=mirror), W, H)
    assert pose.label is PoseLabel.HALF_HEART
    heart = pose.heart
    assert heart is not None
    assert heart.hook > 0.12 and heart.same_side
    assert 0.3 <= heart.gap <= 2.2


def test_pinch_is_not_a_half_heart() -> None:
    # Thumb tip close to the index tip: an ordinary pinch.
    pose = analyze_pose(obs(PINCH, (600, 500)), W, H)
    assert pose.label is not PoseLabel.HALF_HEART
    assert pose.heart is not None and pose.heart.gap < 0.5


def test_sideways_c_shape_is_not_a_half_heart() -> None:
    pose = analyze_pose(obs(C_SIDEWAYS, (600, 500)), W, H)
    assert pose.label is not PoseLabel.HALF_HEART
    assert pose.fingers_up_alignment < 0.4
