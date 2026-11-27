"""Lowering a pointing hand out of the picture was confirmed as a downward swipe.

Recorded in session 1 (Brief 004 benchmark): the wrist was at 0.90 of the image height when the
stroke reached the distance, real downward swipes at 0.62-0.74. A downward stroke in the bottom
15 % of the picture is now confirmed only once the hand stops inside the view (Brief 005).
"""

from __future__ import annotations

from tests.gesture_helpers import Hand, kinds, run, stroke


def test_pointing_hand_lowered_out_of_view_is_not_a_swipe() -> None:
    """Brief 005: lowering a pointing hand out of the picture was read as a downward swipe."""
    base = stroke((640, 520), (640, 760), 0.8, 0.35)

    def position(t: float):
        p = base(t)
        return None if p[1] > 700 else p

    events, _ = run([Hand(position)], 2.0)
    assert events == []


def test_downward_swipe_near_the_bottom_that_stops_in_view_is_confirmed() -> None:
    events, _ = run([Hand(stroke((640, 480), (640, 600), 0.8, 0.25))], 2.0)
    assert kinds(events) == ["INDEX_SWIPE_DOWN"]
