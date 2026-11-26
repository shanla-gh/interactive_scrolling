"""Control modes, actions, outcomes and the controller interface."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Protocol

from interactive_scrolling.gestures.types import GestureEvent, GestureType


class ControlMode(enum.Enum):
    TRACKING_ONLY = "tracking_only"
    """Camera and tracking run; gestures are not recognized and nothing is executed."""
    GESTURE_TEST = "gesture_test"
    """Gestures are recognized, shown and logged; no external action is executed."""
    LIVE_CONTROL = "live_control"
    """Confirmed gestures may execute their mapped action after all safety checks."""

    @property
    def label(self) -> str:
        return {
            ControlMode.TRACKING_ONLY: "Tracking only",
            ControlMode.GESTURE_TEST: "Gesture test",
            ControlMode.LIVE_CONTROL: "Live control",
        }[self]


class ActionType(enum.Enum):
    NONE = "none"
    NEXT_SHORT = "next_short"
    PREVIOUS_SHORT = "previous_short"
    LIKE_SHORT = "like_short"
    TOGGLE_PLAYBACK = "toggle_playback"
    SWITCH_TO_STUDY_APP = "switch_to_study_app"
    RETURN_TO_SOCIAL_APP = "return_to_social_app"

    @property
    def label(self) -> str:
        return _ACTION_LABELS[self]

    @property
    def available(self) -> bool:
        """Whether this version can execute the action."""
        return self in YOUTUBE_ACTIONS


_ACTION_LABELS = {
    ActionType.NONE: "No action",
    ActionType.NEXT_SHORT: "Next Short",
    ActionType.PREVIOUS_SHORT: "Previous Short",
    ActionType.LIKE_SHORT: "Like Short",
    ActionType.TOGGLE_PLAYBACK: "Pause / resume",
    ActionType.SWITCH_TO_STUDY_APP: "Switch to study app (planned)",
    ActionType.RETURN_TO_SOCIAL_APP: "Return to social app (planned)",
}

YOUTUBE_ACTIONS = frozenset(
    {
        ActionType.NEXT_SHORT,
        ActionType.PREVIOUS_SHORT,
        ActionType.LIKE_SHORT,
        ActionType.TOGGLE_PLAYBACK,
    }
)

CONFIGURABLE_GESTURES = (
    GestureType.FINGER_SWIPE_DOWN,
    GestureType.FINGER_SWIPE_UP,
    GestureType.THUMBS_UP,
    GestureType.STOP_GESTURE,
)
"""Gestures whose action the user can change. Hand sweeps are reserved for M4."""

DEFAULT_MAPPING: dict[GestureType, ActionType] = {
    GestureType.FINGER_SWIPE_DOWN: ActionType.NEXT_SHORT,
    GestureType.FINGER_SWIPE_UP: ActionType.PREVIOUS_SHORT,
    GestureType.THUMBS_UP: ActionType.LIKE_SHORT,
    GestureType.STOP_GESTURE: ActionType.TOGGLE_PLAYBACK,
    GestureType.HAND_SWIPE_RIGHT: ActionType.SWITCH_TO_STUDY_APP,
    GestureType.HAND_SWIPE_LEFT: ActionType.RETURN_TO_SOCIAL_APP,
}


class MappingError(ValueError):
    pass


def validate_mapping(mapping: dict[GestureType, ActionType]) -> dict[GestureType, ActionType]:
    """Return a complete mapping; reject assignments outside the allowed action set."""
    result = dict(DEFAULT_MAPPING)
    for gesture, action in mapping.items():
        if gesture in CONFIGURABLE_GESTURES:
            if action is not ActionType.NONE and action not in YOUTUBE_ACTIONS:
                raise MappingError(f"{gesture.label} cannot be mapped to {action.label}.")
        elif action is not DEFAULT_MAPPING[gesture]:
            raise MappingError(f"{gesture.label} is reserved for a later milestone.")
        result[gesture] = action
    return result


class ActionStatus(enum.Enum):
    """Lifecycle and outcome of the action requested for one confirmed gesture."""

    NOT_EXECUTED = "not executed"
    """Recognized but intentionally not executed (mode, mapping, availability)."""
    QUEUED = "queued"
    DISPATCHED = "dispatched"
    """Sent to the controller; outcome not known yet."""
    SUCCEEDED = "succeeded"
    """The controller confirmed the intended effect (e.g. the active Short changed)."""
    NO_CHANGE = "no change"
    """Valid request with nothing to do (e.g. the Short was already liked)."""
    REJECTED = "rejected"
    """Refused before execution (no valid context, stale, busy, disabled)."""
    FAILED = "failed"
    """Execution was attempted and the intended effect did not happen."""
    UNKNOWN = "outcome unknown"
    """The request may or may not have had an effect (e.g. timeout, disabled mid-flight)."""

    @property
    def final(self) -> bool:
        return self not in (ActionStatus.QUEUED, ActionStatus.DISPATCHED)


@dataclass(frozen=True, slots=True)
class ActionResult:
    status: ActionStatus
    reason: str = ""
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ControllerCheck:
    ready: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class ActionRecord:
    """Snapshot of one gesture's journey through the dispatcher (immutable; one per update)."""

    record_id: str
    event: GestureEvent
    action: ActionType
    mode: ControlMode
    status: ActionStatus
    reason: str = ""
    detail: str = ""
    created_ns: int = 0
    dispatched_ns: int | None = None
    completed_ns: int | None = None
    wall_time: float = 0.0
    """Local wall-clock time (epoch seconds) when the gesture was confirmed, for display."""
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def action_latency_ms(self) -> float | None:
        """Time from dispatch to the controller's confirmed outcome."""
        if self.dispatched_ns is None or self.completed_ns is None:
            return None
        return (self.completed_ns - self.dispatched_ns) / 1e6

    @property
    def end_to_end_ms(self) -> float | None:
        """Time from the frame that confirmed the gesture to the confirmed outcome."""
        if self.completed_ns is None:
            return None
        return (self.completed_ns - self.event.timestamp_ns) / 1e6


class ActionController(Protocol):
    """Executes actions on one platform. Methods are called from the dispatcher thread."""

    def check(self, action: ActionType) -> ControllerCheck:
        """Whether ``action`` can be executed right now, and why not."""
        ...

    def execute(self, action: ActionType, request_id: str, timeout_s: float) -> ActionResult:
        """Execute and confirm ``action``; block at most ``timeout_s``."""
        ...

    def cancel_all(self) -> None:
        """Abandon any in-flight request (emergency disable)."""
        ...
