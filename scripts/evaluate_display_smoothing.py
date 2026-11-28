"""Display-only skeleton smoothing: shimmer reduction versus visible lag (Brief 009).

Replays the recordings through ``LandmarkSmoother`` with candidate One Euro parameters and
reports, for the index fingertip (development recordings, one person):

* still-hand jitter: mean frame-to-frame movement while the raw fingertip moves < 0.3 hand
  lengths per second, smoothed relative to raw (lower = calmer);
* fast-movement lag: during frames where the raw fingertip moves > 3 hand lengths per second,
  the distance between the drawn (smoothed) and the real fingertip, as pixels and as time
  (distance / speed).

Usage: python scripts/evaluate_display_smoothing.py recordings/gestures_*.json
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_gestures import load, tracking_of
from interactive_scrolling.visualization import smoothing

CANDIDATES = [(1.0, 0.2), (1.0, 0.5), (1.5, 0.5), (1.0, 1.0), (2.0, 1.0)]


def evaluate(paths: list[Path], min_cutoff: float, beta: float) -> dict:
    smoothing.MIN_CUTOFF_HZ = min_cutoff
    smoothing.BETA = beta
    still_raw, still_smooth, lag_px, lag_ms = [], [], [], []
    for path in paths:
        smoother = smoothing.LandmarkSmoother()
        prev = None
        for frame in load(path):
            tracking = tracking_of(frame, False)
            if len(tracking.hands) != 1:
                smoother.reset()
                prev = None
                continue
            drawn = smoother.smooth(tracking).hands[0].landmarks
            raw = tracking.hands[0].landmarks
            w, h = frame["w"], frame["h"]
            tip = np.array([raw[8, 0] * w, raw[8, 1] * h])
            tip_s = np.array([drawn[8, 0] * w, drawn[8, 1] * h])
            palm = np.linalg.norm((raw[9, :2] - raw[0, :2]) * (w, h)) or 1.0
            if prev is not None:
                dt = (frame["t_ns"] - prev[0]) / 1e9
                if 0 < dt < 0.1:
                    speed_px = np.linalg.norm(tip - prev[1]) / dt
                    speed = speed_px / palm
                    if speed < 0.3:
                        still_raw.append(np.linalg.norm(tip - prev[1]))
                        still_smooth.append(np.linalg.norm(tip_s - prev[2]))
                    elif speed > 3.0:
                        distance = float(np.linalg.norm(tip - tip_s))
                        lag_px.append(distance)
                        lag_ms.append(1000 * distance / speed_px)
            prev = (frame["t_ns"], tip, tip_s)
    return {
        "jitter_ratio": round(statistics.mean(still_smooth) / statistics.mean(still_raw), 3),
        "fast_lag_px_median": round(statistics.median(lag_px), 1),
        "fast_lag_ms_median": round(statistics.median(lag_ms), 1),
        "fast_lag_ms_p90": round(sorted(lag_ms)[int(0.9 * (len(lag_ms) - 1))], 1),
        "fast_frames": len(lag_ms),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("recordings", nargs="+", type=Path)
    args = parser.parse_args()
    for min_cutoff, beta in CANDIDATES:
        r = evaluate(args.recordings, min_cutoff, beta)
        print(f"min_cutoff {min_cutoff} Hz, beta {beta}: {r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
