"""Quick Calibration: measurement of demonstrations, feedback and bounded derivation."""

from __future__ import annotations

from interactive_scrolling.config.settings import GestureSettings, SensitivityPreset
from interactive_scrolling.gestures.calibration import (
    MAX_DISTANCE,
    MIN_DISTANCE,
    CalibrationCollector,
    derive,
)
from interactive_scrolling.gestures.engine import GestureEngine
from interactive_scrolling.gestures.recognizers import swipe_distance
from interactive_scrolling.gestures.types import GestureType
from interactive_scrolling.vision.landmarks import TrackingResult
from tests.gesture_helpers import (
    HALF_HEART,
    OPEN,
    Hand,
    chain,
    make_observation,
    run,
    still,
    stroke,
)

G = GestureType
FPS = 30.0


def measure(gesture: GestureType, hand: Hand, seconds: float):
    collector = CalibrationCollector()
    collector.begin(gesture)
    for i in range(int(seconds * FPS)):
        t = i / FPS
        position = hand.position(t)
        observations = (
            () if position is None else (make_observation(hand.pose(t), position, hand.palm_px),)
        )
        collector.observe(TrackingResult(i, int(1e9 + t * 1e9), 1280, 720, observations))
    return collector.end()


def three_strokes(dx: float, dy: float, size: float = 1.0) -> Hand:
    """Three strokes of ``size`` palm lengths (palm 100 px) with returns, 1.2 s apart."""
    x, y = 640.0, 400.0
    segments = [(0.0, still(x, y))]
    for k in range(3):
        t = 0.8 + 1.2 * k
        end = (x + dx * size * 100, y + dy * size * 100)
        segments.append((t, stroke((x, y), end, t, 0.2)))
        segments.append((t + 0.45, stroke(end, (x, y), t + 0.45, 0.3)))
    return Hand(chain(*segments))


def test_demonstrations_are_measured_and_returns_ignored() -> None:
    result = measure(G.INDEX_SWIPE_UP, three_strokes(0, -1, 0.9), 4.5)
    assert result.valid_demos == 3
    assert all(0.75 <= s.length_palms <= 1.05 for s in result.demos)
    assert result.windups == []
    assert result.feedback() == []


def test_wrong_direction_is_explained() -> None:
    """Only detectable without a return: moving right and back also contains a leftward
    stroke, and the measurement cannot know which part was intended."""
    hand = Hand(stroke((640, 400), (540, 400), 0.8, 0.25))  # image left = the user's right
    result = measure(G.INDEX_SWIPE_LEFT, hand, 2.0)
    assert result.valid_demos == 0
    assert result.feedback() == ["That went to your right - please move to your left."]


def test_too_short_movement_is_explained() -> None:
    result = measure(G.INDEX_SWIPE_UP, three_strokes(0, -1, 0.2), 4.5)
    assert result.valid_demos == 0
    assert result.feedback()[0] in (
        "Movement too short: move a little further.",
        "No movement detected.",
    )


def test_small_hand_gets_the_distance_feedback() -> None:
    hand = three_strokes(0, -1)
    hand.palm_px = 40
    result = measure(G.INDEX_SWIPE_UP, hand, 4.5)
    assert any("closer" in text for text in result.feedback())


def test_small_swipes_lower_the_distance_within_bounds() -> None:
    up = measure(G.INDEX_SWIPE_UP, three_strokes(0, -1, 0.7), 4.5)
    down = measure(G.INDEX_SWIPE_DOWN, three_strokes(0, 1, 0.7), 4.5)
    derived = derive({G.INDEX_SWIPE_UP: up, G.INDEX_SWIPE_DOWN: down}, GestureSettings())
    s = derived.settings
    assert s.preset is SensitivityPreset.PERSONAL
    for direction, result in ((G.INDEX_SWIPE_UP, up), (G.INDEX_SWIPE_DOWN, down)):
        distance = swipe_distance(s, direction)
        assert MIN_DISTANCE <= distance < GestureSettings().swipe_min_distance_palms
        assert distance <= 0.9 * min(d.length_palms for d in result.demos)
    # The calibrated engine recognizes the same small swipes.
    events, _ = run([three_strokes(0, -1, 0.7)], 4.5, engine=GestureEngine(s))
    assert [e.gesture for e in events] == [G.INDEX_SWIPE_UP] * 3


def test_large_swipes_do_not_raise_the_distance() -> None:
    """Calibrating on large swipes must not make later small ones fail (cross-session
    simulation: 0/8 before this rule)."""
    up = measure(G.INDEX_SWIPE_UP, three_strokes(0, -1, 2.5), 4.5)
    down = measure(G.INDEX_SWIPE_DOWN, three_strokes(0, 1, 2.5), 4.5)
    derived = derive({G.INDEX_SWIPE_UP: up, G.INDEX_SWIPE_DOWN: down}, GestureSettings())
    assert derived.settings.swipe_min_distance_palms == GestureSettings().swipe_min_distance_palms
    assert derived.settings.swipe_min_distance_palms <= MAX_DISTANCE


