"""Per-gesture recognizers with explicit, time-based lifecycles.

Each recognizer receives one :class:`HandSample` per frame for the control hand and returns
at most one confirmed :class:`GestureEvent`. All durations come from frame timestamps, so
behaviour does not depend on the frame rate. Distances and speeds are in hand lengths ("palm
lengths"), measured with a stable hand scale (see *Scale*).

Index swipes (dynamic, one recognizer for all four directions)
    The index fingertip is followed in two dimensions. A stroke starts when the fingertip
    moves faster than ``START_SPEED`` along its dominant axis and is measured from where the
    fingertip last rested. The direction is committed at the start. The stroke is confirmed as
    soon as the displacement along that direction reaches the minimum distance (early
    confirmation: the user does not have to finish an exaggerated movement), provided the
    peak speed, the direction ratio (diagonals are rejected, never guessed), the hand pose
    and the maximum duration are satisfied. A reversal starts the opposite stroke from the
    turning point.

Hand pose (``pose_rule="endpoints"``)
    A stroke made with a pointing hand (pointing when the distance is reached and during at
    least half of the stroke, or held pointing just before it started) is confirmed at once.
    A small downward flick, however, curls the index finger: in the labeled recordings the
    hand reads as a fist in 10-12 of ~12 frames of every downward flick, so requiring the
    pointing pose throughout (version 0.3, ``"fraction"``) made downward flicks nearly
    impossible. Relaxing a pointing finger into a fist moves the fingertip the same way,
    though. A stroke that started from a held pointing pose but has the finger curled when it
    reaches the distance is therefore a *pending flick*: it is confirmed only when the finger
    extends again within ``FLICK_REEXTEND_S`` (the flick's natural recovery) and rejected if
    the finger stays curled. An open hand or a fist moving is never a swipe.

Arming (``arming="observe"``)
    A newly acquired hand cannot swipe until the recognizer has seen it at rest once (one
    frame below ``STALL_SPEED``): a hand raised into view while already pointing cannot
    register its entry as a swipe. Strokes that happen before that, or during the cooldown
    after a gesture, are *followed* but not confirmed, and when they meet the motion criteria
    they are remembered like a confirmed swipe so that their return movement is suppressed
    too. Version 0.3 (``"still"``) instead required 0.2 s of stillness; during continuous
    movement that pause never came, the recognizer only armed at the end of a stroke and
    then confirmed the *return* - the main cause of opposite-direction results on recorded
    horizontal movements.

Return movements
    After a swipe the hand usually moves back, about as fast and as far as the swipe itself,
    often in several parts and overshooting the starting point. Every opposite-direction
    stroke is part of that *return* until the return phase ends: either the fingertip is back
    near the swipe's starting point (within ``RETURN_ZONE_FRACTION`` of the swipe length) and
    has paused there for ``RETURN_SETTLE_S``, or ``return_window_s`` has passed since the
    swipe's movement ended. Ending the return phase after a pause anywhere was measured and
    rejected: between a stroke and the next movement the hand pauses 0.2-0.37 s (median, up
    to 1.4 s) in the recordings, so about half of all natural returns would have become false
    reverse gestures.

Scale (``scale="rest"``)
    The projected palm length changes 3-5 fold while the wrist rotates during horizontal
    movements (27-184 px in one recorded sweep). The scale is the larger of palm length and
    palm width (see ``pose.hand_scale_px``), smoothed while the hand is not stroking and
    frozen for the duration of a stroke.

Tracking dropouts
    Fast movements blur and MediaPipe loses the hand for a few frames. The engine keeps the
    current candidate through gaps of up to ``RecognizerOptions.dropout_s``; the stroke
    continues from where the hand reappears.

Static poses
    A candidate starts when the pose is shown with the hand still; it is confirmed after the
    hold time. Stillness (``static_still="window"``) is the net palm drift over
    ``STATIC_WINDOW_S`` rather than the instantaneous speed: at arm's length a hand is only
    ~40 px long and one pixel of landmark jitter already reads as ~1 palm length per second.
    Short pose dropouts are tolerated. After a confirmation the pose must be released for
    ``RELEASE_S`` before it can trigger again, so holding a pose produces exactly one event.

Every rejection carries a stable ``code`` and, where it applies, the measured and the
required value, so the user can be told exactly why a gesture was not accepted.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from interactive_scrolling.config.settings import GestureSettings
from interactive_scrolling.core.timing import NS_PER_S
from interactive_scrolling.gestures.pose import HandPose, PoseLabel
from interactive_scrolling.gestures.types import (
    GestureCandidate,
    GestureEvent,
    GesturePhase,
    GestureRejection,
    GestureType,
    RejectCode,
)
from interactive_scrolling.vision.landmarks import Handedness

START_SPEED = 0.8
"""Axis speed (palms/s) that starts a swipe candidate."""
STALL_SPEED = 0.4
"""Axis speed (palms/s) below which a started stroke is considered to have stopped, and below
which the hand counts as resting."""
STALL_TIME_S = 0.12
POSE_DROPOUT_S = 0.15
"""Static poses survive pose-classification gaps up to this long (version 0.3 strategy)."""
RELEASE_S = 0.25
"""A static pose must be absent this long before it can trigger again."""
INITIAL_REARM_STILL_S = 0.2
"""``arming="still"`` only (version 0.3): a newly acquired hand had to be nearly still this
long before its first swipe."""
RETURN_ZONE_FRACTION = 0.35
RETURN_SETTLE_S = 0.1
RETURN_SETTLE_SPEED = 0.5
"""The return phase ends after the fingertip has stayed below this speed (palms/s), back near
the swipe's starting point, for ``RETURN_SETTLE_S``."""
MAX_REST_AGE_S = 0.25
"""A stroke is measured from the last resting position only if that rest is this recent."""
POSE_WINDOW_S = 0.25
"""``pose_rule="endpoints"``: the pose shown this long before a stroke starts counts."""
ORIGIN_POSE_FRACTION = 0.6
ORIGIN_POSE_MIN_S = 0.06
"""Pointing before the stroke must be sustained - seen over at least this time span and in
``ORIGIN_POSE_FRACTION`` of the frames (a single stray "pointing" frame during ordinary hand
movement is common in the recordings and caused false swipes). Time based, so it means the
same at 15 and at 30 frames per second."""
ENDPOINT_POSE_FRACTION = 0.5
HAND_MOTION_SHARE = 0.4
"""A stroke whose palm centre travels at least this share of the fingertip distance is a hand
or wrist movement (Brief 005: intended downward hand swipes moved the palm 2.2 hand lengths
median, finger curls 0.05)."""
FLICK_REEXTEND_S = 0.8
"""A curled-finger flick is confirmed only if the finger recovers within this time: it is
pointing again, or the fingertip has started back by ``FLICK_RECOVERY_PALMS`` (earlier than the
pose label, which flips only once the finger is almost straight again)."""
FLICK_RECOVERY_PALMS = 0.25
SCALE_TIME_CONSTANT_S = 0.25
END_WAIT_MAX_S = 0.3
"""``confirm="end"``: a qualified stroke is confirmed when it stops, at the latest this long
after it met all criteria."""
MAX_TRAVEL_PALMS = 4.5
BOTTOM_ZONE = 0.85
"""A downward stroke with the hand below this fraction of the image height waits until the hand
stops inside the picture (Brief 005: a hand dropped out of view had its wrist at 0.90, real
downward swipes at 0.62-0.74)."""
"""``confirm="end"``: a stroke that travels further than this before stopping is a large arm
movement (for example lowering the hand out of view), not a swipe."""
STATIC_WINDOW_S = 0.3
STATIC_MAX_DRIFT_PALMS = 0.25
"""``static_still="window"``: the palm may drift at most this far within ``STATIC_WINDOW_S``."""

