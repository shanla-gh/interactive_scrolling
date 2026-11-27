"""Gesture vocabulary, lifecycle phases and the data produced by the gesture engine."""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field

from interactive_scrolling.vision.landmarks import Handedness


class GestureType(enum.Enum):
    """The recognized gestures (Engineering Brief 003).

    The four index swipes are one gesture family: a pointing hand moving in one direction.
    ``left`` and ``right`` are the user's own left and right.
    """

    INDEX_SWIPE_DOWN = "index_swipe_down"
    INDEX_SWIPE_UP = "index_swipe_up"
    INDEX_SWIPE_LEFT = "index_swipe_left"
    INDEX_SWIPE_RIGHT = "index_swipe_right"
    HALF_HEART = "half_heart"
    STOP_GESTURE = "stop_gesture"

    @property
    def label(self) -> str:
        return _LABELS[self]

    @property
    def is_dynamic(self) -> bool:
        return self in SWIPES

    @classmethod
    def from_stored(cls, value: str) -> GestureType:
        """Parse a stored gesture name, including names written by earlier versions."""
        return cls(LEGACY_GESTURE_NAMES.get(value, value))


_LABELS = {
    GestureType.INDEX_SWIPE_DOWN: "SWIPE DOWN",
    GestureType.INDEX_SWIPE_UP: "SWIPE UP",
    GestureType.INDEX_SWIPE_LEFT: "SWIPE LEFT",
    GestureType.INDEX_SWIPE_RIGHT: "SWIPE RIGHT",
    GestureType.HALF_HEART: "HALF HEART",
    GestureType.STOP_GESTURE: "STOP",
}
SWIPES = (
    GestureType.INDEX_SWIPE_DOWN,
    GestureType.INDEX_SWIPE_UP,
    GestureType.INDEX_SWIPE_LEFT,
    GestureType.INDEX_SWIPE_RIGHT,
)

LEGACY_GESTURE_NAMES = {
    # Version 0.2 (Brief 002). The finger swipes were already pointing-hand swipes, so they map
    # to the same gesture. The open-hand sweeps and the thumbs up were different gestures; their
    # *roles* (horizontal navigation, like) are taken over by the new gestures.
    "finger_swipe_down": "index_swipe_down",
    "finger_swipe_up": "index_swipe_up",
    "hand_swipe_left": "index_swipe_left",
    "hand_swipe_right": "index_swipe_right",
    "thumbs_up": "half_heart",
}
LEGACY_GESTURE_LABELS = {
    "finger_swipe_down": "SWIPE DOWN",
    "finger_swipe_up": "SWIPE UP",
    "hand_swipe_left": "HAND SWEEP LEFT (v0.2)",
    "hand_swipe_right": "HAND SWEEP RIGHT (v0.2)",
    "thumbs_up": "THUMBS UP (v0.2)",
}
"""Display names for gesture names found in analytics recorded by version 0.2."""


def stored_gesture_label(value: str) -> str:
    """Human-readable name of a gesture as stored in the analytics database."""
    if value in LEGACY_GESTURE_LABELS:
        return LEGACY_GESTURE_LABELS[value]
    try:
        return GestureType(value).label
    except ValueError:
        return value


class GesturePhase(enum.Enum):
    """Lifecycle of one recognizer.

    IDLE -> CANDIDATE (criteria partially met) -> CONFIRMED (event emitted, for one frame)
    -> COOLDOWN (time based) -> REARMING (waits for a neutral state) -> IDLE.
    A candidate that fails its criteria returns to IDLE with a rejection reason.
    """

    IDLE = "idle"
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    COOLDOWN = "cooldown"
    REARMING = "rearming"


class ControlStatus(enum.Enum):
    DISABLED = "disabled"
    NO_HAND = "no control hand"
    AMBIGUOUS = "ambiguous"
    STABILIZING = "stabilizing"
    ACTIVE = "active"


