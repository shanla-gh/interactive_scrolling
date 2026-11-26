"""Replay recorded landmark sessions through the motion analyzer and gesture engine.

Recordings are made with ``scripts/record_gestures.py`` (landmark numbers only). Every prompt
segment has a label; this script replays all frames, collects the confirmed gestures per
segment and scores them against the segment's expectation:

* positive segments expect an exact number of one gesture (recall = detected / expected,
  where at most the expected number counts as detected);
* every other confirmed gesture in a positive segment is a *false trigger* (for example the
  opposite swipe caused by a return movement);
* negative segments (rest, natural movement, typing, face touching, poses that are not the
  gesture, superseded gestures of version 0.2) expect nothing: every event is a false trigger.

``--mirror`` replays the recordings flipped horizontally with swapped handedness labels. A
mirrored right hand is geometrically a left hand, so this checks the either-hand behaviour on
real motion data (it is a simulation, not a recording of a left hand); horizontal expectations
are swapped accordingly.

``--any-pose`` is a diagnostic: the swipe recognizer accepts any hand pose, so the open-hand
sweeps of version 0.2 can be used to check direction discrimination and return-movement
handling on real horizontal motion. It is not a measurement of the index-swipe gesture.

Usage:
    python scripts/evaluate_gestures.py recordings/gestures_*.json [--mirror] [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from interactive_scrolling.config.settings import GestureSettings, SensitivityPreset
from interactive_scrolling.gestures.engine import GestureEngine
from interactive_scrolling.gestures.types import GestureType
from interactive_scrolling.motion.analyzer import MotionAnalyzer
from interactive_scrolling.vision.landmarks import Handedness, HandObservation, TrackingResult

G = GestureType


@dataclass(frozen=True)
class Expectation:
    category: str
    """Row of the report this segment belongs to."""
    gesture: GestureType | None = None
    count: int = 0
    low: int | None = None
    """For segments where the performer may repeat: accepted range [low, count]."""
    allowed: frozenset[GestureType] = frozenset()
    """Gestures that do not count as false triggers in this segment."""


# Labels of record_gestures.py sessions 1-3. Version 0.2 gestures that Brief 003 replaced are
# negatives now: they must not trigger the new gestures.
EXPECTATIONS: dict[str, Expectation] = {
    # session 1: fingertip swipes performed mostly as finger-led movements (strategy 1)
    "swipe_down_x4": Expectation("finger-led swipe down (session 1)", G.INDEX_SWIPE_DOWN, 4),
    "swipe_up_x4": Expectation("finger-led swipe up (session 1)", G.INDEX_SWIPE_UP, 4),
    # session 2: pointing hand moving (strategy 2)
    "point_down_x4": Expectation("index swipe down", G.INDEX_SWIPE_DOWN, 4),
    "point_up_x4": Expectation("index swipe up", G.INDEX_SWIPE_UP, 4),
    # session 3 (Brief 003 recorder prompts)
    "index_down_x4": Expectation("index swipe down", G.INDEX_SWIPE_DOWN, 4),
    "index_up_x4": Expectation("index swipe up", G.INDEX_SWIPE_UP, 4),
    "index_right_x4": Expectation("index swipe right", G.INDEX_SWIPE_RIGHT, 4),
    "index_left_x4": Expectation("index swipe left", G.INDEX_SWIPE_LEFT, 4),
    "index_next_prev": Expectation(
        "down then up (next, previous)",
        G.INDEX_SWIPE_DOWN,
        2,
        allowed=frozenset({G.INDEX_SWIPE_UP}),
    ),
    "half_heart_x3": Expectation("half-heart", G.HALF_HEART, 3),
    "half_heart_other_hand_x3": Expectation("half-heart (other hand)", G.HALF_HEART, 3),
    "half_heart_hold": Expectation("half-heart held 3 s (one event)", G.HALF_HEART, 1),
    "pose_open_palm": Expectation("stop pose", G.STOP_GESTURE, 1),
    "pose_stop": Expectation("stop pose", G.STOP_GESTURE, 1),
    # negatives
    "pose_pointing": Expectation("negative: pointing held"),
    "pose_fist": Expectation("negative: fist"),
    "pose_thumbs_up": Expectation("negative: thumbs up (v0.2 like)"),
    "thumbs_up_x3": Expectation("negative: thumbs up (v0.2 like)"),
    "sweep_right_x3": Expectation("negative: open-hand sweep (v0.2)"),
    "sweep_left_x3": Expectation("negative: open-hand sweep (v0.2)"),
    "neg_pinch": Expectation("negative: pinch"),
    "neg_c_shape": Expectation("negative: C-shaped hand"),
    "neg_diagonal": Expectation("negative: diagonal pointing movements"),
    "neg_open_hold": Expectation("negative: open hand held", allowed=frozenset({G.STOP_GESTURE})),
}
NEGATIVE_PREFIX = "neg_"
MIN_SEGMENT_FRAMES = 15
"""Shorter labeled runs are carry-over frames of the previous prompt."""

_MIRRORED = {
    G.INDEX_SWIPE_LEFT: G.INDEX_SWIPE_RIGHT,
    G.INDEX_SWIPE_RIGHT: G.INDEX_SWIPE_LEFT,
}


def expectation_for(label: str, mirrored: bool) -> Expectation | None:
    if label in EXPECTATIONS:
        e = EXPECTATIONS[label]
    elif label.startswith(NEGATIVE_PREFIX):
        e = Expectation(f"negative: {label[len(NEGATIVE_PREFIX) :].replace('_', ' ')}")
    else:
        return None
    if mirrored and e.gesture in _MIRRORED:
        e = replace(
            e,
            gesture=_MIRRORED[e.gesture],
            allowed=frozenset(_MIRRORED.get(g, g) for g in e.allowed),
        )
    if mirrored and e.category.startswith("index swipe ") and e.gesture is not None:
        e = replace(e, category=f"index swipe {e.gesture.value.rsplit('_', 1)[1]}")
    return e


def load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["frames"]


_SWAP = {"left": "right", "right": "left"}


def tracking_of(frame: dict, mirror: bool) -> TrackingResult:
    hands = []
    for h in frame["hands"]:
        landmarks = np.asarray(h["lm"], dtype=np.float32)
        label = h["handedness"]
        if mirror:
            landmarks = landmarks.copy()
            landmarks[:, 0] = 1.0 - landmarks[:, 0]
            label = _SWAP.get(label, label)
        hands.append(
            HandObservation(
                landmarks=landmarks,
                handedness=Handedness.from_label(label),
                handedness_score=h["score"],
            )
        )
    return TrackingResult(0, frame["t_ns"], frame["w"], frame["h"], tuple(hands))


@dataclass
class Row:
    segments: int = 0
    expected: int = 0
    detected: int = 0
    false_triggers: int = 0
    failing_segments: list[str] = field(default_factory=list)


@dataclass
class Result:
    rows: dict[str, Row] = field(default_factory=lambda: defaultdict(Row))
    swipe_events: list[dict] = field(default_factory=list)
    returns_suppressed: int = 0
    negative_seconds: float = 0.0


def evaluate(
    frames: list[dict],
    settings: GestureSettings,
    mirror: bool,
    any_pose: bool,
    result: Result,
    name: str,
    verbose: bool,
) -> None:
    analyzer = MotionAnalyzer()
    engine = GestureEngine(settings)
    if any_pose:
        engine.swipes.pose_ok = lambda pose: True
    segments: dict[tuple[int, str], list] = defaultdict(list)
    sizes: Counter = Counter()
    times: dict[tuple[int, str], list[int]] = defaultdict(list)
    for frame in frames:
        tracking = tracking_of(frame, mirror)
        out = engine.update(tracking, analyzer.update(tracking))
        key = (frame["segment"], frame["label"])
        sizes[key] += 1
        times[key].append(frame["t_ns"])
        segments[key].extend(out.events)
        if out.rejection is not None and out.rejection.reason.startswith("return movement"):
            result.returns_suppressed += 1
    t0 = frames[0]["t_ns"]
    for (index, label), events in sorted(segments.items()):
        if label == "transition" or sizes[(index, label)] < MIN_SEGMENT_FRAMES:
            continue
        expectation = expectation_for(label, mirror)
        if expectation is None:
            continue
        got = Counter(e.gesture for e in events)
        row = result.rows[expectation.category]
        row.segments += 1
        if expectation.gesture is None:
            seconds = (times[(index, label)][-1] - times[(index, label)][0]) / 1e9
            result.negative_seconds += seconds
            false = sum(n for g, n in got.items() if g not in expectation.allowed)
            allowed_extra = sum(n for g, n in got.items() if g in expectation.allowed)
            false += max(0, allowed_extra - 1)  # e.g. at most one STOP for an open-hand hold
            ok = false == 0
        else:
            row.expected += expectation.count
            hits = got[expectation.gesture]
            row.detected += min(hits, expectation.count)
            false = max(0, hits - expectation.count) + sum(
                n
                for g, n in got.items()
                if g is not expectation.gesture and g not in expectation.allowed
            )
            ok = hits == expectation.count and false == 0
        row.false_triggers += false
        if not ok:
            row.failing_segments.append(f"{name}#{index}")
        for e in events:
            if e.gesture.is_dynamic:
                result.swipe_events.append(
                    {
                        "segment": label,
                        "gesture": e.gesture.value,
                        "fingertip_palms": e.magnitude_palms,
                        "palm_palms": e.palm_magnitude_palms,
                        "peak_palms_s": e.peak_speed_palms_s,
                        "duration_s": e.duration_s,
                        "hand": e.handedness.value,
                    }
                )
        if verbose or not ok:
            mark = "ok  " if ok else "FAIL"
            summary = ", ".join(f"{g.label} x{n}" for g, n in got.items()) or "-"
            print(f"{mark} {name}#{index:2} {label:24} {summary}")
            if verbose:
                for e in events:
                    print(
                        f"         {(e.timestamp_ns - t0) / 1e9:6.2f}s {e.gesture.label:12} "
                        f"tip={e.magnitude_palms} palm={e.palm_magnitude_palms} "
                        f"peak={e.peak_speed_palms_s} dur={e.duration_s}"
                    )


def report(result: Result) -> dict:
    print()
    print(f"{'category':44} {'segs':>4} {'expected':>8} {'detected':>8} {'recall':>7} {'false':>5}")
    out_rows = {}
    for category in sorted(result.rows, key=lambda c: (c.startswith("negative"), c)):
        row = result.rows[category]
        recall = f"{row.detected / row.expected:.0%}" if row.expected else "-"
        print(
            f"{category:44} {row.segments:4} {row.expected or '-':>8} "
            f"{row.detected if row.expected else '-':>8} {recall:>7} {row.false_triggers:5}"
        )
        out_rows[category] = {
            "segments": row.segments,
            "expected": row.expected,
            "detected": row.detected,
            "false_triggers": row.false_triggers,
            "failing_segments": row.failing_segments,
        }
    swipes = result.swipe_events
    print(f"\nreturn movements suppressed: {result.returns_suppressed}")
    print(f"negative material replayed: {result.negative_seconds:.0f} s")
    if swipes:
        ratios = [s["palm_palms"] / s["fingertip_palms"] for s in swipes if s["fingertip_palms"]]
        print(
            "confirmed swipes: palm displacement / fingertip displacement "
            f"median {np.median(ratios):.2f} (min {min(ratios):.2f}, max {max(ratios):.2f}, "
            f"n={len(ratios)})"
        )
    return {
        "rows": out_rows,
        "returns_suppressed": result.returns_suppressed,
        "negative_seconds": round(result.negative_seconds, 1),
        "swipes": swipes,
    }


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
    parser.add_argument(
        "--mirror", action="store_true", help="replay flipped (simulated other hand)"
    )
    parser.add_argument("--any-pose", action="store_true", help="diagnostic: ignore the hand pose")
    parser.add_argument("--json", type=Path, help="write the summary to this file")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    settings = GestureSettings.from_preset(SensitivityPreset(args.preset))
    for item in args.set:
        name, value = item.split("=", 1)
        settings = replace(settings, **{name: float(value)})
    result = Result()
    for path in args.recordings:
        evaluate(load(path), settings, args.mirror, args.any_pose, result, path.stem, args.verbose)
    summary = report(result)
    summary["settings"] = {"preset": args.preset, "overrides": args.set, "mirror": args.mirror}
    if args.json:
        args.json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    failed = any(r["failing_segments"] for r in summary["rows"].values())
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