def test_single_demonstration_changes_nothing_for_that_axis() -> None:
    one = measure(G.INDEX_SWIPE_UP, three_strokes(0, -1, 0.6), 1.6)
    derived = derive({G.INDEX_SWIPE_UP: one}, GestureSettings())
    assert derived.settings.swipe_min_distance_palms == GestureSettings().swipe_min_distance_palms
    assert any("not enough" in note for note in derived.notes)


def test_half_heart_template_is_learned_from_held_demonstrations() -> None:
    hand = Hand(still(640, 400), pose=lambda t: HALF_HEART)
    result = measure(G.HALF_HEART, hand, 2.0)
    assert result.valid_demos >= 1
    derived = derive({G.HALF_HEART: result}, GestureSettings())
    assert derived.profile.has_heart
    engine = GestureEngine(derived.settings, profile=derived.profile)
    events, _ = run([hand], 2.0, engine=engine)
    assert [e.gesture for e in events] == [G.HALF_HEART]


def test_open_palm_demonstration_keeps_the_standard_stop_tilt() -> None:
    result = measure(G.STOP_GESTURE, Hand(still(640, 400), pose=lambda t: OPEN), 2.0)
    assert result.valid_demos >= 1
    derived = derive({G.STOP_GESTURE: result}, GestureSettings())
    assert derived.settings.stop_upright_deg == GestureSettings().stop_upright_deg


def test_very_small_swipes_keep_the_safe_minimum_and_say_so() -> None:
    up = measure(G.INDEX_SWIPE_UP, three_strokes(0, -1, 0.45), 4.5)
    down = measure(G.INDEX_SWIPE_DOWN, three_strokes(0, 1, 0.45), 4.5)
    derived = derive({G.INDEX_SWIPE_UP: up, G.INDEX_SWIPE_DOWN: down}, GestureSettings())
    assert swipe_distance(derived.settings, G.INDEX_SWIPE_UP) == MIN_DISTANCE
    assert swipe_distance(derived.settings, G.INDEX_SWIPE_DOWN) == MIN_DISTANCE
    assert any("very small" in note for note in derived.notes)


def test_returns_do_not_raise_the_distance_but_opposite_wind_ups_do() -> None:
    """Brief 005: whole-hand returns are as large as the swipe (suppressed by the recognizer
    anyway) and must not raise the distance; a downward wind-up before the first upward swipe
    moves like a downward swipe and sets the floor for "down"."""
    up = measure(G.INDEX_SWIPE_UP, three_strokes(0, -1, 1.0), 4.5)
    down = measure(G.INDEX_SWIPE_DOWN, three_strokes(0, 1, 0.7), 4.5)
    assert up.returns and up.windups == []
    plain = derive({G.INDEX_SWIPE_UP: up, G.INDEX_SWIPE_DOWN: down}, GestureSettings())
    assert swipe_distance(plain.settings, G.INDEX_SWIPE_DOWN) <= 0.7 * 0.7 + 0.05
    windup = up.returns[0]
    up.windups = [windup]
    floored = derive({G.INDEX_SWIPE_UP: up, G.INDEX_SWIPE_DOWN: down}, GestureSettings())
    expected = min(1.15 * windup.length_palms, 0.9 * min(d.length_palms for d in down.demos))
    assert swipe_distance(floored.settings, G.INDEX_SWIPE_DOWN) >= round(expected, 2) - 0.01


def test_fist_demonstrations_set_the_fist_distance() -> None:
    from tests.gesture_helpers import FIST

    def fist_strokes(dy: float) -> Hand:
        hand = three_strokes(0, dy, 0.6)
        hand.pose = lambda t: FIST
        return hand

    collector_results = {}
    for direction, dy in ((G.INDEX_SWIPE_UP, -1), (G.INDEX_SWIPE_DOWN, 1)):
        c = CalibrationCollector()
        c.begin(direction, detector="fist")
        hand = fist_strokes(dy)
        for i in range(int(4.5 * FPS)):
            t = i / FPS
            obs = (make_observation(hand.pose(t), hand.position(t), hand.palm_px),)
            c.observe(TrackingResult(i, int(1e9 + t * 1e9), 1280, 720, obs))
        collector_results[direction] = c.end()
        assert collector_results[direction].valid_demos == 3
    derived = derive({}, GestureSettings(), fist_results=collector_results)
    assert (
        0.3
        <= derived.settings.fist_swipe_distance_palms
        <= GestureSettings().fist_swipe_distance_palms
    )
