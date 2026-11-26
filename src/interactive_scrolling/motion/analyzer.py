"""Motion analysis: displacement, velocity and direction of tracked hands.

Units and conventions
---------------------
* Positions are in **source pixels** of the unmirrored camera image (origin top-left,
  ``x`` right, ``y`` down). Pixels are used instead of normalized coordinates because
  they are isotropic: a circle stays a circle whatever the frame's aspect ratio.
* Time comes from the frame capture timestamps (``perf_counter_ns``), so velocities are
  correct even when frames are dropped or arrive irregularly.
* Velocity is reported in **px/s** and in **palm lengths per second** (``palms/s``),
  where one palm length is the measured wrist to middle-finger-MCP distance. The latter
  is largely independent of the hand's distance from the camera. Neither is a
  physical (m/s) velocity: that would require camera calibration and depth.
* Directions are classified in canonical (unmirrored) image space. Use
  :meth:`Direction.mirrored` or :meth:`PointMotion.display_direction` for a mirrored view.

Smoothing
---------
Positions are filtered with a time-constant exponential moving average,
``alpha = 1 - exp(-dt / tau)``, which behaves consistently at any frame rate. Velocity is
the derivative of the smoothed position, smoothed again with a second time constant.
Under constant real motion the smoothed velocity converges to the true velocity.

Robustness
----------
* A stationary/moving classification with hysteresis suppresses landmark jitter.
* Tracks unobserved for longer than ``max_observation_gap_s`` are discarded; a hand that
  reappears starts with zero velocity, so detection loss never creates velocity spikes.
* A jump larger than ``max_jump_palms`` between consecutive observations (e.g. a tracker
  swap) resets the track's motion state instead of producing a spike.
* Non-increasing timestamps are rejected.
"""

from __future__ import annotations

import enum
import logging
import math
from collections import deque
from dataclasses import dataclass

import numpy as np

from interactive_scrolling.config.settings import MotionSettings
from interactive_scrolling.core.timing import NS_PER_S
from interactive_scrolling.vision.landmarks import (
    Handedness,
    HandLandmark,
    HandObservation,
    TrackingResult,
    palm_length_px,
)

log = logging.getLogger(__name__)

_MIN_PALM_LENGTH_PX = 1.0
_MIN_DT_S = 1e-4
_HANDEDNESS_MISMATCH_PENALTY = 1.0


class Direction(enum.Enum):
    """Eight-way movement direction in image space (``UP`` is towards the top of the image)."""

    NONE = "none"
    RIGHT = "right"
    UP_RIGHT = "up-right"
    UP = "up"
    UP_LEFT = "up-left"
    LEFT = "left"
    DOWN_LEFT = "down-left"
    DOWN = "down"
    DOWN_RIGHT = "down-right"

    def mirrored(self) -> Direction:
        return _MIRRORED_DIRECTION[self]

    @property
    def label(self) -> str:
        return "Stationary" if self is Direction.NONE else self.value.replace("-", " ").title()

    @property
    def arrow(self) -> str:
        return _ARROWS[self]


_SECTORS = (
    Direction.RIGHT,
    Direction.UP_RIGHT,
    Direction.UP,
    Direction.UP_LEFT,
    Direction.LEFT,
    Direction.DOWN_LEFT,
    Direction.DOWN,
    Direction.DOWN_RIGHT,
)

_MIRRORED_DIRECTION = {
    Direction.NONE: Direction.NONE,
    Direction.RIGHT: Direction.LEFT,
    Direction.LEFT: Direction.RIGHT,
    Direction.UP: Direction.UP,
    Direction.DOWN: Direction.DOWN,
    Direction.UP_RIGHT: Direction.UP_LEFT,
    Direction.UP_LEFT: Direction.UP_RIGHT,
    Direction.DOWN_RIGHT: Direction.DOWN_LEFT,
    Direction.DOWN_LEFT: Direction.DOWN_RIGHT,
}