Vector = tuple[float, float]


@dataclass(frozen=True, slots=True)
class RecognizerOptions:
    """Recognition strategies compared in the Brief 004 benchmark
    (docs/benchmarks/GESTURE_BENCHMARK_004.md). The defaults are the selected strategies;
    :data:`V03_OPTIONS` reproduces version 0.3 for comparison."""

    arming: str = "observe"
    pose_rule: str = "endpoints"
    scale: str = "rest"
    dropout_s: float = 0.2
    static_still: str = "window"
    static_while_stabilizing: bool = False
    """Static poses may start their hold while a new hand is still stabilizing (evaluated in
    Brief 004: no recall gain on the recordings, so not enabled)."""
    hand_motion_now: bool = True
    """Confirm a stroke from a held pointing pose at once when the palm moved with it, even if
    the finger reads as curled at the threshold (Brief 005)."""
    confirm: str = "early"
    """``"early"``: confirm as soon as all criteria are met; ``"end"``: wait until the stroke
    stops inside the view (rejects hands leaving the picture, costs latency)."""

    def __post_init__(self) -> None:
        if self.confirm not in ("early", "end"):
            raise ValueError(f"unknown confirmation strategy {self.confirm!r}")
        if self.arming not in ("observe", "still"):
            raise ValueError(f"unknown arming strategy {self.arming!r}")
        if self.pose_rule not in ("endpoints", "fraction"):
            raise ValueError(f"unknown pose rule {self.pose_rule!r}")
        if self.scale not in ("rest", "stroke_max"):
            raise ValueError(f"unknown scale strategy {self.scale!r}")
        if self.static_still not in ("window", "velocity"):
            raise ValueError(f"unknown stillness strategy {self.static_still!r}")
        if not 0.0 <= self.dropout_s <= 0.5:
            raise ValueError("dropout_s must be within [0, 0.5]")


V03_OPTIONS = RecognizerOptions(
    arming="still",
    pose_rule="fraction",
    scale="stroke_max",
    dropout_s=0.0,
    static_still="velocity",
    static_while_stabilizing=False,
)


@dataclass(frozen=True, slots=True)
class DetectorConfig:
    """One way of making a directional swipe (Brief 005, motion-first).

    All detectors share the stroke segmentation, direction scoring and return handling of
    :class:`DirectionalSwipeRecognizer`; they differ in the motion reference and in how the
    activating pose has to be shown."""

    name: str
    reference: str
    """``"fingertip"`` (index fingertip) or ``"palm"`` (mean of wrist and the four knuckles:
    whole-hand or wrist movement; opening or closing the hand hardly moves it)."""
    origin_window_s: float
    origin_fraction: float
    origin_min_s: float
    """The activating pose must be seen in ``origin_fraction`` of the frames of the
    ``origin_window_s`` before the stroke, spanning at least ``origin_min_s``."""
    flicks: bool
    """Finger flicks (finger curled at the threshold) wait for the finger to recover."""
    require_origin: bool
    """The stroke must start from the held pose (an intentional activation cue)."""
    origin_still_s: float = 0.0
    """The reference must have been still (net drift <= ``ORIGIN_STILL_DRIFT``) for this long
    right before the stroke: a fist that is *presented* and then moved, not a closed hand that
    is repositioned in the middle of other movement."""


