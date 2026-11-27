"""The benchmark tooling scores what it claims (synthetic recordings, no camera)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from interactive_scrolling.config.settings import GestureSettings
from interactive_scrolling.gestures.diagnostics import LandmarkRecorder
from interactive_scrolling.vision.landmarks import TrackingResult
from tests.gesture_helpers import Hand, chain, make_observation, still, stroke

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from evaluate_gestures import Result, evaluate, load


def record(tmp_path: Path, segments: list[tuple[str, Hand, float]]) -> Path:
    recorder = LandmarkRecorder()
    recorder.start()
    t0 = 1.0
    for label, hand, seconds in segments:
        recorder.label(label, seconds)
        for i in range(int(seconds * 30)):
            t = i / 30
            position = hand.position(t)
            obs = () if position is None else (make_observation(hand.pose(t), position),)
            recorder.observe(TrackingResult(i, int((t0 + t) * 1e9), 1280, 720, obs))
        t0 += seconds + 1
    path = tmp_path / "gestures_test.json"
    path.write_text(json.dumps(recorder.stop()), encoding="utf-8")
    return path


def test_intentional_reversal_is_scored_for_both_directions(tmp_path: Path) -> None:
    # up (next), back, a pause near the start, then down (previous)
    path_up = chain(
        (0.0, still(640, 400)),
        (0.8, stroke((640, 400), (640, 300), 0.8, 0.2)),
        (1.3, stroke((640, 300), (640, 400), 1.3, 0.3)),
        (2.4, stroke((640, 400), (640, 500), 2.4, 0.2)),
        (2.9, stroke((640, 500), (640, 400), 2.9, 0.3)),
    )
    path = record(
        tmp_path,
        [
            (
                "calib_up",
                Hand(
                    chain((0.0, still(640, 400)), (0.8, stroke((640, 400), (640, 300), 0.8, 0.2)))
                ),
                2.0,
            ),
            ("eval_up_then_down", Hand(path_up), 4.0),
        ],
    )
    result = Result()
    evaluate(load(path), GestureSettings(), False, False, result, "t", False)
    row = result.rows["intentional reversal (up, then down)"]
    assert (row.expected, row.detected, row.false_triggers) == (4, 2, 0)
    assert not any("calib" in category for category in result.rows)
