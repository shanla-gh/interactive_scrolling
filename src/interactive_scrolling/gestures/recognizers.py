"""Per-gesture recognizers with explicit, time-based lifecycles.

Each recognizer receives one :class:`HandSample` per frame for the control hand and returns
at most one confirmed :class:`GestureEvent`. All durations come from frame timestamps, so
behaviour does not depend on the frame rate. Distances and speeds are in palm lengths.

Index swipes (dynamic, one recognizer for all four directions)
    The index fingertip of a *pointing* hand is followed in two dimensions. A stroke starts
    when the fingertip moves faster than ``START_SPEED`` along its dominant axis while the hand
    points, and is measured from where the fingertip last rested. The direction is committed
    at the start. The stroke is confirmed as soon as the displacement along that direction
    reaches the minimum distance, provided the peak speed, the direction ratio (diagonals are
    rejected, never guessed), the pose fraction and the maximum duration are all satisfied. A
    reversal starts the opposite stroke from the turning point.

Return movements
    After a swipe the hand usually moves back, about as fast and as far as the swipe itself,
    often in several parts and overshooting the starting point (seen in the recordings). Every
    opposite-direction stroke is treated as part of that *return* until the return phase ends:
    either the fingertip is back near the swipe's starting point (within
    ``RETURN_ZONE_FRACTION`` of the swipe length) and has *paused* there for
    ``RETURN_SETTLE_S``, or ``return_window_s`` has passed since the swipe's movement ended.
    So "next, then previous" needs only a brief pause after the hand has come back, not a long
    fixed delay, while a return that flows on past the start cannot trigger the opposite
    action.

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
RETURN_ZONE_FRACTION = 0.35
"""An opposite stroke that starts further than this fraction of the previous swipe's length
from that swipe's starting point is the hand's return movement."""
RETURN_SETTLE_S = 0.1
RETURN_SETTLE_SPEED = 0.5
"""The return phase ends after the fingertip has stayed below this speed (palms/s), back near
the swipe's starting point, for ``RETURN_SETTLE_S``."""
MAX_REST_AGE_S = 0.25
"""A stroke is measured from the last resting position only if that rest is this recent."""

Vector = tuple[float, float]


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


def to_user(vector: Vector) -> Vector:
    """Image vector (x right, y down) -> user space (x towards the user's right, y down).

    The camera image is not mirrored, so a movement to the user's right appears as a movement
    to the image's left. Preview mirroring has no influence (it is display-only).
    """
    return (-vector[0], vector[1])


SWIPE_DIRECTIONS: dict[GestureType, Vector] = {
    GestureType.INDEX_SWIPE_DOWN: (0.0, 1.0),
    GestureType.INDEX_SWIPE_UP: (0.0, -1.0),
    GestureType.INDEX_SWIPE_RIGHT: (1.0, 0.0),
    GestureType.INDEX_SWIPE_LEFT: (-1.0, 0.0),
}
DIRECTION_NAMES = {
    GestureType.INDEX_SWIPE_DOWN: "down",
    GestureType.INDEX_SWIPE_UP: "up",
    GestureType.INDEX_SWIPE_RIGHT: "right",
    GestureType.INDEX_SWIPE_LEFT: "left",
}
OPPOSITE = {
    GestureType.INDEX_SWIPE_DOWN: GestureType.INDEX_SWIPE_UP,
    GestureType.INDEX_SWIPE_UP: GestureType.INDEX_SWIPE_DOWN,
    GestureType.INDEX_SWIPE_RIGHT: GestureType.INDEX_SWIPE_LEFT,
    GestureType.INDEX_SWIPE_LEFT: GestureType.INDEX_SWIPE_RIGHT,
}


def _dot(a: Vector, b: Vector) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _across(a: Vector, b: Vector) -> float:
    """Magnitude of ``a`` perpendicular to the unit vector ``b``."""
    return abs(a[0] * b[1] - a[1] * b[0])


def dominant_direction(vector: Vector) -> tuple[GestureType, float, float]:
    """(direction, component along it, component across it) of a user-space vector."""
    x, y = vector
    if abs(y) >= abs(x):
        gesture = GestureType.INDEX_SWIPE_DOWN if y > 0 else GestureType.INDEX_SWIPE_UP
        return gesture, abs(y), abs(x)
    gesture = GestureType.INDEX_SWIPE_RIGHT if x > 0 else GestureType.INDEX_SWIPE_LEFT
    return gesture, abs(x), abs(y)


@dataclass(slots=True)
class _LastSwipe:
    gesture: GestureType
    start_px: Vector
    """Image position where the confirmed stroke started."""
    length_palms: float
    """Stroke length along its direction, followed to the end of the movement."""
    end_ns: int
    """When the hand stopped moving in the swipe direction."""
    scale_px: float
    settled_since_ns: int | None = None
    returned: bool = False
    """The hand came back and paused: the return phase is over."""