FINGER = DetectorConfig("finger", "fingertip", 0.25, 0.6, 0.06, flicks=True, require_origin=False)
FIST = DetectorConfig(
    "fist", "palm", 0.45, 0.7, 0.25, flicks=False, require_origin=True, origin_still_s=0.25
)
PALM = DetectorConfig(
    "palm", "palm", 0.45, 0.7, 0.25, flicks=False, require_origin=True, origin_still_s=0.25
)
ORIGIN_STILL_DRIFT = 0.25


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
    scale_px: float = 0.0
    """Rotation-tolerant hand scale of this frame (``pose.hand_scale_px``); 0 = use the palm
    length."""
    lowest_y: float = 0.0
    """Lowest landmark of the hand, normalized image height (1.0 = bottom edge)."""

    @property
    def fingertip_velocity_px(self) -> Vector:
        return (
            self.fingertip_velocity[0] * self.palm_length_px,
            self.fingertip_velocity[1] * self.palm_length_px,
        )

    @property
    def palm_velocity_px(self) -> Vector:
        return (
            self.palm_velocity[0] * self.palm_length_px,
            self.palm_velocity[1] * self.palm_length_px,
        )

    @property
    def frame_scale_px(self) -> float:
        return self.scale_px if self.scale_px > 0 else self.palm_length_px


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
    """Image position where the stroke started."""
    length_palms: float
    """Stroke length along its direction, followed to the end of the movement."""
    end_ns: int
    """When the hand stopped moving in the swipe direction."""
    scale_px: float
    settled_since_ns: int | None = None
    returned: bool = False
    """The hand came back and paused: the return phase is over."""
    confirmed: bool = True
    """False for a stroke that met the criteria but was not allowed to confirm (cooldown,
    not yet armed, disabled direction); its return is suppressed all the same."""


@dataclass(slots=True)
class _Stroke:
    gesture: GestureType
    direction: Vector
    start_ns: int
    start_pos: Vector
    palm_start: Vector
    scale_px: float
    blocked: str
    """Why the stroke may not confirm (a ``RejectCode``), or empty if it may."""
    origin_pose: bool
    is_return: bool
    peak_px: float = 0.0
    frames: int = 1
    pose_frames: int = 0
    stall_since_ns: int | None = None
    turn: tuple[float, Vector, int] = (0.0, (0.0, 0.0), 0)
    """(furthest displacement along the direction, its position, its timestamp)."""
    observed: bool = False
    """Already remembered as a (blocked) swipe for return suppression."""
    qualified_ns: int = 0
    """``confirm="end"``: when the stroke met every criterion (0 = not yet)."""
    onset_seen: bool = True
    """The recognizer saw the hand before this stroke started (it was not already moving when
    it was detected)."""


@dataclass(slots=True)
class _PendingFlick:
    stroke: _Stroke
    length_palms: float
    peak_palms_s: float
    elapsed_s: float
    qualified_ns: int
    palm: Vector
    track_id: int


