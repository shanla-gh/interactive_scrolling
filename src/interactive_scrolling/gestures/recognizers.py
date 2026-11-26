"""Per-gesture recognizers with explicit, time-based lifecycles.

Each recognizer receives one :class:`HandSample` per frame for the control hand and returns
at most one confirmed :class:`GestureEvent`. All durations come from frame timestamps, so
behaviour does not depend on the frame rate. Distances and speeds are in palm lengths.

Swipes (dynamic)
    A stroke starts when the tracked point moves along the gesture axis faster than
    ``START_SPEED`` (finger swipes additionally require the pointing pose at the start) and
    is measured from where the point last rested. It is confirmed as soon as the
    displacement since the start reaches the minimum distance, provided the peak speed, the
    direction ratio, the pose fraction and the maximum duration are all satisfied. After a
    confirmation the recognizer goes through COOLDOWN and REARMING (the point must be still
    for ``rearm_still_s``); opposite-direction strokes within ``return_window_s`` are treated
    as the hand's return movement.

Static poses
    A candidate starts when the pose is shown with the palm nearly still; it is confirmed
    after the hold time. Short pose dropouts (tracking flicker) are tolerated. After a
    confirmation the pose must be released for ``RELEASE_S`` before it can trigger again, so
    holding a pose produces exactly one event.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from interactive_scrolling.config.settings import GestureSettings
from interactive_scrolling.core.timing import NS_PER_S
from interactive_scrolling.gestures.pose import HandPose, PoseLabel
from interactive_scrolling.gestures.types import (
    GestureCandidate,
    GestureEvent,
    GesturePhase,
    GestureRejection,
    GestureType,
)
from interactive_scrolling.vision.landmarks import Handedness

START_SPEED = 0.8
"""Axis speed (palms/s) that starts a swipe candidate."""
STALL_SPEED = 0.4
"""Axis speed (palms/s) below which a started stroke is considered to have stopped."""
STALL_TIME_S = 0.12
POSE_DROPOUT_S = 0.15
"""Static poses survive pose-classification gaps up to this long."""
RELEASE_S = 0.25
"""A static pose must be absent this long before it can trigger again."""
INITIAL_REARM_STILL_S = 0.2
"""A newly acquired control hand must be nearly still this long before its first swipe, so a
hand raised into view (for example already pointing) cannot register as a swipe."""


@dataclass(frozen=True, slots=True)
class HandSample:
    """What the recognizers need about the control hand in one frame."""

    timestamp_ns: int
    track_id: int
    handedness: Handedness
    pose: HandPose
    fingertip: tuple[float, float]
    """Smoothed index fingertip position, source pixels."""
    palm: tuple[float, float]
    fingertip_velocity: tuple[float, float]
    """Fingertip velocity in palm lengths per second (image axes, y down)."""
    palm_velocity: tuple[float, float]
    palm_length_px: float


@dataclass(slots=True)
class Step:
    """Result of feeding one sample to a recognizer."""

    event: GestureEvent | None = None
    candidate: GestureCandidate | None = None
    rejection: GestureRejection | None = None


def _seconds(ns: int) -> float:
    return ns / NS_PER_S


class SwipeRecognizer:
    """Directional strokes of the fingertip (finger swipes) or the palm (hand sweeps).

    Directions are reported from the user's perspective. The camera image is not mirrored, so
    a movement to the user's right appears as a movement to the image left; the horizontal
    axis is therefore negated before classification. Mirroring of the preview does not change
    the result.
    """

    def __init__(
        self,
        name: str,
        positive: GestureType,
        negative: GestureType,
        horizontal: bool,
        use_palm: bool,
        pose_ok: Callable[[HandPose], bool],
        pose_fraction: float,
        settings: GestureSettings,
        pose_required_at_start: bool = True,
    ) -> None:
        self.name = name
        self.pose_required_at_start = pose_required_at_start
        self.positive = positive
        self.negative = negative
        self.horizontal = horizontal
        self.use_palm = use_palm
        self.pose_ok = pose_ok
        self.pose_fraction = pose_fraction
        self.settings = settings
        self.phase = GesturePhase.REARMING
        self._still_since_ns: int | None = None
        self._rearm_still_s = INITIAL_REARM_STILL_S
        self._phase_until_ns = 0
        self._last_confirm: tuple[int, int] | None = None
        """(end of the confirmed stroke's movement in ns, sign)."""
        self._reset_stroke()

    @property
    def gestures(self) -> tuple[GestureType, GestureType]:
        return self.positive, self.negative

    def _thresholds(self) -> tuple[float, float, float]:
        s = self.settings
        if self.horizontal:
            return (
                s.hand_sweep_min_distance_palms,
                s.hand_sweep_min_speed_palms_s,
                s.hand_sweep_max_duration_s,
            )
        return (
            s.finger_swipe_min_distance_palms,
            s.finger_swipe_min_speed_palms_s,
            s.finger_swipe_max_duration_s,
        )

    def _reset_stroke(self) -> None:
        self._start_ns = 0
        self._start_pos = (0.0, 0.0)
        self._sign = 0
        self._peak_px = 0.0
        self._scale_px = 0.0
        self._frames = 0
        self._pose_frames = 0
        self._stall_since_ns: int | None = None
        self._turn: tuple[float, tuple[float, float], int] = (0.0, (0.0, 0.0), 0)
        self._rest: tuple[tuple[float, float], int] | None = None
        """Last position (and time) at which the point was not moving along the axis."""
        """(furthest axis displacement, its position, its timestamp) of the current stroke."""

    def _axes(self, vector: tuple[float, float]) -> tuple[float, float]:
        """(axis, cross) components; horizontal axis uses the user's left/right."""
        x, y = vector
        return (-x, y) if self.horizontal else (y, x)

    def _gesture(self, sign: int) -> GestureType:
        return self.positive if sign > 0 else self.negative

    def reset(self, rearm: bool = True) -> None:
        """Forget any stroke (tracking loss or a new control hand)."""
        self._reset_stroke()
        self._rest = None
        self.phase = GesturePhase.REARMING if rearm else GesturePhase.IDLE
        self._still_since_ns = None
        self._rearm_still_s = INITIAL_REARM_STILL_S
        self._last_confirm = None

    def block_until(self, timestamp_ns: int) -> None:
        """Global cooldown imposed by another recognizer's confirmation."""
        if self.phase is GesturePhase.CANDIDATE:
            self._reset_stroke()
        self.phase = GesturePhase.COOLDOWN
        self._phase_until_ns = max(self._phase_until_ns, timestamp_ns)

    def update(self, sample: HandSample) -> Step:
        ts = sample.timestamp_ns
        position = sample.palm if self.use_palm else sample.fingertip
        velocity = sample.palm_velocity if self.use_palm else sample.fingertip_velocity
        v_axis, v_cross = self._axes(velocity)
        speed = math.hypot(*velocity)
        if self._last_confirm is not None and self.phase is not GesturePhase.CANDIDATE:
            # Follow the confirmed stroke to its end: the return window starts when the hand
            # stops moving in the stroke direction, not at the moment of confirmation.
            end_ns, sign = self._last_confirm
            if v_axis * sign > STALL_SPEED and end_ns >= ts - int(0.1 * NS_PER_S):
                self._last_confirm = (ts, sign)

        if self.phase is GesturePhase.CONFIRMED:
            self.phase = GesturePhase.COOLDOWN
        if self.phase is GesturePhase.COOLDOWN:
            if ts < self._phase_until_ns:
                return Step()
            self.phase = GesturePhase.REARMING
            self._still_since_ns = None
        if self.phase is GesturePhase.REARMING:
            if speed <= self.settings.rearm_max_speed_palms_s:
                if self._still_since_ns is None:
                    self._still_since_ns = ts
                if _seconds(ts - self._still_since_ns) >= self._rearm_still_s:
                    self.phase = GesturePhase.IDLE
            else:
                self._still_since_ns = None
            return Step()

        if self.phase is GesturePhase.IDLE:
            if abs(v_axis) < STALL_SPEED or self._rest is None:
                self._rest = (position, ts)
            if abs(v_axis) < START_SPEED or abs(v_axis) < abs(v_cross):
                return Step()
            # Measure the stroke from where the point last rested, not from the frame where
            # its speed crossed the start threshold (part of the stroke is already done then).
            rest_pos, rest_ts = self._rest
            if _seconds(ts - rest_ts) > 0.25:
                rest_pos, rest_ts = position, ts
            self._rest = None
            return self._begin(1 if v_axis > 0 else -1, rest_pos, rest_ts, sample, v_axis)

        # CANDIDATE
        min_distance, min_speed, max_duration = self._thresholds()
        gesture = self._gesture(self._sign)
        self._frames += 1
        self._pose_frames += self.pose_ok(sample.pose)
        # The palm looks shorter while the hand is turned edge-on; the largest palm length seen
        # during the stroke is the best estimate of the hand's real size.
        self._scale_px = max(self._scale_px, sample.palm_length_px)
        scale = self._scale_px
        self._peak_px = max(self._peak_px, v_axis * self._sign * sample.palm_length_px)
        peak = self._peak_px / scale
        d_axis, d_cross = self._axes(
            ((position[0] - self._start_pos[0]) / scale, (position[1] - self._start_pos[1]) / scale)
        )
        d_axis *= self._sign
        if d_axis > self._turn[0]:
            self._turn = (d_axis, position, ts)
        elapsed = _seconds(ts - self._start_ns)
        fraction = self._pose_frames / self._frames

        def reject(reason: str) -> Step:
            # A rejected stroke may flow directly into a real one (e.g. a curled wind-up
            # followed by an open-hand sweep), so the recognizer is immediately idle again.
            self._reset_stroke()
            self.phase = GesturePhase.IDLE
            return Step(rejection=GestureRejection(gesture, reason, ts))

        if d_axis >= min_distance:
            if abs(d_cross) * self.settings.direction_ratio > d_axis:
                return reject("diagonal movement")
            if peak < min_speed:
                return reject("too slow")
            if fraction < self.pose_fraction or self._pose_frames < 2:
                return reject(f"pose not held ({self._pose_label()} required)")
            if self._last_confirm is not None:
                last_ts, last_sign = self._last_confirm
                if last_sign != self._sign and _seconds(ts - last_ts) < (
                    self.settings.return_window_s
                ):
                    return reject("return movement after previous swipe")
            event = GestureEvent(
                gesture=gesture,
                timestamp_ns=ts,
                track_id=sample.track_id,
                handedness=sample.handedness,
                direction=_DIRECTIONS[gesture],
                magnitude_palms=round(d_axis, 3),
                peak_speed_palms_s=round(peak, 3),
                duration_s=round(elapsed, 3),
            )
            self._last_confirm = (ts, self._sign)
            self._reset_stroke()
            self._rearm_still_s = self.settings.rearm_still_s
            self.phase = GesturePhase.CONFIRMED
            self._phase_until_ns = ts + int(self.settings.cooldown_s * NS_PER_S)
            return Step(event=event)
        if v_axis * self._sign <= -START_SPEED or d_axis < -0.2:
            # Reversal: the opposite stroke starts from the turning point, so a wind-up that
            # flows straight into the real movement does not cut the real stroke short.
            _, turn_pos, turn_ts = self._turn
            new_sign = -self._sign
            rejection = reject("direction reversed").rejection
            step = self._begin(new_sign, turn_pos, turn_ts, sample, v_axis)
            step.rejection = rejection
            return step
        if elapsed > max_duration:
            return reject("too slow")
        if abs(d_cross) > max(0.6, d_axis):
            return reject("diagonal movement")
        if v_axis * self._sign < STALL_SPEED:
            if self._stall_since_ns is None:
                self._stall_since_ns = ts
            elif _seconds(ts - self._stall_since_ns) >= STALL_TIME_S:
                return reject("movement too short")
        else:
            self._stall_since_ns = None
        progress = max(0.0, min(1.0, d_axis / min_distance))
        return Step(candidate=GestureCandidate(gesture, progress, elapsed))

    def _begin(
        self,
        sign: int,
        start_pos: tuple[float, float],
        start_ns: int,
        sample: HandSample,
        v_axis: float,
    ) -> Step:
        pose_now = self.pose_ok(sample.pose)
        if self.pose_required_at_start and not pose_now:
            return Step()
        self.phase = GesturePhase.CANDIDATE
        self._sign = sign
        self._start_ns = start_ns
        self._start_pos = start_pos
        self._turn = (0.0, start_pos, start_ns)
        self._frames = 1
        self._pose_frames = int(pose_now)
        self._scale_px = sample.palm_length_px
        self._peak_px = max(0.0, v_axis * sign) * sample.palm_length_px
        self._stall_since_ns = None
        return Step(candidate=GestureCandidate(self._gesture(sign), 0.0, 0.0))

    def _pose_label(self) -> str:
        return "open hand" if self.use_palm else "pointing finger"


_DIRECTIONS = {
    GestureType.FINGER_SWIPE_DOWN: "down",
    GestureType.FINGER_SWIPE_UP: "up",
    GestureType.HAND_SWIPE_LEFT: "left",
    GestureType.HAND_SWIPE_RIGHT: "right",
}


class StaticPoseRecognizer:
    """A pose that must be held still for a minimum time; one event per presentation."""

    def __init__(
        self,
        gesture: GestureType,
        pose_ok: Callable[[HandPose], bool],
        hold_s: Callable[[], float],
        settings: GestureSettings,
    ) -> None:
        self.gesture = gesture
        self.pose_ok = pose_ok
        self.hold_s = hold_s
        self.settings = settings
        self.phase = GesturePhase.IDLE
        self._start_ns = 0
        self._last_pose_ns: int | None = None
        self._absent_since_ns: int | None = None
        self._phase_until_ns = 0

    @property
    def gestures(self) -> tuple[GestureType]:
        return (self.gesture,)

    def reset(self, rearm: bool = False) -> None:
        self.phase = GesturePhase.REARMING if rearm else GesturePhase.IDLE
        self._last_pose_ns = None
        self._absent_since_ns = None

    def block_until(self, timestamp_ns: int) -> None:
        if self.phase is GesturePhase.CANDIDATE:
            self.phase = GesturePhase.IDLE
        if self.phase is GesturePhase.IDLE:
            self.phase = GesturePhase.COOLDOWN
        self._phase_until_ns = max(self._phase_until_ns, timestamp_ns)

    def cancel(self, timestamp_ns: int, reason: str) -> Step:
        if self.phase is not GesturePhase.CANDIDATE:
            return Step()
        self.phase = GesturePhase.IDLE
        return Step(rejection=GestureRejection(self.gesture, reason, timestamp_ns))

    def update(self, sample: HandSample) -> Step:
        ts = sample.timestamp_ns
        present = self.pose_ok(sample.pose)
        still = math.hypot(*sample.palm_velocity) <= self.settings.static_max_speed_palms_s
        if present:
            self._last_pose_ns = ts
            self._absent_since_ns = None
        elif self._absent_since_ns is None:
            self._absent_since_ns = ts

        if self.phase is GesturePhase.CONFIRMED:
            self.phase = GesturePhase.COOLDOWN
        if self.phase is GesturePhase.COOLDOWN:
            if ts < self._phase_until_ns:
                return Step()
            self.phase = GesturePhase.REARMING
        if self.phase is GesturePhase.REARMING:
            released = (
                self._absent_since_ns is not None
                and _seconds(ts - self._absent_since_ns) >= RELEASE_S
            )
            if released:
                self.phase = GesturePhase.IDLE
            return Step()

        if self.phase is GesturePhase.IDLE:
            if present and still:
                self.phase = GesturePhase.CANDIDATE
                self._start_ns = ts
                return Step(candidate=GestureCandidate(self.gesture, 0.0, 0.0))
            return Step()

        # CANDIDATE
        if not still:
            return self.cancel(ts, "hand moving")
        if not present:
            gap = _seconds(ts - (self._last_pose_ns or ts))
            if gap > POSE_DROPOUT_S:
                return self.cancel(ts, "pose released before hold time")
        held = _seconds(ts - self._start_ns)
        required = self.hold_s()
        if held >= required and present:
            self.phase = GesturePhase.CONFIRMED
            self._phase_until_ns = ts + int(self.settings.cooldown_s * NS_PER_S)
            self._absent_since_ns = None
            return Step(
                event=GestureEvent(
                    gesture=self.gesture,
                    timestamp_ns=ts,
                    track_id=sample.track_id,
                    handedness=sample.handedness,
                    duration_s=round(held, 3),
                )
            )
        return Step(candidate=GestureCandidate(self.gesture, min(1.0, held / required), held))


def pointing(pose: HandPose) -> bool:
    return pose.label is PoseLabel.POINTING


def open_hand(pose: HandPose) -> bool:
    return pose.label is PoseLabel.OPEN_PALM


def thumbs_up(pose: HandPose) -> bool:
    return pose.label is PoseLabel.THUMBS_UP


def stop_pose(pose: HandPose) -> bool:
    return pose.is_stop_pose
