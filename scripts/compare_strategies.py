"""Brief 005 Milestone 18: compare recognition strategies on every available evaluation set.

For each configuration (``--config name:FIELD=VALUE,FIELD=VALUE`` or the built-in Brief 005
set) it replays:

* the real recordings (finger swipes up/down, stop, negatives),
* ``--synthetic-fist`` (real palm motion, fingers re-posed as a fist; SEMI-SYNTHETIC),
* ``--synthetic-horizontal`` (rotated real pointing swipes; SEMI-SYNTHETIC),

and prints recall per direction and the false events in negative segments and in all segments,
so strategies are compared on identical material. All of it is development data (see
docs/benchmarks); it does not replace the Director's session-4 recordings.

Usage:
    python scripts/compare_strategies.py recordings/gestures_*.json
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from evaluate_gestures import (
    Result,
    evaluate,
    fist_segments,
    load,
    rotate_vertical_segments,
)
from interactive_scrolling.config.settings import GestureSettings
from interactive_scrolling.gestures.recognizers import V03_OPTIONS, RecognizerOptions

CONFIGS: dict[str, tuple[dict, RecognizerOptions]] = {
    "0.3 (pose-first)": ({"control_style": "finger"}, V03_OPTIONS),
    "0.4 finger": ({"control_style": "finger"}, RecognizerOptions()),
    "fist only 0.5": ({"control_style": "fist"}, RecognizerOptions()),
    "hybrid 0.25": (
        {"control_style": "hybrid", "fist_swipe_distance_palms": 0.25},
        RecognizerOptions(),
    ),
    "hybrid 0.40": (
        {"control_style": "hybrid", "fist_swipe_distance_palms": 0.4},
        RecognizerOptions(),
    ),
    "hybrid 0.50": (
        {"control_style": "hybrid", "fist_swipe_distance_palms": 0.5},
        RecognizerOptions(),
    ),
    "hybrid 0.80": (
        {"control_style": "hybrid", "fist_swipe_distance_palms": 0.8},
        RecognizerOptions(),
    ),
}


def run(paths: list[Path], settings: GestureSettings, options: RecognizerOptions, transform=None):  # type: ignore[no-untyped-def]
    result = Result()
    for path in paths:
        frames = load(path)
        if transform is not None:
            frames = transform(frames)
        evaluate(frames, settings, False, False, result, path.stem, False, options)
    return result


def summary(result: Result, prefix: str = "") -> str:
    parts = []
    for category, row in sorted(result.rows.items()):
        if row.expected and category.startswith(prefix) and "stop" not in category:
            parts.append(f"{category.split('(')[0].strip()[-14:]} {row.detected}/{row.expected}")
    false_all = sum(r.false_triggers for r in result.rows.values())
    false_neg = sum(r.false_triggers for c, r in result.rows.items() if c.startswith("negative"))
    return "; ".join(parts) + f" | false {false_all} ({false_neg} in negatives)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("recordings", nargs="+", type=Path)
    parser.add_argument("--config", action="append", default=[])
    args = parser.parse_args()
    configs = dict(CONFIGS)
    for item in args.config:
        name, values = item.split(":", 1)
        fields = {}
        for pair in values.split(","):
            key, value = pair.split("=", 1)
            current = getattr(GestureSettings(), key)
            fields[key] = (
                value == "true"
                if isinstance(current, bool)
                else float(value)
                if isinstance(current, float)
                else value
            )
        configs[name] = (fields, RecognizerOptions())
    for name, (fields, options) in configs.items():
        settings = replace(GestureSettings(), **fields)
        real = run(args.recordings, settings, options)
        fist = run(args.recordings, settings, options, fist_segments)
        horizontal = run(args.recordings, settings, options, rotate_vertical_segments)
        print(f"== {name}")
        print(f"   real      : {summary(real)}")
        print(f"   fist (syn): {summary(fist, 'SYNTHETIC fist')}")
        print(f"   horiz(syn): {summary(horizontal, 'SYNTHETIC index')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