class DirectionalSwipeRecognizer:
    """Index-finger swipes in four directions, from the user's perspective."""

    def __init__(
        self,
        settings: GestureSettings,
        pose_ok: Callable[[HandPose], bool],
        pose_fraction: float = 0.6,
        options: RecognizerOptions | None = None,
        detector: DetectorConfig = FINGER,
    ) -> None:
        self.settings = settings
        self.pose_ok = pose_ok
        self.pose_fraction = pose_fraction
        self.options = options or RecognizerOptions()
        self.detector = detector
        self.enabled: frozenset[GestureType] = frozenset(SWIPE_DIRECTIONS)
        """Directions that may confirm. Disabled directions are still followed (so their
        movement cannot be misread as another direction) but are rejected."""
        self.phase = GesturePhase.REARMING
        self._cooldown_until_ns = 0
        self._last: _LastSwipe | None = None
        self.reset()

    @property
    def gestures(self) -> tuple[GestureType, ...]:
        return tuple(SWIPE_DIRECTIONS)

    @property
    def last_swipe(self) -> _LastSwipe | None:
        return self._last

    def reset(self, rearm: bool = True) -> None:
        """Forget any stroke (tracking loss or a new control hand)."""
        self._stroke: _Stroke | None = None
        self._rest: tuple[Vector, int] | None = None
        self._armed = not rearm
        self._seen_slow = not rearm
        """A sample slower than ``START_SPEED`` was seen since the reset, so the onset of the
        current stroke was observed (it did not begin before the hand was detected)."""
        self._still_since_ns: int | None = None
        self._last = None
        self._scale: float | None = None
        self._scale_ns: int | None = None
        self._pose_history: deque[tuple[int, bool]] = deque()
        self._flick: _PendingFlick | None = None
        self._positions: deque[tuple[int, Vector]] = deque()
        self.phase = GesturePhase.REARMING if rearm else GesturePhase.IDLE

    def block_until(self, timestamp_ns: int) -> None:
        """Global cooldown imposed by another recognizer's confirmation."""
        self._stroke = None
        self._flick = None
        self._cooldown_until_ns = max(self._cooldown_until_ns, timestamp_ns)
        self.phase = GesturePhase.COOLDOWN

    # ------------------------------------------------------------------ helpers

    def _update_scale(self, sample: HandSample) -> None:
        frame_scale = sample.frame_scale_px
        if self.options.scale == "stroke_max":
            self._scale = sample.palm_length_px
            return
        if self._scale is None or self._scale_ns is None:
            self._scale = frame_scale
        else:
            dt = _seconds(sample.timestamp_ns - self._scale_ns)
            alpha = 1.0 - math.exp(-max(dt, 0.0) / SCALE_TIME_CONSTANT_S)
            self._scale += alpha * (frame_scale - self._scale)
        self._scale_ns = sample.timestamp_ns

    def _current_scale(self, sample: HandSample) -> float:
        if self._stroke is not None:
            return self._stroke.scale_px
        return self._scale if self._scale else sample.frame_scale_px

    def _pos(self, sample: HandSample) -> Vector:
        return sample.palm if self.detector.reference == "palm" else sample.fingertip

    def _vel_px(self, sample: HandSample) -> Vector:
        if self.detector.reference == "palm":
            return sample.palm_velocity_px
        return sample.fingertip_velocity_px

    def adopt(self, gesture: GestureType, start_ns: int, ts: int) -> None:
        """A swipe confirmed by another detector of the same hand: remember it in this
        detector's own reference, so its return is suppressed here as well."""
        if gesture not in SWIPE_DIRECTIONS or not self._positions or self._scale is None:
            return
        start = min(self._positions, key=lambda item: abs(item[0] - start_ns))[1]
        now = self._positions[-1][1]
        length = _dot(self._displacement(now, start, self._scale), SWIPE_DIRECTIONS[gesture])
        self._last = _LastSwipe(gesture, start, max(length, 0.0), ts, self._scale)
        self._stroke = None
        self._flick = None

    def _was_still(self, until_ns: int, sample: HandSample) -> bool:
        need = self.detector.origin_still_s
        if need <= 0:
            return True
        since = until_ns - int(need * NS_PER_S)
        window = [pos for t, pos in self._positions if since <= t <= until_ns]
        if len(window) < 2 or self._positions[0][0] > since:
            return False
        xs = [p[0] for p in window]
        ys = [p[1] for p in window]
        scale = self._scale or sample.frame_scale_px
        return math.hypot(max(xs) - min(xs), max(ys) - min(ys)) / scale <= ORIGIN_STILL_DRIFT

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
        moved = _dot(self._displacement(self._pos(sample), last.start_px, last.scale_px), direction)
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

    def _is_return(self, gesture: GestureType, start_ns: int) -> bool:
        last = self._last
        if last is None or last.returned or OPPOSITE[last.gesture] is not gesture:
            return False
        return _seconds(start_ns - last.end_ns) <= self.settings.return_window_s

    def _recent_pose(self, ts: int) -> bool:
        d = self.detector
        cutoff = ts - int(d.origin_window_s * NS_PER_S)
        window = [(t, ok) for t, ok in self._pose_history if t >= cutoff]
        hits = [t for t, ok in window if ok]
        if len(hits) < 2 or len(hits) < d.origin_fraction * len(window):
            return False
        return _seconds(hits[-1] - hits[0]) >= d.origin_min_s

    def _pose_accepted(self, stroke: _Stroke, pose_now: bool, palm_share: float = 0.0) -> str:
        """ "now" (confirm), "flick" (wait for the finger to extend again) or "" (reject).

        ``palm_share``: palm-centre travel along the direction / fingertip travel."""
        fraction = stroke.pose_frames / stroke.frames
        if self.options.pose_rule == "fraction":
            return "now" if fraction >= self.pose_fraction and stroke.pose_frames >= 2 else ""
        if self.detector.require_origin:
            # Fist / palm: activated by the held pose, which must stay mostly visible.
            held = pose_now or fraction >= ENDPOINT_POSE_FRACTION
            return "now" if stroke.origin_pose and held else ""
        if pose_now and (stroke.origin_pose or fraction >= ENDPOINT_POSE_FRACTION):
            return "now"
        if stroke.origin_pose and self.detector.flicks:
            if self.options.hand_motion_now and palm_share >= HAND_MOTION_SHARE:
                # The palm moved with the fingertip: a hand or wrist movement, not a finger
                # curl (fast motion blurs the finger, which then reads as curled). Relaxing the
                # finger moves only the fingertip, so it still waits for the recovery.
                return "now"
            return "flick"
        return ""

    def _arm(self, sample: HandSample, speed: float, axis_speed: float) -> None:
        """Arming of a newly acquired hand (see the module documentation)."""
        if axis_speed < START_SPEED:
            self._seen_slow = True
        if self._armed:
            return
        ts = sample.timestamp_ns
        if self.options.arming == "observe":
            if axis_speed < STALL_SPEED:
                self._armed = True
            return
        if speed <= self.settings.rearm_max_speed_palms_s:
            if self._still_since_ns is None:
                self._still_since_ns = ts
            if _seconds(ts - self._still_since_ns) >= INITIAL_REARM_STILL_S:
                self._armed = True
        else:
            self._still_since_ns = None

    def _blocked_code(self, ts: int) -> str:
        if not self._armed:
            return RejectCode.NOT_ARMED
        if ts < self._cooldown_until_ns:
            return RejectCode.COOLDOWN
        return ""

    def _update_phase(self, ts: int) -> None:
        if self._flick is not None or (self._stroke is not None and not self._stroke.blocked):
            self.phase = GesturePhase.CANDIDATE
        elif ts < self._cooldown_until_ns:
            self.phase = GesturePhase.COOLDOWN
        elif not self._armed:
            self.phase = GesturePhase.REARMING
        else:
            self.phase = GesturePhase.IDLE

    # ------------------------------------------------------------------ update

    def update(self, sample: HandSample) -> Step:
        ts = sample.timestamp_ns
        position = self._pos(sample)
        self._positions.append((ts, position))
        while self._positions and self._positions[0][0] < ts - int(2.0 * NS_PER_S):
            self._positions.popleft()
        pose_now = self.pose_ok(sample.pose)
        self._pose_history.append((ts, pose_now))
        cutoff = ts - int(2 * max(POSE_WINDOW_S, self.detector.origin_window_s) * NS_PER_S)
        while self._pose_history and self._pose_history[0][0] < cutoff:
            self._pose_history.popleft()
        if self._stroke is None:
            self._update_scale(sample)
        scale = self._current_scale(sample)
        vx, vy = self._vel_px(sample)
        v_user = to_user((vx / scale, vy / scale))
        speed = math.hypot(*v_user)
        self._follow_last(sample, v_user, speed)
        flick = self._resolve_flick(sample, pose_now)
        if flick is not None:
            self._update_phase(ts)
            return flick

        stroke = self._stroke
        if stroke is not None and stroke.is_return and (self._last is None or self._last.returned):
            # The hand came back and paused: whatever moves next is a new, deliberate stroke.
            self._stroke = None
            self._rest = (position, ts)
            stroke = None

        gesture, v_axis, v_cross = dominant_direction(v_user)
        self._arm(sample, speed, v_axis)
        if self.options.arming == "still" and not self._armed:
            # Version 0.3: nothing is followed before the hand has been still.
            self._rest = None
            self._update_phase(ts)
            return Step()

        if stroke is None:
            if v_axis < STALL_SPEED or self._rest is None:
                self._rest = (position, ts)
            if v_axis < START_SPEED or v_axis < v_cross:
                self._update_phase(ts)
                return Step()
            # Measure the stroke from where the fingertip last rested, not from the frame where
            # its speed crossed the start threshold (part of the stroke is already done then).
            rest_pos, rest_ts = self._rest
            if _seconds(ts - rest_ts) > MAX_REST_AGE_S:
                rest_pos, rest_ts = position, ts
            self._rest = None
            step = self._begin(gesture, rest_pos, rest_ts, sample, pose_now)
            self._update_phase(ts)
            return step

        step = self._update_stroke(stroke, sample, v_user, pose_now)
        self._update_phase(ts)
        return step

    def _remember(self, stroke: _Stroke, length: float, ts: int, confirmed: bool) -> None:
        self._last = _LastSwipe(
            stroke.gesture, stroke.start_pos, length, ts, stroke.scale_px, confirmed=confirmed
        )

    def _update_stroke(
        self, stroke: _Stroke, sample: HandSample, v_user: Vector, pose_now: bool
    ) -> Step:
        ts = sample.timestamp_ns
        s = self.settings
        gesture = stroke.gesture
        direction = stroke.direction
        stroke.frames += 1
        stroke.pose_frames += pose_now
        if self.options.scale == "stroke_max":
            # Version 0.3: the largest palm length seen during the stroke.
            stroke.scale_px = max(stroke.scale_px, sample.palm_length_px)
        scale = stroke.scale_px
        v_axis = _dot(v_user, direction)
        stroke.peak_px = max(stroke.peak_px, v_axis * scale)
        peak = stroke.peak_px / scale
        d = self._displacement(self._pos(sample), stroke.start_pos, scale)
        d_axis = _dot(d, direction)
        d_cross = _across(d, direction)
        if d_axis > stroke.turn[0]:
            stroke.turn = (d_axis, self._pos(sample), ts)
        elapsed = _seconds(ts - stroke.start_ns)
        distance = swipe_distance(s, gesture, self.detector.name)

        def reject(
            code: str,
            reason: str,
            measured: float | None = None,
            required: float | None = None,
            unit: str = "",
        ) -> Step:
            # A rejected stroke may flow directly into a real one, so the recognizer is
            # immediately idle again.
            self._stroke = None
            return Step(
                rejection=GestureRejection(
                    gesture, reason, ts, code, _round(measured), _round(required), unit
                )
            )

        if d_axis >= distance and not stroke.observed:
            if d_cross * s.direction_ratio > d_axis:
                angle = math.degrees(math.atan2(d_cross, d_axis))
                limit = math.degrees(math.atan2(1.0, s.direction_ratio))
                return reject(RejectCode.DIAGONAL, "diagonal movement", angle, limit, "deg")
            if peak < s.swipe_min_speed_palms_s:
                return reject(
                    RejectCode.TOO_SLOW, "too slow", peak, s.swipe_min_speed_palms_s, "palms/s"
                )
            palm_share = 0.0
            if d_axis > 0:
                palm_move = self._displacement(sample.palm, stroke.palm_start, scale)
                palm_share = _dot(palm_move, direction) / d_axis
            pose_verdict = self._pose_accepted(stroke, pose_now, palm_share)
            if not pose_verdict:
                fraction = stroke.pose_frames / stroke.frames
                return reject(
                    RejectCode.POSE,
                    "pose not held (pointing finger required)",
                    fraction,
                    self.pose_fraction
                    if self.options.pose_rule == "fraction"
                    else ENDPOINT_POSE_FRACTION,
                    "fraction",
                )
            if stroke.is_return:
                return reject(RejectCode.RETURN, "return movement after previous swipe")
            if stroke.blocked or gesture not in self.enabled:
                # Followed but not allowed to confirm: remembered so that its own return is
                # suppressed as well, and followed to its end. A movement that was already
                # under way when the hand was detected (raising the hand into view) is not a
                # swipe at all and is not remembered: the next deliberate stroke may go in
                # the opposite direction.
                if stroke.onset_seen:
                    self._remember(stroke, d_axis, ts, confirmed=False)
                stroke.observed = True
                if gesture not in self.enabled:
                    return Step(
                        rejection=GestureRejection(
                            gesture, "gesture disabled", ts, RejectCode.DISABLED
                        )
                    )
                if stroke.blocked == RejectCode.COOLDOWN:
                    remaining = _seconds(self._cooldown_until_ns - ts)
                    return Step(
                        rejection=GestureRejection(
                            gesture,
                            "too soon after the previous gesture",
                            ts,
                            RejectCode.COOLDOWN,
                            _round(remaining),
                            None,
                            "s",
                        )
                    )
                return Step(
                    rejection=GestureRejection(
                        gesture,
                        "hand was already moving when it was detected",
                        ts,
                        RejectCode.NOT_ARMED,
                    )
                )
            if pose_verdict == "flick":
                # Remembered so the finger's re-extension is not read as a swipe up.
                self._remember(stroke, d_axis, ts, confirmed=False)
                stroke.observed = True
                self._flick = _PendingFlick(
                    stroke, d_axis, peak, elapsed, ts, sample.palm, sample.track_id
                )
                return Step(candidate=GestureCandidate(gesture, 1.0, elapsed))
            leaving = gesture is GestureType.INDEX_SWIPE_DOWN and sample.lowest_y > BOTTOM_ZONE
            if leaving and self.options.confirm != "end":
                # Near the bottom of the picture a downward stroke may be the hand being lowered
                # out of view (a recorded false swipe): confirm only once it stops in view.
                if not stroke.qualified_ns:
                    stroke.qualified_ns = ts
                if v_axis >= STALL_SPEED:
                    if _seconds(ts - stroke.qualified_ns) >= END_WAIT_MAX_S:
                        return reject(
                            RejectCode.TOO_FAR,
                            "hand moving out of the picture",
                            sample.lowest_y,
                            BOTTOM_ZONE,
                            "image height",
                        )
                    return Step(candidate=GestureCandidate(gesture, 1.0, elapsed))
            if self.options.confirm == "end":
                if not stroke.qualified_ns:
                    stroke.qualified_ns = ts
                if d_axis > MAX_TRAVEL_PALMS:
                    return reject(
                        RejectCode.TOO_FAR,
                        "movement continued too far (not a swipe)",
                        d_axis,
                        MAX_TRAVEL_PALMS,
                        "palms",
                    )
                waited = _seconds(ts - stroke.qualified_ns)
                if v_axis >= STALL_SPEED and waited < END_WAIT_MAX_S:
                    return Step(candidate=GestureCandidate(gesture, 1.0, elapsed))
            return self._confirm(stroke, sample, d_axis, peak, elapsed)
        if v_axis <= -START_SPEED or d_axis < -0.2:
            # Reversal: the opposite stroke starts from the turning point, so a wind-up that
            # flows straight into the real movement does not cut the real stroke short.
            _, turn_pos, turn_ts = stroke.turn
            rejection = None
            if not stroke.observed and not stroke.is_return:
                rejection = reject(
                    RejectCode.TOO_SHORT,
                    "direction reversed",
                    max(0.0, stroke.turn[0]),
                    distance,
                    "palms",
                ).rejection
            self._stroke = None
            step = self._begin(OPPOSITE[gesture], turn_pos, turn_ts, sample, pose_now)
            step.rejection = rejection
            return step
        if stroke.observed:
            if v_axis < STALL_SPEED:
                self._stroke = None
            return Step()
        if elapsed > s.swipe_max_duration_s:
            return reject(RejectCode.TOO_LONG, "too slow", elapsed, s.swipe_max_duration_s, "s")
        if d_cross > max(0.6, d_axis):
            angle = math.degrees(math.atan2(d_cross, max(d_axis, 1e-6)))
            limit = math.degrees(math.atan2(1.0, s.direction_ratio))
            return reject(RejectCode.DIAGONAL, "diagonal movement", angle, limit, "deg")
        if v_axis < STALL_SPEED:
            if stroke.stall_since_ns is None:
                stroke.stall_since_ns = ts
            elif _seconds(ts - stroke.stall_since_ns) >= STALL_TIME_S:
                return reject(
                    RejectCode.TOO_SHORT,
                    "movement too short",
                    max(0.0, d_axis),
                    distance,
                    "palms",
                )
        else:
            stroke.stall_since_ns = None
        if stroke.is_return or stroke.blocked:
            # A return movement or a blocked stroke is never shown as an upcoming gesture.
            return Step()
        progress = max(0.0, min(1.0, d_axis / distance))
        return Step(candidate=GestureCandidate(gesture, progress, elapsed))

    def _resolve_flick(self, sample: HandSample, pose_now: bool) -> Step | None:
        """Confirm a pending flick once the finger extends again, reject it if it does not."""
        flick = self._flick
        if flick is None:
            return None
        ts = sample.timestamp_ns
        waited = _seconds(ts - flick.qualified_ns)
        stroke = flick.stroke
        _, turn_pos, _ = stroke.turn
        back = -_dot(
            self._displacement(self._pos(sample), turn_pos, stroke.scale_px), stroke.direction
        )
        if (pose_now or back >= FLICK_RECOVERY_PALMS) and ts > flick.qualified_ns:
            self._flick = None
            stroke = flick.stroke
            stroke.qualified_ns = flick.qualified_ns
            if self._last is not None and self._last.gesture is stroke.gesture:
                self._last.confirmed = True
            event = GestureEvent(
                gesture=stroke.gesture,
                timestamp_ns=ts,
                track_id=flick.track_id,
                handedness=sample.handedness,
                direction=DIRECTION_NAMES[stroke.gesture],
                magnitude_palms=round(flick.length_palms, 3),
                peak_speed_palms_s=round(flick.peak_palms_s, 3),
                duration_s=round(flick.elapsed_s, 3),
                palm_magnitude_palms=round(
                    _dot(
                        self._displacement(flick.palm, stroke.palm_start, stroke.scale_px),
                        stroke.direction,
                    ),
                    3,
                ),
                decision_delay_s=round(waited, 3),
                detector=self.detector.name,
            )
            self._cooldown_until_ns = ts + int(self.settings.cooldown_s * NS_PER_S)
            self.phase = GesturePhase.CONFIRMED
            return Step(event=event)
        if waited > FLICK_REEXTEND_S:
            self._flick = None
            return Step(
                rejection=GestureRejection(
                    flick.stroke.gesture,
                    "finger stayed curled (relaxing the hand is not a swipe)",
                    ts,
                    RejectCode.POSE,
                    round(waited, 3),
                    FLICK_REEXTEND_S,
                    "s",
                )
            )
        return None

    def _confirm(
        self, stroke: _Stroke, sample: HandSample, d_axis: float, peak: float, elapsed: float
    ) -> Step:
        ts = sample.timestamp_ns
        direction = stroke.direction
        palm = self._displacement(sample.palm, stroke.palm_start, stroke.scale_px)
        event = GestureEvent(
            gesture=stroke.gesture,
            timestamp_ns=ts,
            track_id=sample.track_id,
            handedness=sample.handedness,
            direction=DIRECTION_NAMES[stroke.gesture],
            magnitude_palms=round(d_axis, 3),
            peak_speed_palms_s=round(peak, 3),
            duration_s=round(elapsed, 3),
            palm_magnitude_palms=round(_dot(palm, direction), 3),
            decision_delay_s=round(_seconds(ts - stroke.qualified_ns), 3)
            if stroke.qualified_ns
            else 0.0,
            detector=self.detector.name,
        )
        self._remember(stroke, d_axis, ts, confirmed=True)
        self._stroke = None
        self._cooldown_until_ns = ts + int(self.settings.cooldown_s * NS_PER_S)
        self.phase = GesturePhase.CONFIRMED
        return Step(event=event)

    def _begin(
        self,
        gesture: GestureType,
        start_pos: Vector,
        start_ns: int,
        sample: HandSample,
        pose_now: bool,
    ) -> Step:
        ts = sample.timestamp_ns
        if self.options.pose_rule == "fraction" and not pose_now:
            return Step()
        if self.detector.require_origin and not (
            self._recent_pose(ts) and self._was_still(start_ns, sample)
        ):
            # A fist/palm detector only follows movements that start from its held, still
            # pose; anything else belongs to another detector (and is not explained here).
            return Step()
        scale = self._current_scale(sample)
        if self.options.scale == "stroke_max":
            scale = sample.palm_length_px
        stroke = _Stroke(
            gesture=gesture,
            direction=SWIPE_DIRECTIONS[gesture],
            start_ns=start_ns,
            start_pos=start_pos,
            palm_start=sample.palm,
            scale_px=scale,
            blocked=self._blocked_code(ts),
            origin_pose=self._recent_pose(ts),
            is_return=self._is_return(gesture, ts),
            pose_frames=int(pose_now),
            turn=(0.0, start_pos, start_ns),
            onset_seen=self._seen_slow,
        )
        vx, vy = self._vel_px(sample)
        v_axis = _dot(to_user((vx / scale, vy / scale)), stroke.direction)
        stroke.peak_px = max(0.0, v_axis) * scale
        self._stroke = stroke
        if stroke.is_return or stroke.blocked:
            return Step()
        return Step(candidate=GestureCandidate(gesture, 0.0, 0.0))


