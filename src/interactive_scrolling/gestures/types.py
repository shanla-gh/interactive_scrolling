"""Gesture vocabulary, lifecycle phases and the data produced by the gesture engine."""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field

from interactive_scrolling.vision.landmarks import Handedness


class GestureType(enum.Enum):
    FINGER_SWIPE_DOWN = "finger_swipe_down"
    FINGER_SWIPE_UP = "finger_swipe_up"
    HAND_SWIPE_LEFT = "hand_swipe_left"
    HAND_SWIPE_RIGHT = "hand_swipe_right"
    THUMBS_UP = "thumbs_up"
    STOP_GESTURE = "stop_gesture"

    @property
    def label(self) -> str:
        return _LABELS[self]

    @property
    def is_dynamic(self) -> bool:
        return self in _DYNAMIC


_LABELS = {
    GestureType.FINGER_SWIPE_DOWN: "SWIPE DOWN",
    GestureType.FINGER_SWIPE_UP: "SWIPE UP",
    GestureType.HAND_SWIPE_LEFT: "HAND SWIPE LEFT",
    GestureType.HAND_SWIPE_RIGHT: "HAND SWIPE RIGHT",
    GestureType.THUMBS_UP: "THUMBS UP",
    GestureType.STOP_GESTURE: "STOP",
}
_DYNAMIC = {
    GestureType.FINGER_SWIPE_DOWN,
    GestureType.FINGER_SWIPE_UP,
    GestureType.HAND_SWIPE_LEFT,
    GestureType.HAND_SWIPE_RIGHT,
}


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
    ``magnitude_palms`` is the stroke length for swipes; ``duration_s`` is the stroke time for
    swipes and the hold time for static poses. No confidence value is reported because the
    classifier is rule based; the criteria are documented in ``docs/architecture/GESTURES.md``.
    """

    gesture: GestureType
    timestamp_ns: int
    track_id: int
    handedness: Handedness
    direction: str | None = None
    magnitude_palms: float | None = None
    peak_speed_palms_s: float | None = None
    duration_s: float = 0.0
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass(frozen=True, slots=True)
class GestureCandidate:
    gesture: GestureType
    progress: float
    """Fraction of the confirmation requirement met (distance for swipes, hold for poses)."""
    elapsed_s: float


@dataclass(frozen=True, slots=True)
class GestureRejection:
    gesture: GestureType
    reason: str
    timestamp_ns: int


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