@dataclass(frozen=True, slots=True)
class GestureEvent:
    """A confirmed gesture.

    ``timestamp_ns`` is the capture timestamp of the frame that confirmed the gesture (the
    shared ``perf_counter_ns`` clock). Directions are from the user's perspective: ``left`` and
    ``right`` refer to the user's own left and right, independent of preview mirroring.
    ``magnitude_palms`` is the fingertip stroke length for swipes and ``palm_magnitude_palms``
    the palm's displacement along the same direction (how much of the stroke was whole-hand
    movement); ``duration_s`` is the stroke time for swipes and the hold time for static poses.
    No confidence value is reported because the classifier is rule based; the criteria are
    documented in ``docs/architecture/GESTURES.md``.
    """

    gesture: GestureType
    timestamp_ns: int
    track_id: int
    handedness: Handedness
    direction: str | None = None
    magnitude_palms: float | None = None
    peak_speed_palms_s: float | None = None
    duration_s: float = 0.0
    palm_magnitude_palms: float | None = None
    decision_delay_s: float = 0.0
    detector: str = ""
    """Which detector recognized a swipe: ``finger``, ``fist`` or ``palm`` (Brief 005)."""
    """Time between meeting every criterion and the confirmation (the recognizer's own
    waiting, reported separately from the time the movement itself takes)."""
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass(frozen=True, slots=True)
class GestureCandidate:
    gesture: GestureType
    progress: float
    """Fraction of the confirmation requirement met (distance for swipes, hold for poses)."""
    elapsed_s: float


class RejectCode:
    """Stable machine-readable rejection codes (diagnostics, statistics, explanations)."""

    TOO_SHORT = "too_short"
    TOO_SLOW = "too_slow"
    TOO_LONG = "too_long"
    TOO_FAR = "too_far"
    DIAGONAL = "diagonal"
    POSE = "pose"
    RETURN = "return"
    COOLDOWN = "cooldown"
    NOT_ARMED = "not_armed"
    NOT_ACTIVATED = "not_activated"
    DISABLED = "disabled"
    HAND_MOVING = "hand_moving"
    RELEASED = "released"
    TRACKING_LOST = "tracking_lost"
    AMBIGUOUS = "ambiguous_hand"
    HAND_CHANGED = "hand_changed"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class GestureRejection:
    """Why a gesture candidate was not confirmed.

    ``code`` is a :class:`RejectCode`; ``measured``/``required`` (in ``unit``) quantify the
    failed criterion where one applies, e.g. a swipe of 0.42 palm lengths where 0.80 are
    required. ``details`` lists unmet pose conditions (half-heart, stop)."""

    gesture: GestureType
    reason: str
    timestamp_ns: int
    code: str = ""
    measured: float | None = None
    required: float | None = None
    unit: str = ""
    details: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MotionTrace:
    """The stroke a swipe detector is following right now (measured, for the overlay)."""

    detector: str
    gesture: GestureType
    reference_px: tuple[float, float]
    """Current position of the motion reference (fingertip or palm centre), source pixels."""
    start_px: tuple[float, float]
    """Where the stroke started, source pixels."""
    travel_palms: float
    """Travel along the committed direction, hand lengths."""
    required_palms: float
    phase: str
    """``moving``, ``return`` (the hand coming back), ``blocked`` (cooldown / not armed /
    not activated) or ``waiting`` (flick waiting for the finger, hand near the bottom)."""


@dataclass(frozen=True, slots=True)
class GestureFrame:
    """Gesture engine output for one processed frame."""

    timestamp_ns: int
    status: ControlStatus
    status_detail: str = ""
    control_track_id: int | None = None
    control_handedness: Handedness | None = None
    pose: str | None = None
    phase: GesturePhase = GesturePhase.IDLE
    candidates: tuple[GestureCandidate, ...] = ()
    events: tuple[GestureEvent, ...] = ()
    rejection: GestureRejection | None = None
    """A candidate rejected in this frame, if any."""
    blocked_until_ns: int | None = None
    """End of the global cooldown after the last confirmed gesture, if still running."""
    hint: str = ""
    """A positioning hint from measured tracking quality (e.g. hand too far away)."""
    hand_scale_px: float | None = None
    """Hand size of the control hand in source pixels (``pose.hand_scale_px``)."""
    motion: MotionTrace | None = None
