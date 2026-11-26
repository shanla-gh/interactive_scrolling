"""The real MediaPipe hand landmarker on still images (no webcam required)."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from interactive_scrolling.config.settings import TrackingSettings
from interactive_scrolling.vision.hand_tracker import MediaPipeHandTracker
from interactive_scrolling.vision.landmarks import Handedness

pytestmark = pytest.mark.model


@pytest.fixture
def tracker(model_path: Path):
    instance = MediaPipeHandTracker(TrackingSettings(num_hands=2), model_path)
    yield instance
    instance.close()


def load_rgb(path: Path) -> np.ndarray:
    image = cv2.imread(str(path))
    assert image is not None
    return np.ascontiguousarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))


def test_blank_frames_contain_no_hands(tracker: MediaPipeHandTracker) -> None:
    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    for t in range(0, 100, 33):
        assert tracker.process(blank, t) == ()


def test_duplicate_and_decreasing_timestamps_are_tolerated(tracker: MediaPipeHandTracker) -> None:
    blank = np.zeros((240, 320, 3), dtype=np.uint8)
    tracker.process(blank, 100)
    tracker.process(blank, 100)
    tracker.process(blank, 50)


def test_closed_tracker_rejects_use(model_path: Path) -> None:
    instance = MediaPipeHandTracker(TrackingSettings(), model_path)
    instance.close()
    instance.close()
    with pytest.raises(RuntimeError):
        instance.process(np.zeros((10, 10, 3), np.uint8), 0)


@pytest.mark.network
def test_detects_two_real_hands_with_correct_handedness(
    tracker: MediaPipeHandTracker, sample_hands_image_path: Path
) -> None:
    rgb = load_rgb(sample_hands_image_path)
    hands = tracker.process(rgb, 0)
    assert len(hands) == 2
    for hand in hands:
        assert hand.landmarks.shape == (21, 3)
        assert np.all(hand.landmarks[:, :2] > -0.05) and np.all(hand.landmarks[:, :2] < 1.05)
        assert hand.handedness_score is not None and 0.5 < hand.handedness_score <= 1.0
        assert hand.world_landmarks is not None
    # In this photo the subject's right hand rests on her forehead (upper hand) and her left
    # hand reaches towards the camera (lower hand). On the unmirrored image the model must
    # report the subject's own hands.
    upper, lower = sorted(hands, key=lambda h: h.palm_center()[1])
    assert upper.handedness is Handedness.RIGHT
    assert lower.handedness is Handedness.LEFT


@pytest.mark.network
def test_mirrored_input_mirrors_coordinates_and_swaps_handedness(
    model_path: Path, sample_hands_image_path: Path
) -> None:
    """Documents why inference runs on the unmirrored frame and mirroring is display-only."""
    rgb = load_rgb(sample_hands_image_path)
    settings = TrackingSettings(num_hands=2)
    plain_tracker = MediaPipeHandTracker(settings, model_path)
    mirror_tracker = MediaPipeHandTracker(settings, model_path)
    try:
        plain = plain_tracker.process(rgb, 0)
        mirrored = mirror_tracker.process(np.ascontiguousarray(rgb[:, ::-1]), 0)
    finally:
        plain_tracker.close()
        mirror_tracker.close()
    assert len(plain) == len(mirrored) == 2
    for hand in plain:
        center = hand.palm_center()
        twin = min(
            mirrored, key=lambda m: np.hypot(*(m.palm_center() - [1 - center[0], center[1]]))
        )
        assert twin.palm_center()[0] == pytest.approx(1 - center[0], abs=0.02)
        assert twin.palm_center()[1] == pytest.approx(center[1], abs=0.02)
        assert twin.handedness is hand.handedness.swapped()


@pytest.mark.network
def test_tracking_in_video_mode_is_stable_across_frames(
    tracker: MediaPipeHandTracker, sample_hands_image_path: Path
) -> None:
    rgb = load_rgb(sample_hands_image_path)
    results = [tracker.process(rgb, t * 33) for t in range(10)]
    assert all(len(r) == 2 for r in results)
    first = sorted(results[0], key=lambda h: h.palm_center()[1])
    last = sorted(results[-1], key=lambda h: h.palm_center()[1])
    for a, b in zip(first, last, strict=True):
        # Identical input frames should give nearly identical landmarks (< 1 % of the image).
        assert np.max(np.abs(a.landmarks[:, :2] - b.landmarks[:, :2])) < 0.01
        assert a.handedness is b.handedness
    # The hand disappears: no stale landmarks are reported.
    assert tracker.process(np.zeros_like(rgb), 1000) == ()