def swipe_distance(
    settings: GestureSettings, gesture: GestureType, detector: str = "finger"
) -> float:
    """Required travel for ``gesture``: a per-direction value if set, then the left/right
    value for horizontal swipes, then the shared one. Fist and palm detectors measure the palm
    centre and use their own distance."""
    if detector != "finger":
        return settings.fist_swipe_distance_palms
    override = {
        GestureType.INDEX_SWIPE_UP: settings.swipe_up_distance_palms,
        GestureType.INDEX_SWIPE_DOWN: settings.swipe_down_distance_palms,
        GestureType.INDEX_SWIPE_LEFT: settings.swipe_left_distance_palms,
        GestureType.INDEX_SWIPE_RIGHT: settings.swipe_right_distance_palms,
    }[gesture]
    if override > 0:
        return override
    horizontal = gesture in (GestureType.INDEX_SWIPE_LEFT, GestureType.INDEX_SWIPE_RIGHT)
    if horizontal and settings.swipe_horizontal_distance_palms > 0:
        return settings.swipe_horizontal_distance_palms
    return settings.swipe_min_distance_palms


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


@dataclass(slots=True)
class _Drift:
    samples: deque[tuple[int, Vector]] = field(default_factory=deque)

    def add(self, ts: int, position: Vector) -> None:
        self.samples.append((ts, position))
        cutoff = ts - int(STATIC_WINDOW_S * NS_PER_S)
        while len(self.samples) > 1 and self.samples[0][0] < cutoff:
            self.samples.popleft()

    def drift_px(self) -> float:
        if len(self.samples) < 2:
            return 0.0
        xs = [p[0] for _, p in self.samples]
        ys = [p[1] for _, p in self.samples]
        return math.hypot(max(xs) - min(xs), max(ys) - min(ys))