_ARROWS = {
    Direction.NONE: "·",
    Direction.RIGHT: "→",
    Direction.UP_RIGHT: "↗",
    Direction.UP: "↑",
    Direction.UP_LEFT: "↖",
    Direction.LEFT: "←",
    Direction.DOWN_LEFT: "↙",
    Direction.DOWN: "↓",
    Direction.DOWN_RIGHT: "↘",
}


def classify_direction(vx: float, vy: float) -> Direction:
    """Classify an image-space vector (``y`` down) into one of eight 45-degree sectors."""
    if vx == 0.0 and vy == 0.0:
        return Direction.NONE
    angle = math.degrees(math.atan2(-vy, vx)) % 360.0
    return _SECTORS[int(((angle + 22.5) % 360.0) // 45.0)]


def smoothing_alpha(dt_s: float, time_constant_s: float) -> float:
    """EMA weight for a sample ``dt_s`` after the previous one. ``1.0`` disables smoothing."""
    if time_constant_s <= 0.0:
        return 1.0
    return 1.0 - math.exp(-dt_s / time_constant_s)


@dataclass(frozen=True, slots=True)
class TrailPoint:
    timestamp_ns: int
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class PointMotion:
    """Motion of one tracked point (index fingertip or palm centre), in source pixels."""

    position_px: tuple[float, float]
    frame_displacement_px: tuple[float, float]
    """Smoothed displacement since the previous observation of this hand."""
    window_displacement_px: tuple[float, float]
    """Net smoothed displacement over the configured displacement window."""
    velocity_px_s: tuple[float, float]
    speed_px_s: float
    speed_palms_s: float
    is_moving: bool
    direction: Direction
    """Canonical (unmirrored) direction; ``NONE`` while stationary."""

    def display_direction(self, mirrored: bool) -> Direction:
        return self.direction.mirrored() if mirrored else self.direction


@dataclass(frozen=True, slots=True)
class HandMotion:
    """Motion state of one hand, paired with ``TrackingResult.hands[observation_index]``."""

    track_id: int
    observation_index: int
    handedness: Handedness
    timestamp_ns: int
    palm_length_px: float
    fingertip: PointMotion
    palm: PointMotion
    fingertip_trail: tuple[TrailPoint, ...]
    palm_trail: tuple[TrailPoint, ...]
    track_duration_s: float
    reset: bool
    """``True`` when this observation started or restarted the track's motion estimate."""


@dataclass(frozen=True, slots=True)
class MotionFrame:
    timestamp_ns: int
    hands: tuple[HandMotion, ...] = ()

    def for_observation(self, index: int) -> HandMotion | None:
        for hand in self.hands:
            if hand.observation_index == index:
                return hand
        return None


class _PointState:
    __slots__ = ("moving", "position", "velocity")

    def __init__(self, position: np.ndarray) -> None:
        self.position = position.copy()
        self.velocity = np.zeros(2)
        self.moving = False

    def update(self, raw: np.ndarray, dt_s: float, a_pos: float, a_vel: float) -> np.ndarray:
        new_position = self.position + a_pos * (raw - self.position)
        displacement = new_position - self.position
        self.velocity = self.velocity + a_vel * (displacement / dt_s - self.velocity)
        self.position = new_position
        return displacement

    def update_moving(self, palm_length: float, settings: MotionSettings) -> float:
        speed_palms = float(np.hypot(*self.velocity)) / palm_length
        threshold = (
            settings.stationary_threshold_palms_per_s
            if self.moving
            else settings.moving_threshold_palms_per_s
        )
        self.moving = speed_palms >= threshold
        return speed_palms


class _Track:
    def __init__(
        self,
        track_id: int,
        timestamp_ns: int,
        handedness: Handedness,
        tip: np.ndarray,
        palm: np.ndarray,
        palm_length: float,
        capacity: int,
    ) -> None:
        self.id = track_id
        self.history: deque[tuple[int, float, float, float, float]] = deque(maxlen=capacity)
        self.restart(timestamp_ns, handedness, tip, palm, palm_length)

    def restart(
        self,
        timestamp_ns: int,
        handedness: Handedness,
        tip: np.ndarray,
        palm: np.ndarray,
        palm_length: float,
    ) -> None:
        self.started_ns = timestamp_ns
        self.last_ns = timestamp_ns
        self.handedness = handedness
        self.palm_length = palm_length
        self.tip = _PointState(tip)
        self.palm = _PointState(palm)
        self.tip_step = np.zeros(2)
        self.palm_step = np.zeros(2)
        self.history.clear()
        self.history.append((timestamp_ns, *tip, *palm))


class MotionAnalyzer:
    """Stateful per-hand motion estimator fed with consecutive tracking results.

    Not thread-safe; owned by the processing thread.
    """

    def __init__(self, settings: MotionSettings | None = None) -> None:
        self._settings = settings or MotionSettings()
        self._tracks: list[_Track] = []
        self._next_id = 1
        self._last_timestamp_ns: int | None = None

    @property
    def settings(self) -> MotionSettings:
        return self._settings

    @property
    def active_track_count(self) -> int:
        return len(self._tracks)

    def reset(self) -> None:
        """Forget all tracks (e.g. when the camera restarts)."""
        self._tracks.clear()
        self._last_timestamp_ns = None

    def update(self, tracking: TrackingResult) -> MotionFrame:
        ts = tracking.timestamp_ns
        if self._last_timestamp_ns is not None and ts <= self._last_timestamp_ns:
            log.debug("Ignoring non-increasing timestamp %d", ts)
            return MotionFrame(timestamp_ns=ts)
        self._last_timestamp_ns = ts
        s = self._settings
        gap_ns = int(s.max_observation_gap_s * NS_PER_S)
        self._tracks = [t for t in self._tracks if ts - t.last_ns <= gap_ns]

        w, h = tracking.image_width, tracking.image_height
        features = [self._features(obs, w, h) for obs in tracking.hands]
        assignment = self._associate(tracking.hands, features)

        motions: list[HandMotion] = []
        for index, obs in enumerate(tracking.hands):
            tip, palm, length = features[index]
            track = assignment.get(index)
            reset = False
            if track is None:
                track = _Track(
                    self._next_id, ts, obs.handedness, tip, palm, length, s.history_capacity
                )
                self._next_id += 1
                self._tracks.append(track)
                reset = True
            else:
                reset = self._advance(track, ts, obs.handedness, tip, palm, length)
            motions.append(self._snapshot(track, index, ts, reset))
        return MotionFrame(timestamp_ns=ts, hands=tuple(motions))

    @staticmethod
    def _features(obs: HandObservation, w: int, h: int) -> tuple[np.ndarray, np.ndarray, float]:
        scale = np.array([w, h], dtype=np.float64)
        tip = obs.landmarks[HandLandmark.INDEX_FINGER_TIP, :2].astype(np.float64) * scale
        palm = obs.palm_center() * scale
        length = max(palm_length_px(obs.landmarks, w, h), _MIN_PALM_LENGTH_PX)
        return tip, palm, length

    def _associate(
        self,
        observations: tuple[HandObservation, ...],
        features: list[tuple[np.ndarray, np.ndarray, float]],
    ) -> dict[int, _Track]:
        """Greedy nearest-neighbour matching of observations to tracks by palm position."""
        candidates: list[tuple[float, int, int]] = []
        for ti, track in enumerate(self._tracks):
            for oi, obs in enumerate(observations):
                distance = float(np.hypot(*(features[oi][1] - track.palm.position)))
                cost = distance / track.palm_length
                known = Handedness.UNKNOWN not in (obs.handedness, track.handedness)
                if known and obs.handedness is not track.handedness:
                    cost += _HANDEDNESS_MISMATCH_PENALTY
                if cost <= self._settings.association_max_distance_palms:
                    candidates.append((cost, ti, oi))
        candidates.sort()
        used_tracks: set[int] = set()
        assignment: dict[int, _Track] = {}
        for _, ti, oi in candidates:
            if ti in used_tracks or oi in assignment:
                continue
            used_tracks.add(ti)
            assignment[oi] = self._tracks[ti]
        return assignment

    def _advance(
        self,
        track: _Track,
        ts: int,
        handedness: Handedness,
        tip: np.ndarray,
        palm: np.ndarray,
        length: float,
    ) -> bool:
        """Advance a matched track. Returns ``True`` if its motion state was restarted."""
        s = self._settings
        dt_s = (ts - track.last_ns) / NS_PER_S
        jump = float(np.hypot(*(palm - track.palm.position))) / track.palm_length
        if dt_s > s.max_observation_gap_s or jump > s.max_jump_palms:
            track.restart(ts, handedness, tip, palm, length)
            return True
        if dt_s < _MIN_DT_S:
            return False
        a_pos = smoothing_alpha(dt_s, s.position_time_constant_s)
        a_vel = smoothing_alpha(dt_s, s.velocity_time_constant_s)
        track.palm_length += a_pos * (length - track.palm_length)
        track.tip_step = track.tip.update(tip, dt_s, a_pos, a_vel)
        track.palm_step = track.palm.update(palm, dt_s, a_pos, a_vel)
        track.last_ns = ts
        if handedness is not Handedness.UNKNOWN:
            track.handedness = handedness
        track.history.append((ts, *track.tip.position, *track.palm.position))
        trail_cutoff = ts - int(max(s.trail_duration_s, s.displacement_window_s) * NS_PER_S)
        while len(track.history) > 1 and track.history[0][0] < trail_cutoff:
            track.history.popleft()
        return False

    def _snapshot(self, track: _Track, index: int, ts: int, reset: bool) -> HandMotion:
        s = self._settings
        window_cutoff = ts - int(s.displacement_window_s * NS_PER_S)
        reference = next((h for h in track.history if h[0] >= window_cutoff), track.history[-1])
        trail_cutoff = ts - int(s.trail_duration_s * NS_PER_S)
        recent = [h for h in track.history if h[0] >= trail_cutoff]
        return HandMotion(
            track_id=track.id,
            observation_index=index,
            handedness=track.handedness,
            timestamp_ns=ts,
            palm_length_px=track.palm_length,
            fingertip=self._point_motion(
                track.tip, track.tip_step, (reference[1], reference[2]), track.palm_length
            ),
            palm=self._point_motion(
                track.palm, track.palm_step, (reference[3], reference[4]), track.palm_length
            ),
            fingertip_trail=tuple(TrailPoint(h[0], h[1], h[2]) for h in recent),
            palm_trail=tuple(TrailPoint(h[0], h[3], h[4]) for h in recent),
            track_duration_s=(ts - track.started_ns) / NS_PER_S,
            reset=reset,
        )

    def _point_motion(
        self,
        state: _PointState,
        step: np.ndarray,
        reference: tuple[float, float],
        palm_length: float,
    ) -> PointMotion:
        speed_palms = state.update_moving(palm_length, self._settings)
        vx, vy = float(state.velocity[0]), float(state.velocity[1])
        x, y = float(state.position[0]), float(state.position[1])
        return PointMotion(
            position_px=(x, y),
            frame_displacement_px=(float(step[0]), float(step[1])),
            window_displacement_px=(x - reference[0], y - reference[1]),
            velocity_px_s=(vx, vy),
            speed_px_s=math.hypot(vx, vy),
            speed_palms_s=speed_palms,
            is_moving=state.moving,
            direction=classify_direction(vx, vy) if state.moving else Direction.NONE,
        )
