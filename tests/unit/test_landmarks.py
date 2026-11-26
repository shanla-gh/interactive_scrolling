"""Landmark representation and coordinate transforms."""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from interactive_scrolling.vision.landmarks import (
    FINGERTIPS,
    HAND_CONNECTIONS,
    NUM_LANDMARKS,
    Handedness,
    HandLandmark,
    HandObservation,
    TrackingResult,
    palm_length_px,
    to_pixels,
)
from tests.helpers import make_hand


def test_skeleton_has_21_anatomical_bones() -> None:
    assert len(HAND_CONNECTIONS) == 21
    assert len(set(HAND_CONNECTIONS)) == 21
    nodes = {i for pair in HAND_CONNECTIONS for i in pair}
    assert nodes == set(range(NUM_LANDMARKS))


def test_skeleton_is_connected() -> None:
    adjacency: dict[int, set[int]] = {i: set() for i in range(NUM_LANDMARKS)}
    for a, b in HAND_CONNECTIONS:
        adjacency[a].add(b)
        adjacency[b].add(a)
    seen, stack = set(), [HandLandmark.WRIST]
    while stack:
        node = stack.pop()
        if node not in seen:
            seen.add(node)
            stack.extend(adjacency[node])
    assert seen == set(range(NUM_LANDMARKS))
    # Fingertips are chain ends.
    for tip in FINGERTIPS:
        assert len(adjacency[tip]) == 1


@pytest.mark.parametrize(
    "chain",
    [
        (1, 2, 3, 4),
        (5, 6, 7, 8),
        (9, 10, 11, 12),
        (13, 14, 15, 16),
        (17, 18, 19, 20),
    ],
)
def test_each_finger_is_a_chain(chain: tuple[int, ...]) -> None:
    for a, b in itertools.pairwise(chain):
        assert (a, b) in HAND_CONNECTIONS


def test_skeleton_matches_mediapipe_definition() -> None:
    from mediapipe.tasks.python.vision.hand_landmarker import HandLandmarksConnections

    reference = {(c.start, c.end) for c in HandLandmarksConnections.HAND_CONNECTIONS}
    assert set(HAND_CONNECTIONS) == reference


def test_landmark_indices_match_mediapipe() -> None:
    from mediapipe.tasks.python.vision.hand_landmarker import HandLandmark as MpHandLandmark

    for member in HandLandmark:
        assert MpHandLandmark[member.name].value == member.value


def test_to_pixels_uses_width_for_x_and_height_for_y() -> None:
    px = to_pixels(np.array([[0.5, 0.25], [1.0, 1.0]]), 640, 480)
    assert px.tolist() == [[320.0, 120.0], [640.0, 480.0]]


def test_palm_length_is_isotropic_in_pixels() -> None:
    hand = make_hand((320, 400), palm_px=120, width=1280, height=720)
    assert palm_length_px(hand.landmarks, 1280, 720) == pytest.approx(120.0, rel=1e-4)


def test_bounding_box_and_palm_center() -> None:
    hand = make_hand((320, 400), palm_px=100)
    x0, y0, x1, y1 = hand.bounding_box()
    pixels = hand.pixel_points(640, 480)
    assert (x0 * 640, x1 * 640) == pytest.approx((pixels[:, 0].min(), pixels[:, 0].max()), abs=1e-3)
    assert (y0 * 480, y1 * 480) == pytest.approx((pixels[:, 1].min(), pixels[:, 1].max()), abs=1e-3)
    center = hand.palm_center()
    assert x0 <= center[0] <= x1 and y0 <= center[1] <= y1


def test_observation_validates_shape() -> None:
    with pytest.raises(ValueError, match="21, 3"):
        HandObservation(landmarks=np.zeros((20, 3), dtype=np.float32))
    with pytest.raises(ValueError, match="world_landmarks"):
        HandObservation(
            landmarks=np.zeros((21, 3), dtype=np.float32),
            world_landmarks=np.zeros((5, 3), dtype=np.float32),
        )


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Left", Handedness.LEFT),
        ("right", Handedness.RIGHT),
        (" RIGHT ", Handedness.RIGHT),
        ("", Handedness.UNKNOWN),
        (None, Handedness.UNKNOWN),
        ("Both", Handedness.UNKNOWN),
    ],
)
def test_handedness_from_label(label: str | None, expected: Handedness) -> None:
    assert Handedness.from_label(label) is expected


def test_handedness_swapped() -> None:
    assert Handedness.LEFT.swapped() is Handedness.RIGHT
    assert Handedness.RIGHT.swapped() is Handedness.LEFT
    assert Handedness.UNKNOWN.swapped() is Handedness.UNKNOWN


def test_tracking_result_counts() -> None:
    result = TrackingResult(
        frame_index=3,
        timestamp_ns=10,
        image_width=640,
        image_height=480,
        hands=(make_hand((100, 300)), make_hand((400, 300))),
    )
    assert result.hand_count == 2
    assert result.landmark_count == 42
    assert TrackingResult(0, 0, 640, 480).landmark_count == 0
