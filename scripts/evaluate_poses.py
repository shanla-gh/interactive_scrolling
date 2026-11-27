"""Frame-level pose classification on labeled landmark recordings.

For every labeled segment of ``scripts/record_gestures.py`` recordings, report how often each
pose label is assigned to the tracked hand, and the rate of the pose the segment asks for.
Negative segments (rest, typing, face touching, ...) show how often ordinary activity looks
like a gesture pose. ``--model 3d`` replays the version 0.3 finger rule for comparison.

This measures the pose classifier only (no timing, no hold, no tracking selection); gesture
recall is measured by ``scripts/evaluate_gestures.py``.

Usage:
    python scripts/evaluate_poses.py recordings/gestures_*.json [--model 3d|hybrid]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from evaluate_gestures import tracking_of
from interactive_scrolling.gestures.pose import FINGER_MODELS, PoseLabel, analyze_pose

TARGET = {
    "pose_open_palm": "stop",
    "pose_stop": "stop",
    "neg_open_hold": "stop",
    "pose_pointing": PoseLabel.POINTING.value,
    "point_down_x4": PoseLabel.POINTING.value,
    "point_up_x4": PoseLabel.POINTING.value,
    "swipe_down_x4": PoseLabel.POINTING.value,
    "swipe_up_x4": PoseLabel.POINTING.value,
    "index_down_x4": PoseLabel.POINTING.value,
    "index_up_x4": PoseLabel.POINTING.value,
    "index_left_x4": PoseLabel.POINTING.value,
    "index_right_x4": PoseLabel.POINTING.value,
    "pose_fist": PoseLabel.FIST.value,
    "pose_thumbs_up": PoseLabel.THUMBS_UP.value,
    "half_heart_x3": PoseLabel.HALF_HEART.value,
    "half_heart_other_hand_x3": PoseLabel.HALF_HEART.value,
    "half_heart_hold": PoseLabel.HALF_HEART.value,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("recordings", nargs="+", type=Path)
    parser.add_argument("--model", choices=FINGER_MODELS, default="3d")
    args = parser.parse_args()
    counts: dict[str, Counter] = defaultdict(Counter)
    for path in args.recordings:
        frames = json.loads(path.read_text(encoding="utf-8"))["frames"]
        for frame in frames:
            label = frame["label"]
            if label == "transition":
                continue
            if not frame["hands"]:
                counts[label]["(no hand)"] += 1
                continue
            tracking = tracking_of(frame, mirror=False)
            pose = analyze_pose(
                tracking.hands[0],
                tracking.image_width,
                tracking.image_height,
                finger_model=args.model,
            )
            counts[label][pose.label.value] += 1
            if pose.is_stop_pose:
                counts[label]["stop"] += 1
    print(f"finger model: {args.model}")
    print(f"{'segment label':26} {'frames':>6} {'hand':>6} {'target':>12} {'rate':>6}  labels")
    for label in sorted(counts, key=lambda k: (k.startswith("neg_"), k)):
        c = counts[label]
        tracked = sum(n for k, n in c.items() if k not in ("(no hand)", "stop"))
        total = tracked + c["(no hand)"]
        target = TARGET.get(label)
        rate = f"{c[target] / tracked:.0%}" if target and tracked else "-"
        shown = ", ".join(f"{k} {n}" for k, n in c.most_common() if k not in ("stop",) and n)
        stop = f" | stop-pose frames {c['stop']}" if c["stop"] else ""
        print(f"{label:26} {total:6} {tracked:6} {target or '-':>12} {rate:>6}  {shown}{stop}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
