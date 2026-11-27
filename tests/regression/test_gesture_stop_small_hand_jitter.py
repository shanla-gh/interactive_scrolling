"""The stop pose's stillness check failed on small hands far from the camera.

Recording (Brief 004): at arm's length the hand is ~42 px long; one pixel of landmark jitter
reads as about one hand length per second, and version 0.3 cancelled the hold as "hand
moving" at 0.9 hand lengths/s. Stillness is now the net drift over a 0.3 s window.
"""

from __future__ import annotations

from tests.gesture_helpers import OPEN, Hand, kinds, run


def test_small_hand_with_jitter_can_hold_the_stop_pose() -> None:
    """At arm's length a hand is ~45 px long and landmark jitter is a large fraction of it
    (recording: version 0.3 cancelled the hold as "hand moving" at 0.9 palms/s). Stillness is
    now the net drift over a short window, which jitter does not accumulate."""
    import random

    rng = random.Random(4)
    jitter = {round(i / 30, 4): (rng.uniform(-2.5, 2.5), rng.uniform(-2.5, 2.5)) for i in range(90)}

    def position(t: float):
        dx, dy = jitter.get(round(t, 4), (0.0, 0.0))
        return (640 + dx, 400 + dy)

    events, _ = run([Hand(position, pose=lambda t: OPEN, palm_px=45)], 2.8)
    assert kinds(events) == ["STOP_GESTURE"]
