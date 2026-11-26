"""Passive eye analytics: coarse screen-facing / looking-away / unknown estimates (no control).

Inputs per face result: head yaw and pitch (MediaPipe facial transformation matrix), the iris
position between the eye corners, and the blink blendshapes. A standard webcam does not allow
precise gaze coordinates, so only three coarse states are estimated:

* ``SCREEN``: head within ``YAW_LIMIT`` / ``PITCH_LIMIT`` of the baseline and irises within
  ``GAZE_LIMIT`` of the baseline position: probably facing the screen;
* ``AWAY``: head turned beyond 1.6 times those limits, or irises far to the side;
* ``UNKNOWN``: no face, low-quality or ambiguous measurements, eyes closed longer than a blink,
  or gaps in the measurements. **Unknown is never counted as looking away.**

The baseline is (0, 0, 0) or the result of the optional one-point calibration (look at the
middle of the screen for a few seconds). Blinks are counted from the blink blendshapes when the
sampling rate is high enough to see them (>= ``MIN_BLINK_RATE_HZ``); otherwise the blink count
is reported as unavailable.

These estimates are never used to execute actions or enforce limits, and they do not measure
attention, productivity or any psychological state. Only aggregated durations and counts are
kept; no per-frame landmarks or images.
"""

from __future__ import annotations

import enum
import statistics
from dataclasses import dataclass

import numpy as np

from interactive_scrolling.vision.face_tracker import FaceObservation

YAW_LIMIT = 25.0
PITCH_LIMIT = 20.0
GAZE_LIMIT = 0.12
FAR = 1.6
BLINK_CLOSED = 0.5
BLINK_OPEN = 0.35
MAX_BLINK_S = 0.5
MAX_SAMPLE_GAP_S = 0.5
MIN_BLINK_RATE_HZ = 10.0

R_OUTER, R_INNER, R_IRIS = 33, 133, 468
L_OUTER, L_INNER, L_IRIS = 263, 362, 473


class ViewState(enum.Enum):
    SCREEN = "screen"
    AWAY = "away"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Baseline:
    yaw: float = 0.0
    pitch: float = 0.0
    gaze: float = 0.0


@dataclass(frozen=True, slots=True)
class EyeSample:
    state: ViewState
    eyes_closed: bool
    horizontal: str | None
    """Broad gaze direction: "left", "center", "right" (the person's own sides) or None."""


def horizontal_gaze(landmarks: np.ndarray) -> float | None:
    """Iris offset between the eye corners: 0 centred, positive towards the person's left."""
    if landmarks.shape[0] <= L_IRIS:
        return None

    def ratio(outer: int, inner: int, iris: int) -> float | None:
        a = landmarks[outer, :2]
        b = landmarks[inner, :2]
        axis = b - a
        length = float(np.dot(axis, axis))
        if length < 1e-10:
            return None
        return float(np.dot(landmarks[iris, :2] - a, axis) / length)

    right = ratio(R_OUTER, R_INNER, R_IRIS)
    left = ratio(L_OUTER, L_INNER, L_IRIS)
    if right is None or left is None:
        return None
    return (right - left) / 2


def classify(face: FaceObservation | None, baseline: Baseline) -> EyeSample:
    if face is None or face.yaw_deg is None or face.pitch_deg is None:
        return EyeSample(ViewState.UNKNOWN, False, None)
    blink = face.blendshapes.get("eyeBlinkLeft", 0.0) + face.blendshapes.get("eyeBlinkRight", 0.0)
    closed = blink / 2 > BLINK_CLOSED
    gaze = horizontal_gaze(face.landmarks)
    if gaze is None:
        return EyeSample(ViewState.UNKNOWN, closed, None)
    dyaw = abs(face.yaw_deg - baseline.yaw)
    dpitch = abs(face.pitch_deg - baseline.pitch)
    dgaze = gaze - baseline.gaze
    direction = "center" if abs(dgaze) <= GAZE_LIMIT else ("left" if dgaze > 0 else "right")
    if closed:
        return EyeSample(ViewState.UNKNOWN, True, None)
    if dyaw > YAW_LIMIT * FAR or dpitch > PITCH_LIMIT * FAR or abs(dgaze) > GAZE_LIMIT * FAR:
        return EyeSample(ViewState.AWAY, False, direction)
    if dyaw <= YAW_LIMIT and dpitch <= PITCH_LIMIT and abs(dgaze) <= GAZE_LIMIT:
        return EyeSample(ViewState.SCREEN, False, direction)
    return EyeSample(ViewState.UNKNOWN, False, direction)


