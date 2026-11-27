"""Brief 006: one motion engine for every hand shape (default "Swipe with: any hand shape").

A pointing hand is followed at the fingertip (finger flicks included, as in 0.5); every other
onset shape at the palm centre, activated by a hand that was settled before it moved. The hand
shape may change during the movement.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from interactive_scrolling.config.settings import GestureSettings
from interactive_scrolling.gestures.pose import PoseLabel
from interactive_scrolling.vision.landmarks import Handedness
from tests.gesture_helpers import (
    FIST,
    HALF_HEART,
    OPEN,
    POINTING,
    Hand,
    chain,
    index_curl,
    kinds,
    run,
    still,
    stroke,
)

MOVES = [
    (0, -80, "INDEX_SWIPE_UP"),
    (0, 80, "INDEX_SWIPE_DOWN"),
    (-80, 0, "INDEX_SWIPE_RIGHT"),  # image left = the user's right
    (80, 0, "INDEX_SWIPE_LEFT"),
]


def test_any_hand_shape_is_the_default() -> None:
    assert GestureSettings().control_style == "motion"


@pytest.mark.parametrize(("dx", "dy", "expected"), MOVES)
@pytest.mark.parametrize("handedness", [Handedness.RIGHT, Handedness.LEFT])
@pytest.mark.parametrize("shape", [FIST, index_curl(0.6)], ids=["fist", "relaxed"])
def test_settled_hand_of_any_shape_moved_is_a_swipe(dx, dy, expected, handedness, shape) -> None:
    hand = Hand(
        stroke((640, 380), (640 + dx, 380 + dy), 1.0, 0.2),
        pose=lambda t: shape,
        handedness=handedness,
    )
    events, _ = run([hand], 2.2)
    assert kinds(events) == [expected]
    assert events[0].detector == "hand"


def test_pointing_hand_still_uses_the_fingertip_path() -> None:
    events, _ = run([Hand(stroke((640, 300), (640, 400), 1.0, 0.2))], 2.2)
    assert kinds(events) == ["INDEX_SWIPE_DOWN"]
    assert events[0].detector == "finger"


def test_hand_shape_change_during_the_movement_does_not_cancel_it() -> None:
    """A fist that opens while it moves sideways is still one swipe."""
    events, _ = run(
        [Hand(stroke((700, 380), (600, 380), 1.0, 0.2), pose=lambda t: FIST if t < 1.08 else OPEN)],
        2.2,
    )
    assert kinds(events) == ["INDEX_SWIPE_RIGHT"]


def test_hand_that_was_not_settled_before_moving_is_not_a_swipe() -> None:
    """Moving a closed hand around (no pause before the movement) is ordinary activity."""
    path = chain(
        (0.0, stroke((500, 380), (600, 380), 0.0, 0.9)),
        (0.9, stroke((600, 380), (520, 380), 0.9, 0.25)),
    )
    events, _ = run([Hand(path, pose=lambda t: FIST)], 2.0)
    assert events == []


def test_fist_held_still_or_opened_and_closed_in_place_is_not_a_swipe() -> None:
    events, _ = run([Hand(still(640, 400), pose=lambda t: FIST if int(t * 3) % 2 else OPEN)], 3.0)
    assert [k for k in kinds(events) if "SWIPE" in k] == []


def test_one_physical_swipe_gives_one_event_and_its_return_is_suppressed() -> None:
    path = stroke((640, 380), (640, 300), 1.0, 0.2, then=stroke((640, 300), (640, 380), 1.4, 0.3))
    events, _ = run([Hand(path, pose=lambda t: FIST)], 2.8)
    assert kinds(events) == ["INDEX_SWIPE_UP"]


def test_fist_lowered_out_of_view_is_not_a_swipe() -> None:
    base = stroke((640, 520), (640, 800), 1.0, 0.35)

    def position(t: float):
        p = base(t)
        return None if p[1] > 690 else p

    events, _ = run([Hand(position, pose=lambda t: FIST)], 2.2)
    assert events == []


def test_downward_hand_swipe_that_stops_in_view_is_confirmed() -> None:
    events, _ = run([Hand(stroke((640, 300), (640, 400), 1.0, 0.2), pose=lambda t: FIST)], 2.2)
    assert kinds(events) == ["INDEX_SWIPE_DOWN"]


def test_hand_lost_at_rest_and_found_elsewhere_is_not_a_swipe() -> None:
    """Brief 006: a tracking gap followed by re-acquisition two hand lengths away was confirmed
    as a swipe (recorded in a rest segment); no movement was observed."""

    def position(t: float):
        if t < 1.0:
            return (640, 400)
        if t < 1.2:
            return None
        return (840, 400)

    events, _ = run([Hand(position, pose=lambda t: FIST)], 2.2)
    assert events == []


def test_lowering_the_hand_after_a_half_heart_is_not_a_swipe() -> None:
    """Moving the hand away after a static gesture is a release, not a swipe."""
    path = stroke((640, 300), (640, 400), 1.8, 0.25)
    events, _ = run([Hand(path, pose=lambda t: HALF_HEART)], 3.0)
    assert [k for k in kinds(events) if "SWIPE" in k] == []


def test_pointing_finger_only_keeps_the_0_5_behaviour() -> None:
    finger_only = replace(GestureSettings(), control_style="finger")
    events, _ = run(
        [Hand(stroke((640, 380), (560, 380), 1.0, 0.2), pose=lambda t: FIST)], 2.2, finger_only
    )
    assert events == []


def test_hand_shape_predicate_excludes_pointing_and_static_gestures() -> None:
    from interactive_scrolling.gestures.pose import analyze_pose
    from interactive_scrolling.gestures.recognizers import hand_shape
    from tests.gesture_helpers import H, W, make_observation

    def pose(shape):  # type: ignore[no-untyped-def]
        return analyze_pose(make_observation(shape, (640, 400)), W, H)

    assert pose(POINTING).label is PoseLabel.POINTING and not hand_shape(pose(POINTING))
    assert not hand_shape(pose(HALF_HEART))
    assert hand_shape(pose(FIST))
