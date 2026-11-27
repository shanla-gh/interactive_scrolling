"""A momentary duplicate detection of the moving hand cancelled the swipe in progress.

Session 5 (Brief 006, the Director's recordings): during fast movements MediaPipe reported the
blurred control hand a second time for 1-4 frames (about ten times per recorded session,
mostly in the middle of a swipe). The engine read two hands "too close together", cancelled
the stroke and required a fresh, settled hand afterwards; in the downward-finger segment this
cancelled intended swipes and the following finger extensions fired as swipes UP. With the
duplicate ignored, development data went from 9/13 downward swipes (3 in the wrong
direction) to 13/13.
"""

from __future__ import annotations

from tests.gesture_helpers import FPS, POINTING, Hand, kinds, run, still, stroke


def _ghost(t_from: float, t_to: float, follow):  # type: ignore[no-untyped-def]
    """A duplicate of the control hand, slightly offset, visible only in [t_from, t_to)."""

    def position(t: float):
        if not t_from <= t < t_to:
            return None
        x, y = follow(t)
        return (x + 25.0, y - 40.0)

    return position


def test_duplicate_detection_during_a_fast_swipe_does_not_cancel_it() -> None:
    path = stroke((640, 300), (640, 420), 1.0, 0.15)
    ghost = _ghost(1.0 + 2 / FPS, 1.0 + 4 / FPS, path)
    events, frames = run([Hand(path), Hand(ghost, lambda t: POINTING)], 2.5)
    assert kinds(events) == ["INDEX_SWIPE_DOWN"]
    assert not any(f.rejection and f.rejection.code == "ambiguous_hand" for f in frames)


def test_a_real_second_hand_close_to_the_control_hand_still_suspends_recognition() -> None:
    """A second hand that stays next to the control hand is not a duplicate."""
    path = stroke((640, 300), (640, 420), 1.6, 0.15)
    other = Hand(still(700, 280))
    events, frames = run([Hand(path), other], 2.5)
    assert events == []
    assert any(f.status.value == "ambiguous" for f in frames)