@dataclass(frozen=True, slots=True)
class EyeTotals:
    screen_s: float = 0.0
    away_s: float = 0.0
    unknown_s: float = 0.0
    blinks: int | None = 0
    longest_screen_s: float = 0.0
    samples: int = 0

    @property
    def total_s(self) -> float:
        return self.screen_s + self.away_s + self.unknown_s

    @property
    def quality(self) -> float | None:
        """Share of the analysed time with a known state (screen or away)."""
        total = self.total_s
        return (self.screen_s + self.away_s) / total if total > 0 else None


class EyeAnalytics:
    """Accumulates mutually exclusive durations from timestamped samples (one thread)."""

    def __init__(self, baseline: Baseline | None = None) -> None:
        self.baseline = baseline or Baseline()
        self._last_ts: float | None = None
        self._last_state = ViewState.UNKNOWN
        self._closed_since: float | None = None
        self._screen_run = 0.0
        self._times: list[float] = []
        self.reset_totals()

    def reset_totals(self) -> None:
        self.screen_s = self.away_s = self.unknown_s = 0.0
        self.blinks = 0
        self.longest_screen_s = 0.0
        self.samples = 0

    def add(self, ts: float, face: FaceObservation | None) -> EyeSample:
        sample = classify(face, self.baseline)
        state = sample.state
        if sample.eyes_closed:
            if self._closed_since is None:
                self._closed_since = ts
            if ts - self._closed_since <= MAX_BLINK_S:
                state = self._last_state  # a blink does not change where the person faces
        elif self._closed_since is not None:
            if ts - self._closed_since <= MAX_BLINK_S:
                self.blinks += 1
            self._closed_since = None
        if self._last_ts is not None:
            dt = ts - self._last_ts
            if dt > MAX_SAMPLE_GAP_S:
                self.unknown_s += dt  # no measurements: unknown, never "away"
                self._screen_run = 0.0
            elif dt > 0:
                previous = self._last_state
                if previous is ViewState.SCREEN:
                    self.screen_s += dt
                    self._screen_run += dt
                    self.longest_screen_s = max(self.longest_screen_s, self._screen_run)
                elif previous is ViewState.AWAY:
                    self.away_s += dt
                    self._screen_run = 0.0
                else:
                    self.unknown_s += dt
        if state is not ViewState.SCREEN:
            self._screen_run = 0.0
        self._last_ts = ts
        self._last_state = state
        self.samples += 1
        self._times.append(ts)
        if len(self._times) > 64:
            del self._times[:-64]
        return EyeSample(state, sample.eyes_closed, sample.horizontal)

    def rate_hz(self) -> float | None:
        if len(self._times) < 2 or self._times[-1] <= self._times[0]:
            return None
        return (len(self._times) - 1) / (self._times[-1] - self._times[0])

    def take(self) -> EyeTotals:
        """Return the totals since the last call and start new ones (for persistence)."""
        rate = self.rate_hz()
        blinks: int | None = self.blinks if rate is not None and rate >= MIN_BLINK_RATE_HZ else None
        totals = EyeTotals(
            self.screen_s,
            self.away_s,
            self.unknown_s,
            blinks,
            self.longest_screen_s,
            self.samples,
        )
        self.reset_totals()
        return totals


@dataclass(frozen=True, slots=True)
class Calibration:
    baseline: Baseline
    samples: int
    yaw_sd: float
    gaze_sd: float

    @property
    def reliable(self) -> bool:
        return self.samples >= 20 and self.yaw_sd <= 4.0 and self.gaze_sd <= 0.04


def calibrate(faces: list[FaceObservation]) -> Calibration | None:
    """One-point calibration from faces recorded while the user looked at the screen centre."""
    usable = [
        (f.yaw_deg, f.pitch_deg, g)
        for f in faces
        if f.yaw_deg is not None
        and f.pitch_deg is not None
        and (g := horizontal_gaze(f.landmarks)) is not None
    ]
    if len(usable) < 5:
        return None
    yaws, pitches, gazes = zip(*usable, strict=True)
    baseline = Baseline(statistics.fmean(yaws), statistics.fmean(pitches), statistics.fmean(gazes))
    return Calibration(
        baseline,
        len(usable),
        statistics.pstdev(yaws),
        statistics.pstdev(gazes),
    )
