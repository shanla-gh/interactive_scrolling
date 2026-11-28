"""Where recognition time goes: stroke duration and decision delay per detector (Brief 009).

Replays recordings through the engine and reports, for every recognized directional gesture,
the stroke duration (motion onset to stroke end) and the decision delay (stroke end to
event), split by detector (finger / hand). Development recordings of one person.

Usage: python scripts/analyze_decision_delay.py recordings/gestures_*.json [--set FIELD=VALUE]
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_gestures import load, tracking_of
from interactive_scrolling.config.settings import GestureSettings
from interactive_scrolling.gestures.engine import GestureEngine
from interactive_scrolling.motion.analyzer import MotionAnalyzer


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("recordings", nargs="+", type=Path)
    parser.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE")
    parser.add_argument("--option", action="append", default=[], metavar="FIELD=VALUE")
    args = parser.parse_args()
    settings = GestureSettings()
    for item in args.set:
        name, value = item.split("=", 1)
        current = getattr(settings, name)
        typed = type(current)(value) if not isinstance(current, bool) else value == "true"
        settings = settings.__class__(**{**settings.__dict__, name: typed})
    from dataclasses import replace

    from interactive_scrolling.gestures.recognizers import RecognizerOptions

    options = RecognizerOptions()
    for item in args.option:
        name, value = item.split("=", 1)
        current = getattr(options, name)
        typed = value == "true" if isinstance(current, bool) else type(current)(value)
        options = replace(options, **{name: typed})
    by: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for path in args.recordings:
        engine = GestureEngine(settings, options)
        analyzer = MotionAnalyzer()
        for frame in load(path):
            tracking = tracking_of(frame, False)
            out = engine.update(tracking, analyzer.update(tracking))
            for ev in out.events:
                by[f"{ev.detector or '-'} {ev.gesture.value}"].append(
                    (ev.duration_s * 1000, ev.decision_delay_s * 1000)
                )
    print(
        f"{'detector gesture':40s} {'n':>4s} {'stroke ms med':>14s} "
        f"{'decision ms med':>16s} {'p90':>6s}"
    )
    for key in sorted(by):
        rows = by[key]
        dec = sorted(d for _, d in rows)
        print(
            f"{key:40s} {len(rows):4d} {statistics.median(s for s, _ in rows):14.0f} "
            f"{statistics.median(dec):16.0f} {dec[int(0.9 * (len(dec) - 1))]:6.0f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
