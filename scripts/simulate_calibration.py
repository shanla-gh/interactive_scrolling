"""Run Quick Calibration offline on a recorded session and score the result on another.

The prompts of a ``record_gestures.py`` recording are mapped to calibration prompts (e.g.
``point_up_x4`` -> "move your finger up"); the calibration's measurement and derivation run on
those frames exactly as in the app. The derived settings are then evaluated with
``evaluate_gestures.py`` on the recordings given with ``--test`` (use a *different* session
for a held-out result).

Usage:
    python scripts/simulate_calibration.py CALIBRATION.json --test OTHER.json [OTHER2.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path

from evaluate_gestures import Result, evaluate, load, report, tracking_of
from interactive_scrolling.config.settings import GestureSettings
from interactive_scrolling.gestures.calibration import CalibrationCollector, derive
from interactive_scrolling.gestures.types import GestureType

G = GestureType
PROMPTS = {
    "point_up_x4": G.INDEX_SWIPE_UP,
    "point_down_x4": G.INDEX_SWIPE_DOWN,
    "swipe_up_x4": G.INDEX_SWIPE_UP,
    "swipe_down_x4": G.INDEX_SWIPE_DOWN,
    "index_up_x4": G.INDEX_SWIPE_UP,
    "index_down_x4": G.INDEX_SWIPE_DOWN,
    "index_left_x4": G.INDEX_SWIPE_LEFT,
    "index_right_x4": G.INDEX_SWIPE_RIGHT,
    "half_heart_x3": G.HALF_HEART,
    "pose_stop": G.STOP_GESTURE,
    "pose_open_palm": G.STOP_GESTURE,
    "calib_up": G.INDEX_SWIPE_UP,
    "calib_down": G.INDEX_SWIPE_DOWN,
    "calib_left": G.INDEX_SWIPE_LEFT,
    "calib_right": G.INDEX_SWIPE_RIGHT,
    "calib_half_heart": G.HALF_HEART,
    "calib_stop": G.STOP_GESTURE,
}


def calibrate(frames: list[dict]):  # type: ignore[no-untyped-def]
    collector = CalibrationCollector()
    results = {}
    current = None
    for frame in frames:
        key = (frame["segment"], frame["label"])
        if key != current:
            if current is not None and collector.active:
                result = collector.end()
                gesture = PROMPTS[current[1]]
                if gesture not in results or result.valid_demos > results[gesture].valid_demos:
                    results[gesture] = result
            current = key
            if frame["label"] in PROMPTS:
                collector.begin(PROMPTS[frame["label"]])
        collector.observe(tracking_of(frame, mirror=False))
    if collector.active and current is not None:
        result = collector.end()
        results.setdefault(PROMPTS[current[1]], result)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("calibration", type=Path)
    parser.add_argument("--test", type=Path, nargs="+", required=True)
    args = parser.parse_args()
    results = calibrate(load(args.calibration))
    for gesture, result in results.items():
        demos = ", ".join(f"{s.length_palms:.2f}" for s in result.demos)
        windups = ", ".join(f"{s.length_palms:.2f}" for s in result.windups)
        print(
            f"{gesture.label:12} demos {result.valid_demos}"
            + (f" lengths [{demos}] wind-ups [{windups}]" if gesture.is_dynamic else "")
            + (f" | feedback: {'; '.join(result.feedback())}" if result.feedback() else "")
        )
    derived = derive(results, GestureSettings())
    for note in derived.notes:
        print("  -", note)
    changed = {
        f.name: getattr(derived.settings, f.name)
        for f in fields(GestureSettings)
        if getattr(derived.settings, f.name) != getattr(GestureSettings(), f.name)
    }
    print("derived settings:", {k: getattr(v, "value", v) for k, v in changed.items()})
    result = Result()
    for path in args.test:
        evaluate(load(path), derived.settings, False, False, result, path.stem, False)
    summary = report(result)
    print(json.dumps({"derived": {k: str(v) for k, v in changed.items()}}, indent=None))
    return 0 if summary else 1


if __name__ == "__main__":
    sys.exit(main())
