"""Brief 004 CP B3: landmark smoothing and frame-rate robustness on the recordings.

Filters compared on the index fingertip (positions in source pixels, velocity from the
smoothed positions as in ``motion.analyzer``):

* ``none``      - no position smoothing (velocity still smoothed),
* ``ema-20``    - exponential moving average, time constant 20 ms,
* ``ema-40``    - the current setting (40 ms),
* ``ema-80``    - stronger smoothing,
* ``one-euro``  - One Euro filter (Casiez et al. 2012): cut-off rises with speed, so slow
  jitter is smoothed strongly and fast movements pass with little lag.

Measured per filter:

* jitter - standard deviation (in hand lengths) of the fingertip around a 0.5 s moving
  average while the hand holds a pose still (pose_pointing, pose_fist, pose_thumbs_up);
* lag - how much later the smoothed fingertip than the raw one first passes 0.5 hand lengths
  from where a stroke started (strokes of the swipe segments);
* recognition - the gesture benchmark (recall and false triggers) with that filter.

Frame-rate robustness replays every 2nd and every 3rd recorded frame and the recording with 10 %
of the frames dropped at random (time stamps are kept, so the recognizer sees real gaps); the
effective frame rate is printed.

Usage:
    python scripts/experiment_filtering.py recordings/gestures_*.json
"""

from __future__ import annotations

import argparse
import math
import random
import sys
from pathlib import Path

import numpy as np

import evaluate_gestures
import interactive_scrolling.motion.analyzer as analyzer_module
from evaluate_gestures import Result, evaluate, load, tracking_of
from interactive_scrolling.config.settings import GestureSettings, MotionSettings
from interactive_scrolling.motion.analyzer import MotionAnalyzer

STILL = ("pose_pointing", "pose_fist", "pose_thumbs_up")
STROKES = ("swipe_down_x4", "swipe_up_x4", "point_down_x4", "point_up_x4")


class _OneEuro:
    """One Euro filter for a 2D point (min cut-off 1.0 Hz, beta 0.02 px^-1, d cut-off 1 Hz)."""

    __slots__ = ("_dx", "moving", "position", "velocity")

    MIN_CUTOFF = 1.0
    BETA = 0.02
    D_CUTOFF = 1.0

    def __init__(self, position: np.ndarray) -> None:
        self.position = position.copy()
        self.velocity = np.zeros(2)
        self.moving = False
        self._dx = np.zeros(2)

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def update(self, raw: np.ndarray, dt_s: float, a_pos: float, a_vel: float) -> np.ndarray:
        dx = (raw - self.position) / dt_s
        self._dx = self._dx + self._alpha(self.D_CUTOFF, dt_s) * (dx - self._dx)
        cutoff = self.MIN_CUTOFF + self.BETA * float(np.hypot(*self._dx))
        new_position = self.position + self._alpha(cutoff, dt_s) * (raw - self.position)
        displacement = new_position - self.position
        self.velocity = self.velocity + a_vel * (displacement / dt_s - self.velocity)
        self.position = new_position
        return displacement

    def update_moving(self, palm_length: float, settings: MotionSettings) -> float:
        speed = float(np.hypot(*self.velocity)) / palm_length
        threshold = (
            settings.stationary_threshold_palms_per_s
            if self.moving
            else settings.moving_threshold_palms_per_s
        )
        self.moving = speed >= threshold
        return speed


FILTERS = {
    "none": MotionSettings(position_time_constant_s=0.0),
    "ema-20": MotionSettings(position_time_constant_s=0.02),
    "ema-40": MotionSettings(),
    "ema-80": MotionSettings(position_time_constant_s=0.08),
    "one-euro": MotionSettings(),
}


def _with_filter(name: str):  # type: ignore[no-untyped-def]
    original = analyzer_module._PointState
    if name == "one-euro":
        analyzer_module._PointState = _OneEuro  # type: ignore[misc]
    return original


