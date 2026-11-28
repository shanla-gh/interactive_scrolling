"""Display-only landmark smoothing for the Broadcast overlay (Brief 007).

Landmark positions jitter by a pixel or two even when the hand is still, which makes a drawn
skeleton shimmer. The One Euro filter (Casiez et al., CHI 2012) smooths strongly at low speed
and hardly at all at high speed, so a still hand stops shimmering while a fast swipe is drawn
without visible lag.

This module only changes what the overlay *draws*. Gesture recognition, motion analysis and
the Developer view use the raw landmarks; nothing here is fed back into the pipeline. Motion
trails and vectors stay the measured values of the motion analyzer.
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np

from interactive_scrolling.vision.landmarks import HandObservation, TrackingResult

MIN_CUTOFF_HZ = 1.0
"""Cut-off frequency at rest: lower = smoother still hand, more lag when starting to move."""
BETA = 0.5
"""Speed coefficient (per hand-width of speed): higher = less lag during fast movement.
Brief 009 (scripts/evaluate_display_smoothing.py, recordings): 0.2 -> 0.5 halved the drawn
fingertip's lag during fast movement (median 3.5 -> 1.6 ms, p90 9.1 -> 4.5 ms) while the
still-hand shimmer stayed almost as low (0.82 -> 0.83 of the raw frame-to-frame movement)."""
D_CUTOFF_HZ = 1.0
RESET_JUMP = 0.25
"""A hand that moved more than this (normalized image width) between two frames is treated
as a new hand (re-detection elsewhere), not smoothed towards its old position."""


def _alpha(cutoff_hz: float, dt_s: float) -> float:
    tau = 1.0 / (2.0 * math.pi * cutoff_hz)
    return 1.0 / (1.0 + tau / dt_s)


class _HandFilter:
    def __init__(self, landmarks: np.ndarray, ts_ns: int) -> None:
        self.x = landmarks.astype(np.float64).copy()
        self.dx = np.zeros_like(self.x)
        self.ts_ns = ts_ns

    def update(self, landmarks: np.ndarray, ts_ns: int) -> np.ndarray:
        dt = (ts_ns - self.ts_ns) / 1e9
        if dt <= 0:
            return self.x.astype(np.float32)
        raw = landmarks.astype(np.float64)
        dx = (raw - self.x) / dt
        a_d = _alpha(D_CUTOFF_HZ, dt)
        self.dx = self.dx + a_d * (dx - self.dx)
        # Speed of the whole hand in hand-widths per second, so the filter behaves the same
        # at any distance from the camera.
        width = max(float(np.ptp(raw[:, 0])), 1e-3)
        speed = float(np.linalg.norm(self.dx[:, :2], axis=1).mean()) / width
        cutoff = MIN_CUTOFF_HZ + BETA * speed * 60.0
        a = _alpha(cutoff, dt)
        self.x = self.x + a * (raw - self.x)
        self.ts_ns = ts_ns
        return self.x.astype(np.float32)


class LandmarkSmoother:
    """Smooths the landmarks of every hand for drawing; hands are matched by position."""

    def __init__(self) -> None:
        self._filters: list[_HandFilter] = []

    def reset(self) -> None:
        self._filters = []

    def smooth(self, tracking: TrackingResult) -> TrackingResult:
        ts = tracking.timestamp_ns
        filters: list[_HandFilter] = []
        hands: list[HandObservation] = []
        unused = list(self._filters)
        for hand in tracking.hands:
            centre = hand.landmarks[:, :2].mean(axis=0)
            best = None
            best_d = RESET_JUMP
            for f in unused:
                d = float(np.linalg.norm(f.x[:, :2].mean(axis=0) - centre))
                if d < best_d:
                    best, best_d = f, d
            if best is None:
                best = _HandFilter(hand.landmarks, ts)
                smoothed = hand.landmarks
            else:
                unused.remove(best)
                smoothed = best.update(hand.landmarks, ts)
            filters.append(best)
            hands.append(replace(hand, landmarks=smoothed))
        self._filters = filters
        return replace(tracking, hands=tuple(hands))
