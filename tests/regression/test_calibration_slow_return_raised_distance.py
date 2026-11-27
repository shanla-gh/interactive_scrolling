"""Quick Calibration raised the swipe distance when the user paused before returning.

Director's calibration (Brief 004 beta, 2026-11-27 09:51): the vertical distance became 1.34
hand lengths and the speed 2.5 (from 0.8 and 2.0), after which recorded finger flicks went from
8/8 to 0/8 in replay. Cause: a return that started more than 0.6 s after the swipe (a short
hold at the top) and ended just before the next demonstration was classified as a *wind-up*
of that demonstration; a "wind-up" as large as the swipe pushed the distance up to 0.9 x the
smallest demonstration. The speed was also raised from the user's fast demonstrations.
"""

from __future__ import annotations

from interactive_scrolling.config.settings import GestureSettings
from interactive_scrolling.gestures.calibration import CalibrationCollector, derive
from interactive_scrolling.gestures.types import GestureType
from interactive_scrolling.vision.landmarks import TrackingResult
from tests.gesture_helpers import Hand, chain, make_observation, still, stroke

G = GestureType


def _measure(gesture: GestureType, hand: Hand, seconds: float):
    collector = CalibrationCollector()
    collector.begin(gesture)
    for i in range(int(seconds * 30)):
        t = i / 30
        position = hand.position(t)
        obs = () if position is None else (make_observation(hand.pose(t), position),)
        collector.observe(TrackingResult(i, int(1e9 + t * 1e9), 1280, 720, obs))
    return collector.end()


def _held_swipes(dy: float) -> Hand:
    """Three quick 1.5-hand-length swipes, each held 0.8 s, then a slow return that ends
    0.3 s before the next swipe."""
    x, y = 640.0, 400.0
    end = (x, y + dy * 150)
    segments = [(0.0, still(x, y))]
    for k in range(3):
        t = 0.8 + 2.0 * k
        segments.append((t, stroke((x, y), end, t, 0.2)))
        segments.append((t + 1.0, stroke(end, (x, y), t + 1.0, 0.7)))
    return Hand(chain(*segments))


def test_slow_returns_do_not_raise_the_distance_or_the_speed() -> None:
    up = _measure(G.INDEX_SWIPE_UP, _held_swipes(-1), 7.0)
    down = _measure(G.INDEX_SWIPE_DOWN, _held_swipes(1), 7.0)
    assert up.valid_demos == 3 and down.valid_demos == 3
    assert up.windups == [] and down.windups == []
    derived = derive({G.INDEX_SWIPE_UP: up, G.INDEX_SWIPE_DOWN: down}, GestureSettings())
    assert derived.settings.swipe_min_distance_palms <= GestureSettings().swipe_min_distance_palms
    assert derived.settings.swipe_min_speed_palms_s <= GestureSettings().swipe_min_speed_palms_s
