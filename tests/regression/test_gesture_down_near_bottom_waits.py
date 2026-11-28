"""A downward swipe with the hand low in the picture waited for a full stop (Brief 009).

Brief 009 pipeline analysis: downward swipes (previous Short) were confirmed a median 255 ms
(finger) / 432 ms (whole hand) after the stroke reached its distance, while up / left / right
were confirmed at once - the guard against a hand lowered out of view waited for the hand to
stop. At a well-sampled frame rate (>= 22 fps) a clear slow-down from the stroke's peak
(below half of it) now counts as stopping inside the picture; at lower frame rates the
conservative rule stays (it prevented duplicate and reversal errors at 15 fps). Moving the
bottom zone from 0.85 to 0.90 was rejected: it re-opened the Brief 005 false swipe of a hand
lowered out of view (``test_gesture_hand_lowered_out_of_view.py``).
"""

from __future__ import annotations

from interactive_scrolling.config.settings import GestureSettings
from interactive_scrolling.gestures.engine import GestureEngine
from interactive_scrolling.gestures.recognizers import RecognizerOptions
from tests.gesture_helpers import Hand, kinds, run, stroke

LOW_SWIPE = stroke((640, 540), (640, 640), 0.8, 0.25)


def test_low_downward_swipe_is_confirmed_promptly_at_30_fps() -> None:
    events, _ = run([Hand(LOW_SWIPE)], 2.0, fps=30)
    assert kinds(events) == ["INDEX_SWIPE_DOWN"]
    assert events[0].decision_delay_s <= 0.1  # 67 ms (two frames) instead of 200 ms


def test_low_downward_swipe_keeps_the_conservative_wait_at_15_fps() -> None:
    events, _ = run([Hand(LOW_SWIPE)], 2.0, fps=15)
    assert kinds(events) == ["INDEX_SWIPE_DOWN"]
    assert events[0].decision_delay_s >= 0.15


def test_previous_rule_waited_longer_at_30_fps() -> None:
    old = RecognizerOptions(down_stop_fraction=0.0, fast_bottom_zone=0.0, early_min_fps=0.0)
    events, _ = run([Hand(LOW_SWIPE)], 2.0, fps=30, engine=GestureEngine(GestureSettings(), old))
    assert kinds(events) == ["INDEX_SWIPE_DOWN"]
    assert events[0].decision_delay_s >= 0.15


def test_hand_lowered_out_of_view_is_still_not_a_swipe_at_30_fps() -> None:
    base = stroke((640, 520), (640, 760), 0.8, 0.35)

    def position(t: float):  # type: ignore[no-untyped-def]
        p = base(t)
        return None if p[1] > 700 else p

    events, _ = run([Hand(position)], 2.0, fps=30)
    assert events == []
