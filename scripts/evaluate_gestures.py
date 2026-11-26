"""Replay recorded landmark sessions through the motion analyzer and gesture engine.

For every prompt segment of a recording made with ``scripts/record_gestures.py`` this prints
the confirmed gestures and compares them with the gestures the prompt asked for. Segments whose
label starts with ``neg_`` must produce no gesture (``neg_open_hold`` may produce at most one
STOP, since holding an open hand still is the stop pose). Exit code 1 if any segment fails.

Usage:
    python scripts/evaluate_gestures.py recordings/gestures_*.json [--verbose]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

import numpy as np

from interactive_scrolling.config.settings import GestureSettings, SensitivityPreset
from interactive_scrolling.gestures.engine import GestureEngine
from interactive_scrolling.gestures.types import GestureType
from interactive_scrolling.motion.analyzer import MotionAnalyzer
from interactive_scrolling.vision.landmarks import Handedness, HandObservation, TrackingResult

G = GestureType
EXPECTED: dict[str, Counter] = {
    "swipe_down_x4": Counter({G.FINGER_SWIPE_DOWN: 4}),
    "swipe_up_x4": Counter({G.FINGER_SWIPE_UP: 4}),
    "point_down_x4": Counter({G.FINGER_SWIPE_DOWN: 4}),
    "point_up_x4": Counter({G.FINGER_SWIPE_UP: 4}),
    "sweep_right_x3": Counter({G.HAND_SWIPE_RIGHT: 3}),
    "sweep_left_x3": Counter({G.HAND_SWIPE_LEFT: 3}),
    "pose_thumbs_up": Counter({G.THUMBS_UP: 1}),
    "pose_open_palm": Counter({G.STOP_GESTURE: 1}),
    "pose_stop": Counter({G.STOP_GESTURE: 1}),
    "pose_pointing": Counter(),
    "pose_fist": Counter(),
}
# Segments where the performer may repeat more often than asked: (gesture, minimum, maximum).
RANGES: dict[str, tuple[GestureType, int, int]] = {
    # The prompt asked for 3; recordings show up to 7 separate presentations in 12 s.
    "thumbs_up_x3": (G.THUMBS_UP, 3, 7),
}


def load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["frames"]


def tracking_of(frame: dict) -> TrackingResult:
    hands = tuple(
        HandObservation(
            landmarks=np.asarray(h["lm"], dtype=np.float32),
            handedness=Handedness.from_label(h["handedness"]),
            handedness_score=h["score"],
            world_landmarks=None if h["world"] is None else np.asarray(h["world"], np.float32),
        )
        for h in frame["hands"]
    )
    return TrackingResult(0, frame["t_ns"], frame["w"], frame["h"], hands)


def evaluate(frames: list[dict], settings: GestureSettings, verbose: bool) -> tuple[int, int]:
    analyzer = MotionAnalyzer()
    engine = GestureEngine(settings)
    segments: dict[tuple[int, str], list] = {}
    rejections: dict[tuple[int, str], Counter] = {}
    events_frames: dict[tuple[int, str], list] = {}
    for frame in frames:
        tracking = tracking_of(frame)
        result = engine.update(tracking, analyzer.update(tracking))
        key = (frame["segment"], frame["label"])
        if frame["label"] == "transition":
            key = (frame["segment"], "transition")
        segments.setdefault(key, [])
        events_frames.setdefault(key, []).append(frame)
        rejections.setdefault(key, Counter())
        for event in result.events:
            segments[key].append(event)
        if result.rejection is not None:
            rejections[key][f"{result.rejection.gesture.label}: {result.rejection.reason}"] += 1
    passed = failed = 0
    t0 = frames[0]["t_ns"]
    for (index, label), events in sorted(segments.items()):
        got = Counter(e.gesture for e in events)
        if label != "transition" and len(events_frames[(index, label)]) < 15:
            continue  # carry-over frames of the previous prompt
        if label.startswith("neg_"):
            allowed = Counter({G.STOP_GESTURE: 1}) if label == "neg_open_hold" else Counter()
            ok = all(got[g] <= allowed[g] for g in got)
        elif label in RANGES:
            gesture, low, high = RANGES[label]
            ok = low <= got[gesture] <= high and set(got) <= {gesture}
        elif label in EXPECTED:
            ok = got == EXPECTED[label]
        else:
            ok = True  # transitions between prompts are not scored
        if label != "transition":
            passed += ok
            failed += not ok
        if verbose or not ok or events:
            mark = "ok  " if ok else "FAIL"
            summary = ", ".join(f"{g.label} x{n}" for g, n in got.items()) or "-"
            print(f"{mark} {index:2} {label:15} {summary}")
            for e in events:
                print(
                    f"         {(e.timestamp_ns - t0) / 1e9:6.2f}s {e.gesture.label:16} "
                    f"mag={e.magnitude_palms} peak={e.peak_speed_palms_s} dur={e.duration_s}"
                )
            if verbose or not ok:
                for reason, n in rejections[(index, label)].most_common(4):
                    print(f"         rejected {n}x {reason}")
    return passed, failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("recordings", nargs="+", type=Path)
    parser.add_argument(
        "--preset",
        choices=[p.value for p in SensitivityPreset if p.value != "custom"],
        default="balanced",
    )
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="FIELD=VALUE",
        help="override a GestureSettings field",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    settings = GestureSettings.from_preset(SensitivityPreset(args.preset))
    for item in args.set:
        name, value = item.split("=", 1)
        settings = replace(settings, **{name: float(value)})
    total_pass = total_fail = 0
    for path in args.recordings:
        print(f"== {path}")
        p, f = evaluate(load(path), settings, args.verbose)
        total_pass += p
        total_fail += f
    print(f"segments passed: {total_pass}, failed: {total_fail}")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