class StaticPoseRecognizer:
    """A pose that must be held still for a minimum time; one event per presentation."""

    def __init__(
        self,
        gesture: GestureType,
        pose_ok: Callable[[HandPose], bool],
        hold_s: Callable[[], float],
        settings: GestureSettings,
        options: RecognizerOptions | None = None,
        describe: Callable[[HandPose], tuple[str, ...]] | None = None,
    ) -> None:
        self.gesture = gesture
        self.pose_ok = pose_ok
        self.hold_s = hold_s
        self.settings = settings
        self.options = options or RecognizerOptions()
        self.describe = describe
        """Optional: the unmet conditions of a pose that is close but not recognized."""
        self.phase = GesturePhase.IDLE
        self._start_ns = 0
        self._last_pose_ns: int | None = None
        self._absent_since_ns: int | None = None
        self._phase_until_ns = 0
        self._drift = _Drift()

    @property
    def gestures(self) -> tuple[GestureType]:
        return (self.gesture,)

    def reset(self, rearm: bool = False) -> None:
        self.phase = GesturePhase.REARMING if rearm else GesturePhase.IDLE
        self._last_pose_ns = None
        self._absent_since_ns = None
        self._drift = _Drift()

    def block_until(self, timestamp_ns: int) -> None:
        if self.phase is GesturePhase.CANDIDATE:
            self.phase = GesturePhase.IDLE
        if self.phase is GesturePhase.IDLE:
            self.phase = GesturePhase.COOLDOWN
        self._phase_until_ns = max(self._phase_until_ns, timestamp_ns)

    def cancel(
        self, timestamp_ns: int, reason: str, code: str = RejectCode.CANCELLED, **values
    ) -> Step:
        if self.phase is not GesturePhase.CANDIDATE:
            return Step()
        self.phase = GesturePhase.IDLE
        return Step(rejection=GestureRejection(self.gesture, reason, timestamp_ns, code, **values))

    def _still(self, sample: HandSample) -> tuple[bool, float]:
        """(still, drift in palms over the window or speed in palms/s)."""
        if self.options.static_still == "velocity":
            speed = math.hypot(*sample.palm_velocity)
            return speed <= self.settings.static_max_speed_palms_s, speed
        self._drift.add(sample.timestamp_ns, sample.palm)
        drift = self._drift.drift_px() / sample.frame_scale_px
        return drift <= STATIC_MAX_DRIFT_PALMS, drift

    def update(self, sample: HandSample) -> Step:
        ts = sample.timestamp_ns
        present = self.pose_ok(sample.pose)
        still, motion = self._still(sample)
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
        held = _seconds(ts - self._start_ns)
        required = self.hold_s()
        if not still:
            limit = (
                self.settings.static_max_speed_palms_s
                if self.options.static_still == "velocity"
                else STATIC_MAX_DRIFT_PALMS
            )
            unit = "palms/s" if self.options.static_still == "velocity" else "palms"
            return self.cancel(
                ts,
                "hand moving",
                RejectCode.HAND_MOVING,
                measured=_round(motion),
                required=limit,
                unit=unit,
            )
        if not present:
            gap = _seconds(ts - (self._last_pose_ns or ts))
            dropout = POSE_DROPOUT_S
            if self.options.static_still == "window":
                dropout = max(POSE_DROPOUT_S, self.options.dropout_s)
            if gap > dropout:
                details = self.describe(sample.pose) if self.describe else ()
                return self.cancel(
                    ts,
                    "pose released before hold time",
                    RejectCode.RELEASED,
                    measured=_round(held),
                    required=required,
                    unit="s",
                    details=details,
                )
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


def fist(pose: HandPose) -> bool:
    """A closed hand (pose label FIST: four fingers curled, not a thumbs-up or half-heart)."""
    return pose.label is PoseLabel.FIST


def open_hand(pose: HandPose) -> bool:
    return pose.label is PoseLabel.OPEN_PALM