class DirectionalSwipeRecognizer:
    """Index-finger swipes in four directions, from the user's perspective."""

    def __init__(
        self,
        settings: GestureSettings,
        pose_ok: Callable[[HandPose], bool],
        pose_fraction: float = 0.6,
    ) -> None:
        self.settings = settings
        self.pose_ok = pose_ok
        self.pose_fraction = pose_fraction
        self.enabled: frozenset[GestureType] = frozenset(SWIPE_DIRECTIONS)
        """Directions that may confirm. Disabled directions are still followed (so their
        movement cannot be misread as another direction) but are rejected."""
        self.phase = GesturePhase.REARMING
        self._still_since_ns: int | None = None
        self._rearm_still_s = INITIAL_REARM_STILL_S
        self._phase_until_ns = 0
        self._last: _LastSwipe | None = None
        self._rest: tuple[Vector, int] | None = None
        self._reset_stroke()

    @property
    def gestures(self) -> tuple[GestureType, ...]:
        return tuple(SWIPE_DIRECTIONS)

    def _reset_stroke(self) -> None:
        self._gesture = GestureType.INDEX_SWIPE_DOWN
        self._dir: Vector = (0.0, 1.0)
        self._start_ns = 0
        self._start_pos: Vector = (0.0, 0.0)
        self._palm_start: Vector = (0.0, 0.0)
        self._peak_px = 0.0
        self._scale_px = 0.0
        self._frames = 0
        self._pose_frames = 0
        self._stall_since_ns: int | None = None
        self._turn: tuple[float, Vector, int] = (0.0, (0.0, 0.0), 0)
        """(furthest displacement along the direction, its position, its timestamp)."""
        self._return = False

    def reset(self, rearm: bool = True) -> None:
        """Forget any stroke (tracking loss or a new control hand)."""
        self._reset_stroke()
        self._rest = None
        self.phase = GesturePhase.REARMING if rearm else GesturePhase.IDLE
        self._still_since_ns = None
        self._rearm_still_s = INITIAL_REARM_STILL_S
        self._last = None

    def block_until(self, timestamp_ns: int) -> None:
        """Global cooldown imposed by another recognizer's confirmation."""
        if self.phase is GesturePhase.CANDIDATE:
            self._reset_stroke()
        self.phase = GesturePhase.COOLDOWN
        self._phase_until_ns = max(self._phase_until_ns, timestamp_ns)

    @staticmethod
    def _displacement(position: Vector, origin: Vector, scale: float) -> Vector:
        return to_user(((position[0] - origin[0]) / scale, (position[1] - origin[1]) / scale))

    def _follow_last(self, sample: HandSample, v_user: Vector, speed: float) -> None:
        """Follow the last swipe: extend it to the end of its movement (the return window
        starts there) and detect when the hand has come back and paused."""
        last = self._last
        if last is None or last.returned:
            return
        ts = sample.timestamp_ns
        direction = SWIPE_DIRECTIONS[last.gesture]
        moved = _dot(self._displacement(sample.fingertip, last.start_px, last.scale_px), direction)
        recent = last.end_ns >= ts - int(0.1 * NS_PER_S)
        if recent and _dot(v_user, direction) > STALL_SPEED:
            last.end_ns = ts
            last.length_palms = max(last.length_palms, moved)
        back = moved <= RETURN_ZONE_FRACTION * last.length_palms
        if back and speed < RETURN_SETTLE_SPEED and ts > last.end_ns:
            if last.settled_since_ns is None:
                last.settled_since_ns = ts
            elif _seconds(ts - last.settled_since_ns) >= RETURN_SETTLE_S:
                last.returned = True
        else:
            last.settled_since_ns = None

    def _last_returned(self) -> bool:
        return self._last is None or self._last.returned

    def _is_return(self, gesture: GestureType, start_ns: int) -> bool:
        last = self._last
        if last is None or last.returned or OPPOSITE[last.gesture] is not gesture:
            return False
        return _seconds(start_ns - last.end_ns) <= self.settings.return_window_s

    def update(self, sample: HandSample) -> Step:
        ts = sample.timestamp_ns
        position = sample.fingertip
        v_user = to_user(sample.fingertip_velocity)
        speed = math.hypot(*v_user)
        self._follow_last(sample, v_user, speed)
        if self.phase is GesturePhase.CANDIDATE and self._return and self._last_returned():
            # The hand came back and paused: whatever moves next is a new, deliberate stroke.
            self._reset_stroke()
            self.phase = GesturePhase.IDLE
            self._rest = (position, ts)

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
            gesture, v_axis, v_cross = dominant_direction(v_user)
            if v_axis < STALL_SPEED or self._rest is None:
                self._rest = (position, ts)
            if v_axis < START_SPEED or v_axis < v_cross:
                return Step()
            # Measure the stroke from where the fingertip last rested, not from the frame where
            # its speed crossed the start threshold (part of the stroke is already done then).
            rest_pos, rest_ts = self._rest
            if _seconds(ts - rest_ts) > MAX_REST_AGE_S:
                rest_pos, rest_ts = position, ts
            self._rest = None
            return self._begin(gesture, rest_pos, rest_ts, sample)

        return self._update_candidate(sample, v_user)

    def _update_candidate(self, sample: HandSample, v_user: Vector) -> Step:
        ts = sample.timestamp_ns
        s = self.settings
        gesture = self._gesture
        direction = self._dir
        self._frames += 1
        self._pose_frames += self.pose_ok(sample.pose)
        # The palm looks shorter while the hand is turned edge-on; the largest palm length seen
        # during the stroke is the best estimate of the hand's real size.
        self._scale_px = max(self._scale_px, sample.palm_length_px)
        scale = self._scale_px
        v_axis = _dot(v_user, direction)
        self._peak_px = max(self._peak_px, v_axis * sample.palm_length_px)
        peak = self._peak_px / scale
        d = self._displacement(sample.fingertip, self._start_pos, scale)
        d_axis = _dot(d, direction)
        d_cross = _across(d, direction)
        if d_axis > self._turn[0]:
            self._turn = (d_axis, sample.fingertip, ts)
        elapsed = _seconds(ts - self._start_ns)
        fraction = self._pose_frames / self._frames

        def reject(reason: str) -> Step:
            # A rejected stroke may flow directly into a real one, so the recognizer is
            # immediately idle again.
            self._reset_stroke()
            self.phase = GesturePhase.IDLE
            return Step(rejection=GestureRejection(gesture, reason, ts))

        if d_axis >= s.swipe_min_distance_palms:
            if d_cross * s.direction_ratio > d_axis:
                return reject("diagonal movement")
            if peak < s.swipe_min_speed_palms_s:
                return reject("too slow")
            if fraction < self.pose_fraction or self._pose_frames < 2:
                return reject("pose not held (pointing finger required)")
            if self._return:
                return reject("return movement after previous swipe")
            if gesture not in self.enabled:
                # Still remembered as a swipe, so its own return is suppressed as well.
                self._last = _LastSwipe(gesture, self._start_pos, d_axis, ts, scale)
                return reject("gesture disabled")
            palm = self._displacement(sample.palm, self._palm_start, scale)
            event = GestureEvent(
                gesture=gesture,
                timestamp_ns=ts,
                track_id=sample.track_id,
                handedness=sample.handedness,
                direction=DIRECTION_NAMES[gesture],
                magnitude_palms=round(d_axis, 3),
                peak_speed_palms_s=round(peak, 3),
                duration_s=round(elapsed, 3),
                palm_magnitude_palms=round(_dot(palm, direction), 3),
            )
            self._last = _LastSwipe(gesture, self._start_pos, d_axis, ts, scale)
            self._reset_stroke()
            self._rearm_still_s = s.rearm_still_s
            self.phase = GesturePhase.CONFIRMED
            self._phase_until_ns = ts + int(s.cooldown_s * NS_PER_S)
            return Step(event=event)
        if v_axis <= -START_SPEED or d_axis < -0.2:
            # Reversal: the opposite stroke starts from the turning point, so a wind-up that
            # flows straight into the real movement does not cut the real stroke short.
            _, turn_pos, turn_ts = self._turn
            rejection = reject("direction reversed").rejection
            step = self._begin(OPPOSITE[gesture], turn_pos, turn_ts, sample)
            step.rejection = rejection
            return step
        if elapsed > s.swipe_max_duration_s:
            return reject("too slow")
        if d_cross > max(0.6, d_axis):
            return reject("diagonal movement")
        if v_axis < STALL_SPEED:
            if self._stall_since_ns is None:
                self._stall_since_ns = ts
            elif _seconds(ts - self._stall_since_ns) >= STALL_TIME_S:
                return reject("movement too short")
        else:
            self._stall_since_ns = None
        # A return movement is never shown as an upcoming gesture.
        progress = 0.0 if self._return else max(0.0, min(1.0, d_axis / s.swipe_min_distance_palms))
        return Step(candidate=GestureCandidate(gesture, progress, elapsed))

    def _begin(
        self, gesture: GestureType, start_pos: Vector, start_ns: int, sample: HandSample
    ) -> Step:
        if not self.pose_ok(sample.pose):
            self.phase = GesturePhase.IDLE
            return Step()
        self.phase = GesturePhase.CANDIDATE
        self._gesture = gesture
        self._dir = SWIPE_DIRECTIONS[gesture]
        self._start_ns = start_ns
        self._start_pos = start_pos
        self._palm_start = sample.palm
        self._turn = (0.0, start_pos, start_ns)
        self._frames = 1
        self._pose_frames = 1
        self._scale_px = sample.palm_length_px
        v_axis = _dot(to_user(sample.fingertip_velocity), self._dir)
        self._peak_px = max(0.0, v_axis) * sample.palm_length_px
        self._stall_since_ns = None
        self._return = self._is_return(gesture, sample.timestamp_ns)
        return Step(candidate=GestureCandidate(gesture, 0.0, 0.0))


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


def half_heart(pose: HandPose) -> bool:
    return pose.label is PoseLabel.HALF_HEART


def stop_pose(pose: HandPose) -> bool:
    return pose.is_stop_pose
