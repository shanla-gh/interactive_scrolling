"""Brief 006 benchmark: one configuration, every evaluation set, separate dev / held-out rows.

For every labeled segment the replay counts, per expected direction:

* ``correct``   - events in the prompted direction (at most the prompted count),
* ``wrong``     - events in the *opposite* direction (the costly error: next instead of back),
* ``extra``     - more events in the prompted direction than prompted (duplicates),
* ``other``     - events in a perpendicular direction or static gestures,

and the false events in negative segments (ordinary activity). Recordings are split into
*development* data (used to look at failures and tune) and *held-out* data (``--holdout``
glob; scored, never inspected per event while tuning). Semi-synthetic sets (``--synthetic-
fist``, ``--synthetic-horizontal``) are reported separately and never count as physical
evidence. Calibration segments (``calib_*``) are not scored.

Usage:
    python scripts/benchmark_motion.py recordings/gestures_*.json --holdout "*s5_left*"
    python scripts/benchmark_motion.py ... --set control_style=finger --option ghost_hands=false
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path

from evaluate_gestures import (
    MIN_SEGMENT_FRAMES,
    expectation_for,
    fist_segments,
    load,
    rotate_vertical_segments,
    tracking_of,
)
from interactive_scrolling.config.settings import GestureSettings
from interactive_scrolling.gestures.engine import GestureEngine
from interactive_scrolling.gestures.recognizers import OPPOSITE, RecognizerOptions
from interactive_scrolling.gestures.types import GestureType
from interactive_scrolling.motion.analyzer import MotionAnalyzer

G = GestureType
SHORT = {
    G.INDEX_SWIPE_UP: "up",
    G.INDEX_SWIPE_DOWN: "down",
    G.INDEX_SWIPE_LEFT: "left",
    G.INDEX_SWIPE_RIGHT: "right",
    G.HALF_HEART: "heart",
    G.STOP_GESTURE: "stop",
}


@dataclass
class Cell:
    expected: int = 0
    correct: int = 0
    wrong: int = 0
    extra: int = 0
    other: int = 0
    segments: int = 0

    def add(self, other: Cell) -> None:
        for name in ("expected", "correct", "wrong", "extra", "other", "segments"):
            setattr(self, name, getattr(self, name) + getattr(other, name))


@dataclass
class Table:
    rows: dict[str, Cell] = field(default_factory=lambda: defaultdict(Cell))
    negative_events: Counter = field(default_factory=Counter)
    negative_seconds: float = 0.0
    failing: list[str] = field(default_factory=list)
    ghost_frames: int = 0
    confirm_s: list[float] = field(default_factory=list)
    """Stroke start to confirmation of every swipe in a positive segment (seconds)."""


def kind_of(label: str) -> str:
    if "fist" in label:
        return "fist"
    if label.startswith("synthetic_") and "fist" not in label:
        return "rotated"
    if "sweep" in label:
        return "open hand"
    return "finger"


def score(
    frames: list[dict],
    settings: GestureSettings,
    options: RecognizerOptions,
    table: Table,
    name: str,
    mirror: bool = False,
    sweeps: bool = True,
) -> None:
    analyzer = MotionAnalyzer()
    engine = GestureEngine(settings, options)
    events: dict[tuple[int, str], list] = defaultdict(list)
    sizes: Counter = Counter()
    times: dict[tuple[int, str], list[int]] = defaultdict(list)
    for frame in frames:
        tracking = tracking_of(frame, mirror)
        out = engine.update(tracking, analyzer.update(tracking))
        key = (frame["segment"], frame["label"])
        sizes[key] += 1
        times[key].append(frame["t_ns"])
        events[key].extend(out.events)
    table.ghost_frames += engine.ghost_frames
    for (index, label), evs in sorted(events.items()):
        if (
            label == "transition"
            or label.startswith("calib_")
            or sizes[(index, label)] < MIN_SEGMENT_FRAMES
        ):
            continue
        e = expectation_for(label, mirror, any_pose=sweeps)
        if e is None:
            continue
        got = Counter(ev.gesture for ev in evs)
        if e.gesture is None:
            seconds = (times[(index, label)][-1] - times[(index, label)][0]) / 1e9
            table.negative_seconds += seconds
            for g, n in got.items():
                if g in e.allowed:
                    n = max(0, n - 1)
                if n:
                    table.negative_events[f"{label}:{SHORT.get(g, g.value)}"] += n
            continue
        wanted = {e.gesture: e.count, **dict(e.also)}
        table.confirm_s.extend(
            ev.duration_s + ev.decision_delay_s for ev in evs if ev.gesture in wanted
        )
        for g, n in wanted.items():
            cell = Cell(expected=n, segments=1)
            cell.correct = min(got[g], n)
            cell.extra = max(0, got[g] - n)
            if g in OPPOSITE and OPPOSITE[g] not in wanted:
                cell.wrong = got[OPPOSITE[g]]
            row = f"{kind_of(label)} {SHORT[g]}"
            if len(wanted) > 1:
                row = f"{kind_of(label)} reversal {SHORT[g]}"
            table.rows[row].add(cell)
        others = sum(
            n
            for g, n in got.items()
            if g not in wanted
            and not (g in OPPOSITE and OPPOSITE[g] in wanted and len(wanted) == 1)
            and g not in e.allowed
        )
        first = next(iter(wanted))
        table.rows[
            f"{kind_of(label)} {SHORT[first]}"
            if len(wanted) == 1
            else f"{kind_of(label)} reversal {SHORT[first]}"
        ].other += others
        ok = (
            all(got[g] == n for g, n in wanted.items())
            and others == 0
            and not any(
                got[OPPOSITE[g]] for g in wanted if g in OPPOSITE and OPPOSITE[g] not in wanted
            )
        )
        if not ok:
            table.failing.append(
                f"{name}#{index} {label}: "
                + ", ".join(f"{SHORT.get(g, g.value)} x{n}" for g, n in got.items())
                or "-"
            )


def degrade(frames: list[dict], how: str, seed: int = 6) -> list[dict]:
    """Synthetic degradations of a real recording (engineering checks, not physical evidence):
    ``fps15`` / ``fps20`` keep every 2nd / 2 of 3 frames, ``drop10`` loses 10 % of the frames at
    random, ``jitter`` adds +-8 ms of timestamp noise (the measured delivery jitter is 5 ms sd),
    ``blur`` removes the hand from 15 % of the frames of fast movement (landmark dropouts),
    ``periodic`` replaces the bursty arrival times with periodic sample times (driver clock)."""
    import random

    rng = random.Random(seed)
    if how == "fps15":
        return frames[::2]
    if how == "fps20":
        return [f for i, f in enumerate(frames) if i % 3 != 2]
    if how == "drop10":
        return [f for f in frames if rng.random() >= 0.1]
    if how == "jitter":
        out, last = [], 0
        for f in frames:
            t = f["t_ns"] + int(rng.uniform(-8e6, 8e6))
            t = max(t, last + 1_000_000)
            last = t
            out.append({**f, "t_ns": t})
        return out
    if how == "periodic":
        # Brief 009: approximate the driver's exactly periodic sample times - each frame moved
        # to the nearest multiple of the median interval (strictly increasing).
        import itertools
        import statistics

        times = [f["t_ns"] for f in frames]
        period = statistics.median(b - a for a, b in itertools.pairwise(times))
        out, last = [], None
        for f in frames:
            slot = times[0] + round((f["t_ns"] - times[0]) / period) * period
            if last is not None and slot <= last:
                slot = last + period
            last = slot
            out.append({**f, "t_ns": int(slot)})
        return out
    if how == "blur":
        import numpy as np

        out, prev = [], None
        for f in frames:
            fast = False
            if f["hands"] and prev is not None and prev["hands"]:
                a = np.asarray(f["hands"][0]["lm"])[0, :2]
                b = np.asarray(prev["hands"][0]["lm"])[0, :2]
                fast = float(np.hypot(*(a - b))) > 0.012
            prev = f
            out.append({**f, "hands": []} if fast and rng.random() < 0.15 else f)
        return out
    raise ValueError(how)


def show(title: str, table: Table) -> dict:
    print(f"== {title}")
    out: dict = {"rows": {}, "negatives": {}}
    for row, c in sorted(table.rows.items()):
        recall = f"{100 * c.correct / c.expected:3.0f}%" if c.expected else "  - "
        print(
            f"   {row:22} {c.correct:3}/{c.expected:<3} {recall}  wrong-dir {c.wrong:2}  "
            f"extra {c.extra:2}  other {c.other:2}"
        )
        out["rows"][row] = c.__dict__
    total = sum(table.negative_events.values())
    minutes = table.negative_seconds / 60
    print(
        f"   negatives: {total} false events in {table.negative_seconds:.0f} s"
        f" ({total / minutes:.1f}/min)"
        if minutes
        else "   negatives: none"
    )
    if table.negative_events:
        print("     " + ", ".join(f"{k} x{v}" for k, v in sorted(table.negative_events.items())))
    print(f"   duplicate hand detections ignored: {table.ghost_frames} frames")
    if table.confirm_s:
        values = sorted(table.confirm_s)
        median = values[len(values) // 2]
        p95 = values[min(len(values) - 1, int(0.95 * len(values)))]
        print(f"   stroke start to confirmation: median {median:.3f} s, p95 {p95:.3f} s")
        out["confirm_s"] = {"median": round(median, 3), "p95": round(p95, 3)}
    out["negatives"] = dict(table.negative_events)
    out["negative_seconds"] = round(table.negative_seconds, 1)
    out["failing"] = table.failing
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("recordings", nargs="+", type=Path)
    parser.add_argument(
        "--holdout", action="append", default=[], help="glob of held-out recordings"
    )
    parser.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE")
    parser.add_argument("--option", action="append", default=[], metavar="FIELD=VALUE")
    parser.add_argument(
        "--synthetic", action="store_true", help="also score the semi-synthetic sets"
    )
    parser.add_argument("--mirror", action="store_true", help="also score mirrored dev recordings")
    parser.add_argument("--failing", action="store_true", help="list failing dev segments")
    parser.add_argument(
        "--sweeps-negative",
        action="store_true",
        help="score the v0.2 open-hand sweeps as negatives (Brief 005) instead of as horizontal "
        "swipes (Brief 006: the hand shape does not matter)",
    )
    parser.add_argument(
        "--degrade",
        choices=["fps15", "fps20", "drop10", "jitter", "blur", "periodic"],
        help="score SYNTHETIC degradations of the development recordings",
    )
    parser.add_argument("--json", type=Path)
    parser.add_argument(
        "--baseline",
        type=Path,
        help="regression gate: compare the development rows with a saved --json result and "
        "exit 1 if a direction loses correct swipes or gains wrong-direction, extra or "
        "ordinary-activity events",
    )
    args = parser.parse_args()

    settings = GestureSettings()
    for item in args.set:
        name, value = item.split("=", 1)
        current = getattr(settings, name)
        typed: object = value
        if isinstance(current, bool):
            typed = value == "true"
        elif isinstance(current, float):
            typed = float(value)
        settings = replace(settings, **{name: typed})
    options = RecognizerOptions()
    for item in args.option:
        name, value = item.split("=", 1)
        current = getattr(options, name)
        typed = value
        if isinstance(current, bool):
            typed = value == "true"
        elif isinstance(current, float):
            typed = float(value)
        options = replace(options, **{name: typed})

    dev, holdout, synthetic, mirrored = Table(), Table(), Table(), Table()
    for path in args.recordings:
        frames = load(path)
        held = any(fnmatch.fnmatch(path.name, pattern) for pattern in args.holdout)
        if args.degrade:
            frames = degrade(frames, args.degrade)
        score(
            frames,
            settings,
            options,
            holdout if held else dev,
            path.stem,
            sweeps=not args.sweeps_negative,
        )
        if args.synthetic and not held:
            score(fist_segments(frames), settings, options, synthetic, path.stem + "+fist")
            score(
                rotate_vertical_segments(frames), settings, options, synthetic, path.stem + "+rot"
            )
        if args.mirror and not held:
            score(frames, settings, options, mirrored, path.stem + "+mirror", mirror=True)
    result = {"development (real)": show("development (real recordings)", dev)}
    if args.failing:
        for line in dev.failing:
            print("     FAIL", line)
    if args.mirror:
        result["mirrored"] = show("development mirrored (simulated other hand)", mirrored)
    if args.synthetic:
        result["semi-synthetic"] = show("SEMI-SYNTHETIC (development material re-posed)", synthetic)
    if args.holdout:
        result["held-out (real)"] = show("HELD-OUT (real recordings, not used for tuning)", holdout)
    if args.json:
        args.json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if args.baseline:
        return gate(json.loads(args.baseline.read_text(encoding="utf-8")), result)
    return 0


def gate(baseline: dict, result: dict) -> int:
    """Per-row comparison with a saved result; 1 = regression."""
    key = "development (real)"
    old, new = baseline[key], result[key]
    worse = []
    print(f"== regression gate against the baseline ({key})")
    for row in sorted(set(old["rows"]) | set(new["rows"])):
        a = old["rows"].get(row, {})
        b = new["rows"].get(row, {})
        deltas = {k: b.get(k, 0) - a.get(k, 0) for k in ("correct", "wrong", "extra", "other")}
        if any(deltas.values()):
            print(f"   {row:22} " + "  ".join(f"{k} {v:+d}" for k, v in deltas.items() if v))
        if deltas["correct"] < 0 or deltas["wrong"] > 0 or deltas["extra"] > 0:
            worse.append(row)
    neg_old = sum(old["negatives"].values())
    neg_new = sum(new["negatives"].values())
    print(f"   ordinary-activity events {neg_old} -> {neg_new}")
    if neg_new > neg_old:
        worse.append("ordinary activity")
    if "confirm_s" in old and "confirm_s" in new:
        print(
            f"   confirmation median {old['confirm_s']['median']} -> {new['confirm_s']['median']} s"
        )
    print("   RESULT:", "REGRESSION in " + ", ".join(worse) if worse else "no regression")
    return 1 if worse else 0


if __name__ == "__main__":
    sys.exit(main())