def measure(frames: list[dict], name: str) -> tuple[list[float], list[float]]:
    original = _with_filter(name)
    try:
        analyzer = MotionAnalyzer(FILTERS[name])
        jitter_series: dict[int, list[tuple[float, float, float]]] = {}
        lags: list[float] = []
        stroke_state: dict = {}
        for frame in frames:
            tracking = tracking_of(frame, mirror=False)
            motion = analyzer.update(tracking)
            if len(motion.hands) != 1:
                stroke_state.clear()
                continue
            hand = motion.hands[0]
            raw = tracking.hands[hand.observation_index].landmarks[8, :2] * (
                tracking.image_width,
                tracking.image_height,
            )
            smooth = np.array(hand.fingertip.position_px)
            scale = hand.palm_length_px
            t = frame["t_ns"] / 1e9
            if frame["label"] in STILL:
                jitter_series.setdefault(frame["segment"], []).append((t, *(smooth / scale)))
            if frame["label"] in STROKES:
                speed = math.hypot(*hand.fingertip.velocity_px_s) / scale
                if not stroke_state and speed < 0.4:
                    stroke_state.update(origin_raw=raw.copy(), origin=smooth.copy())
                elif stroke_state:
                    d_raw = np.hypot(*(raw - stroke_state["origin_raw"])) / scale
                    d_smooth = np.hypot(*(smooth - stroke_state["origin"])) / scale
                    if "t_raw" not in stroke_state and d_raw >= 0.5:
                        stroke_state["t_raw"] = t
                    if "t_raw" in stroke_state and d_smooth >= 0.5:
                        lags.append(t - stroke_state["t_raw"])
                        stroke_state.clear()
                    elif speed < 0.4 and "t_raw" not in stroke_state:
                        stroke_state.update(origin_raw=raw.copy(), origin=smooth.copy())
        jitters = []
        for series in jitter_series.values():
            a = np.array(series)
            if len(a) < 20:
                continue
            for axis in (1, 2):
                trend = np.convolve(a[:, axis], np.ones(15) / 15, mode="same")
                jitters.append(float(np.std((a[:, axis] - trend)[7:-7])))
        return jitters, lags
    finally:
        analyzer_module._PointState = original  # type: ignore[misc]


def recognition(paths: list[Path], name: str, transform=None) -> tuple[int, int, int, int]:  # type: ignore[no-untyped-def]
    original = _with_filter(name)
    try:
        result = Result()
        for path in paths:
            frames = load(path)
            if transform is not None:
                frames = transform(frames)
            saved = evaluate_gestures.MotionAnalyzer
            evaluate_gestures.MotionAnalyzer = lambda: MotionAnalyzer(FILTERS[name])  # type: ignore[assignment]
            try:
                evaluate(frames, GestureSettings(), False, False, result, path.stem, False)
            finally:
                evaluate_gestures.MotionAnalyzer = saved
        expected = sum(r.expected for r in result.rows.values())
        detected = sum(r.detected for r in result.rows.values())
        false = sum(r.false_triggers for r in result.rows.values())
        negative_false = sum(
            r.false_triggers for c, r in result.rows.items() if c.startswith("negative")
        )
        return detected, expected, false, negative_false
    finally:
        analyzer_module._PointState = original  # type: ignore[misc]


def subsample(fps: float):  # type: ignore[no-untyped-def]
    def transform(frames: list[dict]) -> list[dict]:
        out, next_t = [], None
        for frame in frames:
            if next_t is None or frame["t_ns"] >= next_t:
                out.append(frame)
                next_t = frame["t_ns"] + int(1e9 / fps) - 2_000_000
        return out

    return transform


def every(n: int):  # type: ignore[no-untyped-def]
    def transform(frames: list[dict]) -> list[dict]:
        return frames[::n]

    return transform


def effective_fps(paths: list[Path], transform) -> float:  # type: ignore[no-untyped-def]
    rates = []
    for path in paths:
        frames = load(path)
        if transform is not None:
            frames = transform(frames)
        span = (frames[-1]["t_ns"] - frames[0]["t_ns"]) / 1e9
        rates.append((len(frames) - 1) / span)
    return float(np.mean(rates))


def drop(fraction: float, seed: int = 7):  # type: ignore[no-untyped-def]
    def transform(frames: list[dict]) -> list[dict]:
        rng = random.Random(seed)
        return [f for f in frames if rng.random() >= fraction]

    return transform


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("recordings", nargs="+", type=Path)
    args = parser.parse_args()
    header = f"{'filter':9} {'jitter (hand lengths)':>22} {'lag at 0.5 (ms)':>18}"
    print(f"{header} {'recall':>8} {'false':>6}")
    for name in FILTERS:
        jitters, lags = [], []
        for path in args.recordings:
            j, lag = measure(load(path), name)
            jitters += j
            lags += lag
        detected, expected, false, negative_false = recognition(args.recordings, name)
        print(
            f"{name:9} {np.median(jitters):12.4f} (n={len(jitters):2})"
            f" {1000 * np.median(lags):8.0f} (n={len(lags):2})"
            f" {detected:3}/{expected:<3} {false:3} ({negative_false} in negatives)"
        )
    print("\nframe-rate robustness (current filter):")
    for label, transform in (
        ("recorded", None),
        ("every 2nd frame", every(2)),
        ("every 3rd frame", every(3)),
        ("10 % frames dropped", drop(0.10)),
    ):
        detected, expected, false, negative_false = recognition(
            args.recordings, "ema-40", transform
        )
        rate = effective_fps(args.recordings, transform)
        print(
            f"  {label:20} ({rate:4.1f} fps) {detected}/{expected}  false {false} "
            f"({negative_false} in negatives)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
