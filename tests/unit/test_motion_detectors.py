"""Brief 005 motion-first detectors: fist swipes, hybrid control and shared return memory."""

from __future__ import annotations

from dataclasses import replace

import pytest

from interactive_scrolling.config.settings import GestureSettings
from interactive_scrolling.gestures.engine import GestureEngine
from interactive_scrolling.gestures.types import GestureType
from interactive_scrolling.vision.landmarks import Handedness
from tests.gesture_helpers import FIST, OPEN, POINTING, Hand, chain, kinds, run, still, stroke

G = GestureType


def engine(style: str = "hybrid") -> GestureEngine:
    return GestureEngine(replace(GestureSettings(), control_style=style))


@pytest.mark.parametrize(
    ("dx", "dy", "expected"),
    [
        (0, -70, "INDEX_SWIPE_UP"),
        (0, 70, "INDEX_SWIPE_DOWN"),
        (-70, 0, "INDEX_SWIPE_RIGHT"),  # image left = the user's right
        (70, 0, "INDEX_SWIPE_LEFT"),
    ],
)
@pytest.mark.parametrize("handedness", [Handedness.RIGHT, Handedness.LEFT])
def test_held_fist_moved_is_a_fist_swipe(dx, dy, expected, handedness) -> None:
    hand = Hand(
        stroke((640, 400), (640 + dx, 400 + dy), 0.9, 0.2),
        pose=lambda t: FIST,
        handedness=handedness,
    )
    events, _ = run([hand], 2.0, engine=engine("fist"))
    assert kinds(events) == [expected]
    assert events[0].detector == "fist"


def test_finger_style_ignores_fist_movements() -> None:
    hand = Hand(stroke((640, 400), (640, 330), 0.9, 0.2), pose=lambda t: FIST)
    events, _ = run([hand], 2.0, engine=engine("finger"))
    assert events == []


def test_stationary_fist_never_swipes() -> None:
    events, _ = run([Hand(still(640, 400), pose=lambda t: FIST)], 4.0, engine=engine())
    assert events == []


def test_opening_and_closing_the_hand_in_place_is_not_a_swipe() -> None:
    def pose(t: float):
        return FIST if int(t / 0.6) % 2 == 0 else OPEN

    events, _ = run([Hand(still(640, 400), pose=pose)], 4.0, engine=engine())
    assert not [e for e in events if e.gesture.is_dynamic]


def test_fist_closed_during_a_movement_is_not_activated() -> None:
    """The activation cue is a fist held still before the movement."""

    def pose(t: float):
        return OPEN if t < 0.95 else FIST

    hand = Hand(stroke((640, 400), (640, 300), 0.9, 0.3), pose=pose)
    events, _ = run([hand], 2.0, engine=engine("fist"))
    assert events == []


def test_one_physical_swipe_gives_one_event_and_its_return_is_suppressed_everywhere() -> None:
    """Hybrid: a pointing swipe down, then the hand closes into a fist and comes back up."""
    path = chain(
        (0.0, still(640, 300)),
        (0.8, stroke((640, 300), (640, 450), 0.8, 0.25)),
        (1.6, stroke((640, 450), (640, 300), 1.6, 0.3)),
    )

    def pose(t: float):
        return POINTING if t < 1.2 else FIST

    events, _ = run([Hand(path, pose=pose)], 3.0, engine=engine())
    assert kinds(events) == ["INDEX_SWIPE_DOWN"]
    assert events[0].detector == "finger"


def test_frames_carry_the_measured_stroke_for_the_overlay() -> None:
    _, frames = run([Hand(stroke((640, 300), (640, 450), 0.8, 0.3))], 2.0)
    traces = [f.motion for f in frames if f.motion is not None]
    assert traces and traces[0].detector == "finger"
    assert traces[0].gesture is G.INDEX_SWIPE_DOWN
    assert 0.5 <= max(t.travel_palms for t in traces) < 0.8  # shown until it confirms
    assert all(t.required_palms == 0.8 for t in traces)
    _, still_frames = run([Hand(still(640, 400))], 1.5)
    assert all(f.motion is None for f in still_frames)
