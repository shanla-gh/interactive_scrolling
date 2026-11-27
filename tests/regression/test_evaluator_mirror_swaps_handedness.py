"""The evaluator's mirrored replay kept the original handedness labels.

Recordings store "Left"/"Right", the swap table used lowercase keys, so a mirrored right hand
stayed labeled right (found in Brief 004 while writing the in-app recorder). Results in AUTO
control-hand mode were unaffected because recognition does not use the label.
"""

from __future__ import annotations

import sys
from pathlib import Path

from interactive_scrolling.vision.landmarks import Handedness

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from evaluate_gestures import tracking_of


def test_mirrored_replay_swaps_the_handedness_label() -> None:
    frame = {
        "t_ns": 1,
        "w": 1280,
        "h": 720,
        "hands": [{"lm": [[0.25, 0.5, 0.0]] * 21, "handedness": "Right", "score": 0.9}],
    }
    assert tracking_of(frame, mirror=False).hands[0].handedness is Handedness.RIGHT
    mirrored = tracking_of(frame, mirror=True).hands[0]
    assert mirrored.handedness is Handedness.LEFT
    assert abs(float(mirrored.landmarks[0, 0]) - 0.75) < 1e-6
