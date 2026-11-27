"""Brief 005 CP 14.4: natural returns, deliberate reversals and repetition (synthetic hands).

A swipe is a 1.5-hand-length stroke in 0.2 s; a natural return comes straight back in 0.3 s.
A deliberate reversal returns, pauses near the start (as the gesture guide asks) and then
swipes the other way."""

from __future__ import annotations

from dataclasses import replace

import pytest

from interactive_scrolling.config.settings import GestureSettings
from interactive_scrolling.gestures.engine import GestureEngine
from tests.gesture_helpers import FIST, POINTING, Hand, chain, kinds, run, still, stroke

X, Y = 640.0, 380.0
UP, DOWN = -150.0, 150.0


def path(*moves: tuple[float, float, float]):
    """moves: (start time, dy, duration); each move starts where the previous one ended."""
    segments = [(0.0, still(X, Y))]
    y = Y
    for t, dy, duration in moves:
        segments.append((t, stroke((X, y), (X, y + dy), t, duration)))
        y += dy
    return chain(*segments)


SCENARIOS = {
    "up, return, up": (
        [(0.8, UP, 0.2), (1.1, -UP, 0.3), (2.4, UP, 0.2), (2.7, -UP, 0.3)],
        ["INDEX_SWIPE_UP", "INDEX_SWIPE_UP"],
    ),
    "down, return, down": (
        [(0.8, DOWN, 0.2), (1.1, -DOWN, 0.3), (2.4, DOWN, 0.2), (2.7, -DOWN, 0.3)],
        ["INDEX_SWIPE_DOWN", "INDEX_SWIPE_DOWN"],
    ),
    "up, return, pause, deliberate down": (
        [(0.8, UP, 0.2), (1.1, -UP, 0.3), (1.9, DOWN, 0.2), (2.2, -DOWN, 0.3)],
        ["INDEX_SWIPE_UP", "INDEX_SWIPE_DOWN"],
    ),
    "down, return, pause, deliberate up": (
        [(0.8, DOWN, 0.2), (1.1, -DOWN, 0.3), (1.9, UP, 0.2), (2.2, -UP, 0.3)],
        ["INDEX_SWIPE_DOWN", "INDEX_SWIPE_UP"],
    ),
    "rapid repeated up (0.9 s apart)": (
        [
            (0.8, UP, 0.15),
            (1.0, -UP, 0.25),
            (1.7, UP, 0.15),
            (1.9, -UP, 0.25),
            (2.6, UP, 0.15),
            (2.8, -UP, 0.25),
        ],
        ["INDEX_SWIPE_UP"] * 3,
    ),
    "slow natural up": (
        [(0.8, UP, 0.45), (1.6, -UP, 0.6)],
        ["INDEX_SWIPE_UP"],
    ),
}


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_finger_scenarios(name: str) -> None:
    moves, expected = SCENARIOS[name]
    events, _ = run([Hand(path(*moves), pose=lambda t: POINTING)], 4.0)
    assert kinds(events) == expected


@pytest.mark.parametrize(
    "name", ["up, return, up", "down, return, down", "down, return, pause, deliberate up"]
)
def test_fist_scenarios(name: str) -> None:
    moves, expected = SCENARIOS[name]
    hand = Hand(path(*[(t, dy * 0.6, d) for t, dy, d in moves]), pose=lambda t: FIST)
    engine = GestureEngine(replace(GestureSettings(), control_style="fist"))
    events, _ = run([hand], 4.0, engine=engine)
    assert kinds(events) == expected
    assert all(e.detector == "fist" for e in events)
