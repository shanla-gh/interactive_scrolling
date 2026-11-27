"""Brief 005 CP 12.1 / 14.1: which landmark motion carries a stroke, per direction.

For every fingertip stroke of the labeled swipe segments (Quick Calibration segmenter) this
reports, in hand lengths along the stroke's direction:

* ``tip``   - index fingertip, camera coordinates (version 0.4 reference);
* ``rel``   - index fingertip relative to the palm centre (finger flexion / extension);
* ``palm``  - palm centre (mean of wrist and the four knuckles; whole-hand or wrist motion);
* ``wrist`` - wrist landmark;
* ``dflex`` - change of the index finger's summed joint flexion (degrees, + = curling).

Strokes are grouped as *intended* (in the prompted direction), *return* (opposite, after an
intended stroke) and *wind-up* (opposite, right before one). Medians and ranges per group and
direction show which reference separates intended strokes from the rest, and whether up and
down behave alike.

Usage:
    python scripts/analyze_motion_references.py recordings/gestures_*.json
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from evaluate_gestures import load, tracking_of
from interactive_scrolling.gestures.calibration import _Segmenter
from interactive_scrolling.gestures.pose import PoseLabel, analyze_pose, hand_scale_px
from interactive_scrolling.gestures.recognizers import SWIPE_DIRECTIONS, to_user
from interactive_scrolling.gestures.types import GestureType
from interactive_scrolling.motion.analyzer import MotionAnalyzer
from interactive_scrolling.vision.landmarks import HandLandmark as L

G = GestureType
TARGET = {
    "swipe_down_x4": G.INDEX_SWIPE_DOWN,
    "swipe_up_x4": G.INDEX_SWIPE_UP,
    "point_down_x4": G.INDEX_SWIPE_DOWN,
    "point_up_x4": G.INDEX_SWIPE_UP,
    "eval_up_x5": G.INDEX_SWIPE_UP,
    "eval_down_x5": G.INDEX_SWIPE_DOWN,
    "eval_left_x5": G.INDEX_SWIPE_LEFT,
    "eval_right_x5": G.INDEX_SWIPE_RIGHT,
    "calib_up": G.INDEX_SWIPE_UP,
    "calib_down": G.INDEX_SWIPE_DOWN,
}
PALM = (L.WRIST, L.INDEX_FINGER_MCP, L.MIDDLE_FINGER_MCP, L.RING_FINGER_MCP, L.PINKY_MCP)


def frame_points(tracking) -> dict | None:  # type: ignore[no-untyped-def]
    if len(tracking.hands) != 1:
        return None
    obs = tracking.hands[0]
    img = obs.landmarks[:, :2].astype(float) * (tracking.image_width, tracking.image_height)
    palm = img[list(PALM)].mean(axis=0)
    pose = analyze_pose(obs, tracking.image_width, tracking.image_height)
    return {
        "tip": img[L.INDEX_FINGER_TIP],
        "palm": palm,
        "wrist": img[L.WRIST],
        "rel": img[L.INDEX_FINGER_TIP] - palm,
        "flex": pose.flexion["index"],
        "scale": hand_scale_px(img),
        "pointing": pose.label is PoseLabel.POINTING,
    }


def analyze(path: Path, rows: dict) -> None:
    frames = load(path)
    by_segment: dict = defaultdict(list)
    for f in frames:
        if f["label"] in TARGET:
            by_segment[(f["segment"], f["label"])].append(f)
    for (_, label), seg in by_segment.items():
        analyzer = MotionAnalyzer()
        segmenter = _Segmenter()
        points: dict[int, dict] = {}
        for f in seg:
            tracking = tracking_of(f, mirror=False)
            motion = analyzer.update(tracking)
            p = frame_points(tracking)
            if p is None or len(motion.hands) != 1:
                continue
            points[f["t_ns"]] = p
            hand = motion.hands[0]
            segmenter.add(
                f["t_ns"],
                hand.fingertip.position_px,
                hand.fingertip.velocity_px_s,
                p["scale"],
                p["pointing"],
            )
        target = TARGET[label]
        times = sorted(points)
        intended_ends = []
        for s in segmenter.strokes:
            if s.length_palms < 0.3 or s.diagonal:
                continue
            if s.direction is target:
                group = "intended"
                intended_ends.append(s.end_ns)
            elif any(0 <= s.start_ns - e <= int(1.2e9) for e in intended_ends):
                group = "return"
            else:
                group = "other/wind-up"
            a = points[min(times, key=lambda t: abs(t - s.start_ns))]
            b = points[min(times, key=lambda t: abs(t - s.end_ns))]
            direction = SWIPE_DIRECTIONS[s.direction]
            scale = a["scale"]
            values = {}
            for ref in ("tip", "rel", "palm", "wrist"):
                d = to_user(tuple((b[ref] - a[ref]) / scale))
                values[ref] = d[0] * direction[0] + d[1] * direction[1]
            values["dflex"] = b["flex"] - a["flex"]
            rows[(s.direction.name[12:], group)].append(values)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("recordings", nargs="+", type=Path)
    args = parser.parse_args()
    rows: dict = defaultdict(list)
    for path in args.recordings:
        analyze(path, rows)
    print(
        f"{'direction':6} {'group':14} {'n':>3}  "
        + "  ".join(f"{k:>16}" for k in ("tip", "rel", "palm", "wrist", "dflex"))
    )
    for (direction, group), values in sorted(rows.items()):
        cells = []
        for key in ("tip", "rel", "palm", "wrist", "dflex"):
            v = [x[key] for x in values]
            cells.append(f"{statistics.median(v):6.2f} [{min(v):5.2f},{max(v):5.2f}]")
        print(f"{direction:6} {group:14} {len(values):3}  " + "  ".join(f"{c:>16}" for c in cells))
    return 0


if __name__ == "__main__":
    sys.exit(main())
