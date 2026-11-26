"""A return movement that comes back in parts and overshoots must not trigger the opposite swipe.

Found while replaying the Director's recordings at the HIGH preset during CP 4.5 (Brief 003):
the hand returned in three parts and the last part started near the swipe's starting point and
continued past it. A position-only return rule treated that part as a deliberate opposite swipe
(SWIPE UP after SWIPE DOWN), and the next real swipe was then suppressed as the return of the
false one. The return phase now ends only when the hand is back near the start *and* has paused.
"""

from __future__ import annotations

from interactive_scrolling.config.settings import GestureSettings, SensitivityPreset
from tests.gesture_helpers import Hand, chain, kinds, run, stroke


def test_overshooting_return_in_parts_is_not_an_opposite_swipe() -> None:
    settings = GestureSettings.from_preset(SensitivityPreset.HIGH)
    path = chain(
        (0.0, stroke((640, 350), (640, 520), 0.8, 0.3)),  # swipe down
        # The return, after the cooldown: three parts with very short hesitations; the last
        # part starts back near the swipe's start and continues well past it.
        (1.7, stroke((640, 520), (640, 450), 1.7, 0.15)),
        (1.9, stroke((640, 450), (640, 380), 1.9, 0.15)),
        (2.08, stroke((640, 380), (640, 250), 2.08, 0.2)),
        # The next intended swipe down, after a real pause.
        (3.1, stroke((640, 300), (640, 470), 3.1, 0.3)),
    )
    events, _ = run([Hand(path)], 4.1, settings=settings)
    assert kinds(events) == ["INDEX_SWIPE_DOWN", "INDEX_SWIPE_DOWN"]
