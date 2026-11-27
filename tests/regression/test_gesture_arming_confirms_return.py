"""A hand in continuous motion armed at the end of a stroke and confirmed the return.

Found in Brief 004 by replaying the recorded open-hand sweeps without the pose check: every
sweep came out in the opposite direction (0/12). Version 0.3 armed a newly tracked hand only
after 0.2 s of stillness, which never came during continuous movement; the recognizer armed
when the hand briefly stopped at the end of a stroke and the next movement it saw was the
return. It now arms on one observed rest and follows (and remembers) earlier strokes.
"""

from __future__ import annotations

from interactive_scrolling.config.settings import GestureSettings
from interactive_scrolling.gestures.engine import GestureEngine
from tests.gesture_helpers import Hand, chain, kinds, run, still, stroke


def test_continuous_back_and_forth_after_acquisition_recognizes_the_first_stroke() -> None:
    """Regression (recorded sweeps, Brief 004): version 0.3 armed a new hand only after 0.2 s
    of stillness, so a hand in continuous motion armed at the end of a stroke and then
    confirmed the return - always the opposite direction."""
    path = chain(
        (0.0, still(700, 400)),
        (0.45, stroke((700, 400), (520, 400), 0.45, 0.25)),  # to the user's right
        (0.75, stroke((520, 400), (700, 400), 0.75, 0.35)),  # back
        (1.15, stroke((700, 400), (520, 400), 1.15, 0.25)),
        (1.45, stroke((520, 400), (700, 400), 1.45, 0.35)),
    )
    events, _ = run([Hand(path)], 2.5)
    assert kinds(events)[:1] == ["INDEX_SWIPE_RIGHT"]
    assert "INDEX_SWIPE_LEFT" not in kinds(events)


def test_v03_arming_misses_the_first_stroke_and_confirms_its_return() -> None:
    """The same movement with the version 0.3 strategies, documenting the defect."""
    from interactive_scrolling.gestures.recognizers import V03_OPTIONS

    path = chain(
        (0.0, stroke((700, 400), (690, 400), 0.0, 0.2)),
        (0.2, stroke((690, 400), (520, 400), 0.2, 0.25)),
        (0.45, stroke((520, 400), (700, 400), 0.45, 0.35)),
    )
    events, _ = run([Hand(path)], 1.6, engine=GestureEngine(GestureSettings(), V03_OPTIONS))
    new, _ = run([Hand(path)], 1.6)
    assert "INDEX_SWIPE_RIGHT" not in kinds(events)
    assert "INDEX_SWIPE_LEFT" not in kinds(new)
