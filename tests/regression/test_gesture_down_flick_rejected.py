"""Downward finger flicks were rejected because the curling finger reads as a fist.

Director test (Nov 2026): one vertical direction was easy, the other nearly impossible. In
the recordings every downward fingertip flick curls the index finger and the hand is
classified as a fist in 10-12 of ~12 frames, so "pointing throughout the stroke" rejected
3 of 4 downward flicks (an upward flick ends with the finger extended and passed). A flick
from a held pointing pose is now confirmed when the finger recovers.
"""

from __future__ import annotations

from tests.gesture_helpers import FIST, POINTING, Hand, index_curl, kinds, run, still


def _flick_pose(t_start: float, curl_s: float = 0.12, hold_s: float = 0.25, back_s: float = 0.15):
    """Pointing, a quick index curl (fingertip moves down), a short pause, re-extension."""

    def pose(t: float):
        if t < t_start:
            return POINTING
        u = t - t_start
        if u < curl_s:
            return index_curl(u / curl_s)
        if u < curl_s + hold_s:
            return FIST
        if u < curl_s + hold_s + back_s:
            return index_curl(1.0 - (u - curl_s - hold_s) / back_s)
        return POINTING

    return pose


def test_downward_finger_flick_that_recovers_is_a_swipe_down() -> None:
    """Director test, Nov 2026: downward swipes were nearly impossible. A downward fingertip
    flick curls the index finger (the hand reads as a fist), which version 0.3 rejected; it is
    now confirmed once the finger recovers, after a measured decision delay."""
    events, _ = run([Hand(still(640, 400), pose=_flick_pose(1.0), palm_px=140)], 2.5)
    assert kinds(events) == ["INDEX_SWIPE_DOWN"]
    assert events[0].decision_delay_s > 0.0
