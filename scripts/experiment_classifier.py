"""Brief 004 Strategy D: does a small learned stroke classifier beat the rules?

Every fingertip stroke of the recordings is extracted with the Quick Calibration segmenter
and labeled *intended* when it goes in the prompted direction of a gesture segment, and
*not intended* otherwise (the return of a swipe, the wind-up before it, and every stroke in a
negative segment). A k-nearest-neighbour classifier (standardized features, k=3) is trained
on one recording session and tested on the other (and vice versa); the rule (distance,
speed and pose as used by the recognizer, without its temporal return handling) is scored on
the same strokes.

Limits that matter for the conclusion: the labels are per prompt, not per stroke (a prompt of
"up x4" may contain an unintended extra up stroke); the sample is small and from one person;
an isolated-stroke classifier cannot see context, so it cannot tell an intentional down swipe
from the return after an up swipe - that is the recognizer's temporal logic.

Usage:
    python scripts/experiment_classifier.py recordings/gestures_A.json recordings/gestures_B.json
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

from evaluate_gestures import load, tracking_of
from interactive_scrolling.config.settings import GestureSettings
from interactive_scrolling.gestures.calibration import _Segmenter
from interactive_scrolling.gestures.pose import PoseLabel, analyze_pose
from interactive_scrolling.gestures.types import GestureType
from interactive_scrolling.motion.analyzer import MotionAnalyzer

G = GestureType
TARGET = {
    "swipe_down_x4": G.INDEX_SWIPE_DOWN,
    "swipe_up_x4": G.INDEX_SWIPE_UP,
    "point_down_x4": G.INDEX_SWIPE_DOWN,
    "point_up_x4": G.INDEX_SWIPE_UP,
    "index_down_x4": G.INDEX_SWIPE_DOWN,
    "index_up_x4": G.INDEX_SWIPE_UP,
    "index_left_x4": G.INDEX_SWIPE_LEFT,
    "index_right_x4": G.INDEX_SWIPE_RIGHT,
    "eval_up_x5": G.INDEX_SWIPE_UP,
    "eval_down_x5": G.INDEX_SWIPE_DOWN,
    "eval_left_x5": G.INDEX_SWIPE_LEFT,
    "eval_right_x5": G.INDEX_SWIPE_RIGHT,
}


def strokes(path: Path) -> list[tuple[np.ndarray, int, bool]]:
    """(features, direction index, intended) per stroke."""
    out = []
    analyzer = MotionAnalyzer()
    segmenter = _Segmenter()
    current = None
    frames = load(path)

    def flush(label: str | None) -> None:
        for s in segmenter.strokes:
            if s.length_palms < 0.3:
                continue
            intended = label in TARGET and s.direction is TARGET[label] and not s.diagonal
            features = np.array(
                [
                    s.length_palms,
                    s.peak_palms_s,
                    s.duration_s,
                    float(s.pointing_before),
                    float(s.pointing_after),
                    float(s.diagonal),
                ]
            )
            out.append((features, list(G).index(s.direction), intended, label))

    for frame in frames:
        key = (frame["segment"], frame["label"])
        if key != current:
            if current is not None:
                flush(current[1])
            segmenter = _Segmenter()
            current = key
        tracking = tracking_of(frame, mirror=False)
        motion = analyzer.update(tracking)
        if len(motion.hands) != 1:
            continue
        hand = motion.hands[0]
        pose = analyze_pose(tracking.hands[hand.observation_index], tracking.image_width, 720)
        segmenter.add(
            tracking.timestamp_ns,
            hand.fingertip.position_px,
            hand.fingertip.velocity_px_s,
            pose.scale_px,
            pose.label is PoseLabel.POINTING,
        )
    if current is not None:
        flush(current[1])
    return out


def rule(features: np.ndarray, settings: GestureSettings) -> bool:
    length, peak, duration, before, after, diagonal = features
    return (
        length >= settings.swipe_min_distance_palms
        and peak >= settings.swipe_min_speed_palms_s
        and not diagonal
        and (before or after)
    )


def knn(train: list, test: list, k: int = 3) -> list[bool]:
    x = np.array([t[0] for t in train])
    mean, std = x.mean(0), x.std(0) + 1e-9
    xs = (x - mean) / std
    labels = np.array([t[2] for t in train])
    predictions = []
    for features, *_ in test:
        d = np.linalg.norm(xs - (features - mean) / std, axis=1)
        nearest = labels[np.argsort(d)[:k]]
        predictions.append(bool(nearest.sum() * 2 > k))
    return predictions


def score(name: str, truth: list[bool], predicted: list[bool]) -> None:
    tp = int(sum(bool(t and p) for t, p in zip(truth, predicted, strict=True)))
    fp = int(sum(bool((not t) and p) for t, p in zip(truth, predicted, strict=True)))
    fn = int(sum(bool(t and (not p)) for t, p in zip(truth, predicted, strict=True)))
    recall = tp / (tp + fn) if tp + fn else math.nan
    precision = tp / (tp + fp) if tp + fp else math.nan
    print(
        f"  {name:28} intended found {tp}/{tp + fn} (recall {recall:.0%}), "
        f"false {fp} (precision {precision:.0%})"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("a", type=Path)
    parser.add_argument("b", type=Path)
    args = parser.parse_args()
    data = {args.a.stem: strokes(args.a), args.b.stem: strokes(args.b)}
    settings = GestureSettings()
    for test_name, test in data.items():
        train = [s for name, d in data.items() if name != test_name for s in d]
        truth = [s[2] for s in test]
        print(
            f"test on {test_name}: {len(test)} strokes, {sum(truth)} intended; "
            f"trained on {len(train)} strokes, {sum(s[2] for s in train)} intended"
        )
        score("rule (distance/speed/pose)", truth, [rule(s[0], settings) for s in test])
        score("3-nearest-neighbour", truth, knn(train, test))
    return 0


if __name__ == "__main__":
    sys.exit(main())
